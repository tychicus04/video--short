"""`vshort auto`: run a whole video without a Claude session steering it — fixed steps are `vshort` commands, the
judgement steps are vs-* agents called with `claude -p`. Every call's cost goes to RUN/cost.json."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vshort import timing
from vshort.run import Run

ROOT = Path(__file__).resolve().parent.parent  # agents run here: Sonnet session, advisor off, `model:` of the agent
CLAUDE = ["claude"]
TIMEOUT = {"vs-researcher": 1800, "vs-transcriber": 900, "vs-translator": 1200, "vs-motion": 2400, "vs-visuals": 2400,
           "vs-nhip": 1800, "vs-reviewer": 3600}  # seconds


GIT_TIMEOUT = 120  # seconds per git call: a hung network must not keep a finished video "running"
_COST = threading.Lock()  # the canvas agent logs its cost while the others do


class AgentError(Exception):
    pass


def _log_cost(run: Run, step: str, agent: str, seconds: float, out: dict, ok: bool) -> None:
    with _COST:
        rows = run.read("cost.json") if run.file("cost.json").exists() else []
        rows.append({"step": step, "agent": agent, "seconds": round(seconds), "cost_usd": out.get("total_cost_usd") or 0,
                     "models": list(out.get("modelUsage") or {}), "ok": ok})
        run.write("cost.json", rows)


def _agent_env() -> dict[str, str]:
    """Our environment without the Claude Code session that may have started us (`/video-short`): each agent is
    its own top-level session, not a child of that one."""
    return {k: v for k, v in os.environ.items() if not (k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_"))}


def run_claude(run: Run, step: str, agent: str, prompt: str, timeout: int) -> str:
    """Run one agent headless; its reply text. AgentError (reason in Vietnamese) when it fails or overruns."""
    timing.start(run.path, step)
    t = time.monotonic()
    try:
        cp = subprocess.run([*CLAUDE, "-p", "--agent", agent, "--output-format", "json", prompt], cwd=ROOT,
                            capture_output=True, text=True, timeout=timeout, env=_agent_env())
    except subprocess.TimeoutExpired:
        _log_cost(run, step, agent, time.monotonic() - t, {}, False)
        raise AgentError(f"{agent} chạy quá {timeout // 60} phút ở bước {step}") from None
    try:
        out = json.loads(cp.stdout)
    except json.JSONDecodeError:
        out = {}
    ok = cp.returncode == 0 and bool(out) and not out.get("is_error")
    _log_cost(run, step, agent, time.monotonic() - t, out, ok)
    if not ok:
        why = (out.get("result") or cp.stderr or cp.stdout).strip().splitlines()[-1:] or ["không rõ lý do"]
        raise AgentError(f"{agent} lỗi ở bước {step} (mã {cp.returncode}): {why[0][:300]}")
    return out.get("result", "")


def get_state(run: Run) -> dict:
    """RUN/auto.json — what the skill (or Tai) reads: running | wait_brief | wait_script | error | done."""
    if run.file("auto.json").exists():
        return run.read("auto.json")
    return {"state": "none", "message": "", "round": 0, "pid": 0}


def set_state(run: Run, state: str, message: str = "", round: int | None = None, pid: int | None = None) -> None:
    """`pid` is the process doing the run (wait uses it to tell a run that died from one still going)."""
    old = get_state(run)
    run.write("auto.json", {"state": state, "message": message, "round": old["round"] if round is None else round,
                            "pid": pid or os.getpid()})


def alive_run(run: Run) -> bool:
    state = run.file("auto.json")
    return bool(locked_by(run)) or (state.exists() and _alive(get_state(run)["pid"], state.stat().st_mtime))


def _started(pid: int) -> float | None:
    """When process `pid` started (epoch seconds), or None if there is no such process. Same on macOS and Linux."""
    if pid <= 0:
        return None
    cp = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                        env=os.environ | {"LC_ALL": "C"})
    return time.mktime(time.strptime(cp.stdout.strip(), "%a %b %d %H:%M:%S %Y")) if cp.stdout.strip() else None


def _alive(pid: int, since: float) -> bool:
    """`pid` is running and started no later than `since` (the mtime of the file that names it). After a reboot the old
    pid may belong to some other process; that one started after the file was written. `lstart` is whole seconds, the
    file is always written after its process started (by itself, or by `cmd_auto` after Popen), hence some slack. 30 s,
    not 1: right after boot the clock can step forward (chrony makestep) between the process starting and the file being
    written, and a live run must not look dead and lose its lock. A reused pid starts hours later, never within 30 s."""
    start = _started(pid)
    return start is not None and start <= since + 30


def locked_by(run: Run) -> int | None:
    """The pid of the live `vshort auto` working on this run, if any (a dead one's lock doesn't count)."""
    lock = run.file("auto.lock")
    pid = lock.read_text().strip() if lock.exists() else ""
    return int(pid) if pid.isdigit() and _alive(int(pid), lock.stat().st_mtime) else None


def acquire_lock(run: Run) -> bool:
    """One `vshort auto` per run folder; the lock of a process that died is taken over."""
    if locked_by(run):
        return False
    run.file("auto.lock").write_text(str(os.getpid()))
    return True


def release_lock(run: Run) -> None:
    run.file("auto.lock").unlink(missing_ok=True)


def total_cost(run: Run) -> float:
    return sum(r["cost_usd"] for r in run.read("cost.json")) if run.file("cost.json").exists() else 0.0


# --- the flow ------------------------------------------------------------------------------------------------------

FETCH_PROMPT = (
    "Vertical short. Follow the source '# BRIEF (EN) – {slug}' closely: open with its title line, word for word, "
    "cover its key points in order, end with its call to action. Walk through its 'How it works, step by step' section "
    "in order, unless it says None. Explain at concept level only; do not assert claims the brief marks as disputed."
)
RESEARCH = ("Bước 1 của /video-short.\n\n- Chủ đề: {topic}\n- slug: `{slug}`\n- RUN={run}\n\n"
            "Ghi notebook id (chỉ id, một dòng) vào {run}/notebook.txt.")
BRIEF_CHECK = (
    "RUN={run}. Chế độ tự động: Tai không duyệt brief. Soát brief ({run}/brief.vi.md và {run}/brief.en.md) với {run}/sources.md: "
    "dữ kiện, ngày, điểm tranh cãi. Soát cả mục \"Cơ chế từng bước\" theo luật an toàn: chỉ mức khái niệm, không tên lỗ hổng/"
    "kỹ thuật/công cụ, không mã hay lệnh. Lệch thì sửa ở cả hai bản. Không tạo notebook mới, không nạp nguồn mới.")
TRANSCRIBE = ("RUN={run}. Đọc các ảnh mảnh phụ đề {sheets} ({n} mảnh, chỉ số 0–{last}, theo {run}/fragments.json) "
              "và ghi {run}/fragments_text.json.")
TRANSLATE = "RUN={run}\n\nĐầu ra nguyên văn của `vshort text`:\n\n```\n{table}\n```"
MOTION_DESIGN = ("Việc 1 — vẽ khung từ brief. RUN={run}\n\nĐọc {run}/brief.vi.md (mục \"Cơ chế từng bước\" và \"Lưu ý độ "
                 "chính xác\"), viết {run}/motion.json; hình chưa có trong assets/shapes/ thì vẽ vào {run}/shapes/. "
                 "Chạy `vshort motion {run} --design` tới khi mã 0.")
MOTION_BIND = ("Việc 2 — gắn nhịp vào lời. RUN={run}\n\nĐọc {run}/motion.json và {run}/script.vi.json, viết "
               "{run}/motion.bind.json. Chạy `vshort motion {run}` tới khi mã 0.")
VISUALS = ("RUN={run}\n\nĐọc {run}/motion.bind.json (lines) để biết câu nào đã có hình động (đừng chọn tư liệu cho các câu đó), "
           "{run}/sources.md (nguồn tư liệu thật) và {run}/brief.vi.md (mục \"Lưu ý độ chính xác\") khi vá chữ.")
NHIP = ("RUN={run}\n\nChạy `vshort shots {run} --prep`, đọc {run}/shots/phrases.txt, rồi làm nhịp hình như hướng dẫn; "
        "tự chạy `vshort shots {run}` tới khi mã 0.")
COVER = ("Việc riêng: chọn ảnh đại diện, viết tiêu đề đăng và prompt ảnh bìa cho video, không làm gì khác (không tạo notebook, không nạp "
         "nguồn, không sửa brief). RUN={run}. Chạy `vshort cover {run} --candidates`: nó tải ảnh đầu bài (og:image) của các "
         "nguồn trong {run}/sources.md, ghép thành {run}/cover/sheet.jpg có đánh số. Xem ảnh đó, {run}/brief.vi.md và "
         "{run}/script.vi.json (lời video thật sự nói). Chọn MỘT ảnh minh hoạ đúng chủ đề video: ưu tiên ảnh của nguồn "
         "gốc/chính thức; bỏ logo, thẻ chỉ có tên hãng hay tên bài, sơ đồ kỹ thuật lộ tên tệp/công cụ mà brief cấm.\n\n"
         "Rồi viết hai dòng chữ: \"title\" — tiêu đề đăng video (60–90 ký tự), giật tít, gây tò mò mà vẫn đúng sự thật và "
         "có chất kỹ thuật: nêu tên sản phẩm/hãng, mã CVE, điểm CVSS hay con số cụ thể có trong script.vi.json, và hậu quả "
         "người xem quan tâm (ví dụ \"Lỗ hổng CVSS 10 trong LXD: mạo danh client, chiếm cả cụm máy không cần khóa\"); "
         "\"thumb\" — chữ in lên ảnh bìa (3–6 từ, ≤ 32 ký tự), đặt từ khóa đắt nhất trong dấu sao để tô vàng (ví dụ "
         "\"*CVSS 10*: chiếm cụm không cần khóa\"). Chỉ dùng dữ kiện có trong script.vi.json; không bịa số; không tên "
         "tệp/công cụ mà mục \"Lưu ý độ chính xác\" của brief cấm.\n\n"
         "Cuối cùng viết \"poster\" — phần riêng của prompt để Tai dán vào app Gemini vẽ ảnh bìa kiểu poster tin nóng "
         "(khung chung: phong cách, chữ đúng dấu, không logo thật, đã có sẵn trong code): \"scene\" bằng tiếng Anh, gồm một "
         "câu \"Story:\" kể sự việc bằng lời thường, rồi \"Layout, top to bottom:\" với 3–4 gạch đầu dòng tả thứ cụ thể "
         "nhìn thấy được ở trên, giữa (vật chính, cận cảnh, có chi tiết hậu quả) và đáy khung; vật chính không ghi tên hãng "
         "hay logo; \"badge\" — nhãn đỏ góc trên phải, 2–3 từ in hoa (\"CẢNH BÁO KHẨN\" khi đang bị tấn công/cần vá "
         "ngay, \"TIN BẢO MẬT\" hay \"CÔNG NGHỆ MỚI\" khi không khẩn); \"lines\" — 4 dòng tít tiếng Việt xếp chồng: "
         "dòng 1 (đỏ, to nhất, 2–4 từ in hoa) và dòng 2 (trắng, to, 2–4 từ in hoa, có thể có dấu !) là cú đấm; dòng 3 "
         "(vàng, ≤ 32 ký tự) là hậu quả; dòng 4 (trắng, ≤ 32 ký tự) là việc người xem nên làm. Ví dụ cho video NAS "
         "Synology bị tống tiền: scene = \"Story: ransomware is attacking home NAS storage boxes running an old, unpatched "
         "operating system; it encrypts the owner's photos and documents and leaves a ransom note.\\n\\nLayout, top to "
         "bottom:\\n- Top-left: a hooded hacker typing on a laptop in the dark, floating code and red WARNING tags.\\n- "
         "Center: a close-up of a black 4-bay home NAS with glowing red drive lights, a cracked red padlock in front, photo "
         "and document icons turning into locked files, a red ransom note taped to its front.\\n- Bottom: a dim home "
         "office shelf with the NAS among family photo frames, red smoke and two yellow warning triangles.\", lines = "
         "[\"NAS CHƯA VÁ\", \"BỊ TỐNG TIỀN!\", \"Mã độc mã hóa ảnh, tài liệu\", \"Cập nhật DSM ngay hôm nay\"]. Cùng "
         "luật dữ kiện như title.\n\nGhi {run}/cover/pick.json: "
         "{{\"n\": số hoặc null khi không ảnh nào hợp, \"why\": \"…\", \"title\": \"…\", \"thumb\": \"…\", "
         "\"poster\": {{\"scene\": \"…\", \"badge\": \"…\", \"lines\": [\"…\", \"…\", \"…\", \"…\"]}}}}. "
         "Đừng chạy `vshort cover {run}` không có --candidates.")
COVER_TIMEOUT = 600  # seconds: one sheet to look at
MAC_DIR = "~/Movies/vshort"  # where the Mac's LaunchAgent (scripts/vn.tai.vshort-keo.plist) pulls */xuat/ to
REVIEW = "RUN={run}. final.mp4 đã render. Soát video cuối; ghi {run}/review.md và {run}/review.json."
RECHECK = ("Soát lại: chỉ các phần đã sửa.\n\nRUN={run}. review.md cũ: {run}/review.md. Đã sửa (lỗi, agent, câu, thời điểm):\n"
           "{fixed}\nGhi kết quả vào cuối review.md và ghi lại review.json cho lần soát này.")
FIX = ("RUN={run}\n\nSửa theo {run}/review.json, các lỗi agent={agent}:\n{items}\n{how}")
FIX_HOW = {
    "motion": ("Sửa motion.json và/hoặc motion.bind.json; được thêm hình mới vào RUN/shapes/, không sửa hình đã có trong "
               "thư viện; tự chạy `vshort motion` tới khi mã 0."),
    "visuals": "Sửa visuals.json rồi tự chạy `vshort visuals` tới khi mã 0.",
    "shots": "Sửa shots.json rồi tự chạy `vshort shots` tới khi mã 0.",
    "translator": ("Ghi bản sửa vào {run}/script.proposed.json (cùng dạng script.vi.json, sửa cả `note`); "
                   "KHÔNG sửa script.vi.json — Tai duyệt bản đề xuất trước."),
}
MAX_ROUNDS = 2
BUDGET = 5.0
FAILED_CODE = 1


class Stop(Exception):
    """End this `vshort auto` run: `code` is its exit code, `state` what auto.json says."""

    def __init__(self, code: int, message: str, state: str = "error"):
        super().__init__(message)
        self.code, self.message, self.state = code, message, state


def run_vshort(args: list[str]) -> int:
    """`vshort <step> <run> …`; the step's start goes to times.json (its end comes with Run.mark)."""
    from vshort import cli
    if len(args) >= 2 and Path(args[1]).is_dir():
        timing.start(Path(args[1]), args[0])
    return cli.main(args)


def notebooklm(args: list[str]) -> int:
    from vshort import cli
    return cli._notebooklm(args)[1]


def _vs(run: Run, step: str, *extra: str) -> None:
    """A fixed `vshort` step, skipped when state.json has it done."""
    if run.done(step):
        return
    if code := run_vshort([step, str(run.path), *extra]):
        from vshort.cli import AUTH, RELOGIN
        raise Stop(code, RELOGIN if code == AUTH else f"`vshort {step} {run.path}` lỗi (mã {code}); xem auto.log")


def _agent(run: Run, step: str, agent: str, prompt: str) -> None:
    """A judgement step done by an agent, skipped when state.json has it done."""
    if not run.done(step):
        run_claude(run, step, agent, prompt, TIMEOUT[agent])
        run.mark(step)


def _table(run: Run) -> str:
    return "\n".join(f"{s['id']}\t{s['start']:.2f}–{s['end']:.2f}\t{s['en']}" for s in run.read("sentences.en.json"))


def _translation_md(run: Run) -> str:
    en = {s["id"]: s["en"] for s in run.read("sentences.en.json")}
    rows = ["| id | tiếng Anh | tiếng Việt | note |", "|---|---|---|---|"]
    for r in run.read("script.vi.json"):
        vi = " ".join(r["phrases"].replace("|", " ").split())
        rows.append(f"| {r['id']} | {en.get(r['id'], '')} | {vi} | {r.get('note', '')} |")
    return "\n".join(rows) + "\n"


def _flow(run: Run) -> int:
    from vshort.cli import FAILED, OK, WAIT_BRIEF, WAIT_SCRIPT
    meta, p = run.read("run.json"), run.path
    if not run.done("research"):
        # Fail before the researcher agent is paid for, not at the first NotebookLM call after it.
        # ponytail: this command once hung for over 2 minutes on the Mac; if it hangs on the server, add a timeout to run_notebooklm.
        if code := notebooklm(["auth", "check", "--test"]):
            from vshort.cli import AUTH, RELOGIN
            raise Stop(code, RELOGIN if code == AUTH else "Không kiểm được phiên NotebookLM; xem auto.log")
        run_claude(run, "research", "vs-researcher", RESEARCH.format(topic=meta["topic"], slug=meta["slug"], run=p),
                   TIMEOUT["vs-researcher"])
        nb = run.file("notebook.txt").read_text().strip() if run.file("notebook.txt").exists() else ""
        if not nb:
            raise Stop(FAILED, f"researcher không ghi notebook id vào {p}/notebook.txt")
        run.write("run.json", meta | {"notebook_id": nb})
        run.mark("research")
    meta = run.read("run.json")
    if meta.get("auto"):
        _agent(run, "brief_check", "vs-researcher", BRIEF_CHECK.format(run=p))
    elif not run.done("approve_brief"):
        raise Stop(WAIT_BRIEF, f"Duyệt brief: {p}/brief.vi.md (sửa thì sửa cả brief.en.md), rồi "
                               f"`vshort approve {p} brief` và `vshort auto {p}`.", "wait_brief")
    if not run.done("source"):
        timing.start(run.path, "source")
        if code := notebooklm(["source", "add", "-n", meta["notebook_id"], "--type", "text", "--title",
                               f"# BRIEF (EN) – {meta['slug']}", run.file("brief.en.md").read_text()]):
            from vshort.cli import AUTH, RELOGIN
            raise Stop(code, RELOGIN if code == AUTH else "NotebookLM không nạp được brief tiếng Anh; xem auto.log")
        run.mark("source")
    with ThreadPoolExecutor(1) as ex:  # the canvas is drawn from the brief while NotebookLM works; waited for on any exit
        design = None if run.done("motion_design") else ex.submit(_design, run)
        _vs(run, "fetch", "--prompt", FETCH_PROMPT.format(slug=meta["slug"]))
        _vs(run, "detect")
        if not run.done("transcribe"):
            sheets = sorted(run.file("sheets").glob("sheet*.png"))
            n = len(run.read("fragments.json"))
            _agent(run, "transcribe", "vs-transcriber",
                   TRANSCRIBE.format(run=p, sheets=", ".join(map(str, sheets)), n=n, last=n - 1))
        _vs(run, "text")
        if not run.done("translate"):
            run_claude(run, "translate", "vs-translator", TRANSLATE.format(run=p, table=_table(run)),
                       TIMEOUT["vs-translator"])
            if code := run_vshort(["check", str(p)]):
                raise Stop(FAILED, f"bản dịch chưa qua `vshort check` (mã {code}); xem auto.log")
            run.mark("translate")
        if design:
            design.result()
    if not run.done("approve_script"):
        run.file("translation.md").write_text(_translation_md(run), encoding="utf-8")
        raise Stop(WAIT_SCRIPT, f"Duyệt bản dịch: {p}/translation.md (sửa thì sửa {p}/script.vi.json), rồi "
                                f"`vshort approve {p} script` và `vshort auto {p}`.", "wait_script")
    _build(run)
    _review(run)
    return OK


def read_review(run: Run) -> dict:
    """RUN/review.json as the reviewer wrote it: {"verdict": "Đạt"|"Cần sửa", "findings": [{agent, ids, at, what}]}."""
    try:
        rev = run.read("review.json")
        assert rev["verdict"] in ("Đạt", "Cần sửa") and isinstance(rev["findings"], list)
        for f in rev["findings"]:
            assert f["agent"] in ("motion", "visuals", "translator", "shots", "none")
            assert isinstance(f["what"], str) and isinstance(f.get("ids", []), list)
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        raise AgentError(f"review.json không đọc được (thiếu hoặc sai dạng) — xem {run.path}/review.md") from None
    return rev


def _items(fs: list[dict]) -> str:
    return "\n".join(f"- {f['agent']}, câu {', '.join(map(str, f.get('ids', [])))}, {f.get('at', '')}: {f['what']}"
                     for f in fs)


def _fix(run: Run, r: int, todo: list[dict]) -> None:
    """Round r's fixes; each agent step is marked, so a run that died midway redoes only what is left."""
    from vshort.cli import WAIT_SCRIPT
    p = run.path
    by = {a: [f for f in todo if f["agent"] == a] for a in ("motion", "visuals", "shots", "translator")}
    for agent, redo in (("motion", _motion), ("visuals", _visuals), ("shots", _shots)):  # the beats last: they stand on the rest
        if by[agent]:
            redo(run, FIX.format(run=p, agent=agent, items=_items(by[agent]), how=FIX_HOW[agent]), step=f"fix{r}_{agent}")
            run.unmark("render")
    if by["translator"]:
        if not run.done(f"fix{r}_translator"):
            run_claude(run, f"fix{r}_translator", "vs-translator",
                       FIX.format(run=p, agent="translator", items=_items(by["translator"]),
                                  how=FIX_HOW["translator"].format(run=p)), TIMEOUT["vs-translator"])
            if not run.file("script.proposed.json").exists():
                raise AgentError("vs-translator không ghi script.proposed.json khi sửa theo review")
            run.mark(f"fix{r}_translator")
        # the voice, stills (a line may no longer be empty), visuals and the motion check all follow the words
        run.unmark("approve_script", "tts", "timeline", "shots", "render", "motion", "motion_bind", "stills", "visuals")
        run.mark(f"fixed{r}")  # what is left (read the voice again, render) happens once Tai approves
        raise Stop(WAIT_SCRIPT, _proposal(run), "wait_script")
    _render(run)
    run.mark(f"fixed{r}")


def _review(run: Run) -> None:
    """Review; while it finds what an agent can fix, fix it and have a fresh reviewer check the fix (≤ MAX_ROUNDS)."""
    p = run.path
    while True:
        r = get_state(run)["round"]
        if r and not run.done(f"fixed{r}"):  # died during round r's fixes: finish them first
            _fix(run, r, run.read(f"fix{r}.json"))
        if not run.done(f"review{r}"):
            prompt = REVIEW.format(run=p) if r == 0 else RECHECK.format(run=p, fixed=_items(run.read(f"fix{r}.json")))
            run.file("review.json").unlink(missing_ok=True)  # never act on the previous reviewer's findings
            run_claude(run, f"review{r}", "vs-reviewer", prompt, TIMEOUT["vs-reviewer"])
            read_review(run)  # a bad file is not marked done: a rerun asks a reviewer again
            run.mark(f"review{r}")
        rev = read_review(run)
        todo = [f for f in rev["findings"] if f["agent"] != "none"]
        if rev["verdict"] == "Đạt" or not todo or r >= MAX_ROUNDS:
            _finish(run, rev, r)
            return
        run.write(f"fix{r + 1}.json", todo)  # before the round number moves: a resume finds what to fix
        set_state(run, "running", round=r + 1)


def _proposal(run: Run) -> str:
    old = {r["id"]: r for r in run.read("script.vi.json")}
    lines = [f"Reviewer thấy lỗi ở bản dịch; bản sửa đề xuất: {run.path}/script.proposed.json"]
    for r in run.read("script.proposed.json"):
        a, b = (" ".join(x.replace("|", " ").split()) for x in (old.get(r["id"], {}).get("phrases", ""), r["phrases"]))
        if a != b:
            lines.append(f"câu {r['id']}: {a}  →  {b}" + (f"  ({r['note']})" if r.get("note") else ""))
    lines.append(f"Đồng ý thì chép đè lên script.vi.json (hoặc sửa tay) và xóa script.proposed.json, rồi "
                 f"`vshort approve {run.path} script` và `vshort auto {run.path}`.")
    return "\n".join(lines)


def _voice(run: Run) -> str:
    from vshort import cli
    try:
        made = [Path(c["path"]).name for c in run.read("tts.json")]
        local = [q.name for q in cli.clip_paths(cli._tts_lines(run), run.file("tts"), cli._zerotts_tag(cli.config()))]
    except (OSError, ValueError, KeyError):
        return "?"
    return "ZeroTTS (hết lượt Gemini)" if made == local else "Gemini"


def _cover(run: Run) -> str:
    """The final message's title, cover and export lines. Never fails the video: a failed agent leaves the spoken
    title on the video's own still. `vshort cover` reruns every time, so the export carries the last final.mp4."""
    p = run.path
    if not run.done("cover"):
        try:
            run_claude(run, "cover", "vs-researcher", COVER.format(run=p), COVER_TIMEOUT)
        except AgentError as e:
            print(f"Ảnh đại diện: {e}; dùng ảnh từ video.", flush=True)
    run_vshort(["cover", str(p)])
    if not run.file("cover/cover.json").exists():  # `vshort cover` writes it last, after the pictures
        return f"Ảnh đại diện: chưa làm được, xem auto.log; làm lại: `vshort cover {p}`"
    info = run.read("cover/cover.json")
    where = f"{p}/cover/thumb-16x9.jpg, thumb-9x16.jpg (không chữ: anh-dai-dien-*.jpg)"
    out = [f"Tiêu đề: {info['title']}",
           f"Ảnh bìa: {where} — " + (f"ảnh của {info['page']} (ghi nguồn khi đăng)" if info["from"] == "source"
                                      else f"ảnh từ video, nên thay ({info.get('why') or 'không nguồn nào có ảnh hợp'})")]
    done = sorted(run.file("xuat").glob("*/"))
    out.append(f"Về Mac: Mac tự kéo về {MAC_DIR}/{done[0].name}/ (lấy ngay, gõ trong terminal Mac: "
               f"rsync -a 'pve2:{p}/xuat/' {MAC_DIR}/)" if done
               else f"Thư mục xuất: chưa làm được, xem auto.log; làm lại: `vshort cover {p}`")
    return "\n".join(out)


def _finish(run: Run, rev: dict, rounds: int) -> None:
    p = run.path
    out = [f"Video: {p}/final.mp4",
           _cover(run),
           f"Giọng: {_voice(run)}"]
    bind = run.read("motion.bind.json") if _canvas(run) and run.file("motion.bind.json").exists() else None
    if isinstance(bind, dict) and bind.get("lines"):
        out.append("Hình động: câu " + ", ".join(map(str, bind["lines"])))
    else:
        out.append("Hình động: không có" + (" (motion.json không qua kiểm, xem motion.loi.json)"
                                             if run.file("motion.loi.json").exists() else ""))
    out.append(_shots_note(run))
    fx = run.read("sfx.json") if run.file("sfx.json").exists() else []
    out.append("Hiệu ứng âm thanh: " + (", ".join(f"{c['name']} {c['at']:.1f} s" for c in fx) or "không có"))
    out.append(publish_shapes(run))
    for v in run.read("visuals.json") if run.file("visuals.json").exists() else []:
        out.append(f"- {v.get('kind')} câu {v.get('ids') or v.get('id')}: "
                   + (f"{v.get('old', '')} → {v.get('new', '')}" if v.get("kind") == "patch" else v.get("source", "")))
    left = [f for f in rev["findings"]]
    out.append(f"Soát: {rev['verdict']} sau {rounds} vòng sửa"
               + (" — còn lỗi, xem review.md" if rev["verdict"] != "Đạt" else ""))
    out += [f"  • {f['what']}" for f in left[:5]]
    rows = run.read("cost.json") if run.file("cost.json").exists() else []
    per: dict[str, float] = {}
    for row in rows:
        per[row["agent"]] = per.get(row["agent"], 0) + row["cost_usd"]
    total = total_cost(run)
    out.append(f"Chi phí Claude: ${total:.2f} (" + ", ".join(f"{a} ${c:.2f}" for a, c in per.items()) + ")")
    if total > BUDGET:
        out.append(f"Vượt ngân sách ${BUDGET:.0f}.")
    set_state(run, "done", "\n".join(out))


def _shots_note(run: Run) -> str:
    """The final message's line on the beat plan: the lines that follow it, and those allowed beats that fell back to the
    old camera (`vshort shots --prep` listed the allowed ones in shots/phrases.txt); else why there are none."""
    try:
        planned = sorted(int(i) for i in run.read("shots/ok.json")["lines"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):  # no verdicts, or not what `vshort shots` writes
        planned = []
    if not planned:
        return "Nhịp hình: không có (" + ("không câu nào qua `vshort shots`; chạy lại để xem lỗi" if run.file("shots.json").exists()
                                           else "thiếu shots.json: agent lỗi hoặc chưa ghi kế hoạch") + ")"
    try:
        allowed = [int(m[1]) for m in re.finditer(r"^câu (\d+) \(", run.file("shots/phrases.txt").read_text(encoding="utf-8"), re.M)]
    except OSError:
        allowed = []
    old = [i for i in allowed if i not in planned]
    return f"Nhịp hình: câu {', '.join(map(str, planned))}" + (f" (kiểu cũ: câu {', '.join(map(str, old))})" if old else "")


def _no_motion(run: Run) -> None:
    """motion.json failed its check: keep it (and its binding) as *.loi.json and go on with stills only."""
    for name in ("motion", "motion.bind"):
        if run.file(f"{name}.json").exists():
            run.file(f"{name}.json").replace(run.file(f"{name}.loi.json"))
    if code := run_vshort(["motion", str(run.path)]):
        raise Stop(code, f"`vshort motion` lỗi cả khi không có hình động (mã {code}); xem auto.log")


def _design(run: Run) -> None:
    """The canvas from the brief (alongside fetch…translate). A failed agent does not stop the video: one try, then
    the build finds no good canvas and goes on with stills."""
    try:
        run_claude(run, "motion_design", "vs-motion", MOTION_DESIGN.format(run=run.path), TIMEOUT["vs-motion"])
    except AgentError as e:
        print(f"Hình động: {e}; video dùng ảnh tĩnh cho đoạn cơ chế.", flush=True)
    run.mark("motion_design")


def _canvas(run: Run):
    """motion.json: None when there is none or it says null; True when it is not even JSON (the checks say why)."""
    from vshort import motion
    try:
        return motion.load(run.file("motion.json"))
    except ValueError:
        return True


def _motion(run: Run, prompt: str, step: str = "motion_bind") -> None:
    """The canvas bound to the lines by the agent; no canvas, or one that fails its check: stills only."""
    p = str(run.path)
    if _canvas(run) is None:  # none drawn (the brief has no mechanism, or the design agent failed): stills
        if code := run_vshort(["motion", p]):
            raise Stop(code, f"`vshort motion` lỗi cả khi không có hình động (mã {code}); xem auto.log")
        return
    # only an unbound canvas is checked against the brief: a fix may since use spoken words the brief lacks
    if not run.file("motion.bind.json").exists() and run_vshort(["motion", p, "--design"]):
        _no_motion(run)  # nothing worth binding: don't spend an agent on it
        return
    if not run.done(step):
        run_claude(run, step, "vs-motion", prompt, TIMEOUT["vs-motion"])
        run.mark(step)
    if run_vshort(["motion", p]):  # don't take the agent's word for it
        _no_motion(run)


def git(args: list[str]) -> tuple[int, str]:
    """git in the repo, never asking for a password and never hanging: (exit code, its message)."""
    try:
        cp = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=GIT_TIMEOUT,
                            env=os.environ | {"GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return cp.returncode, (cp.stderr or cp.stdout).strip()


def publish_shapes(run: Run) -> str:
    """The run's new shapes into the library, committed alone and pushed, so every machine draws them; one line for
    the final message. A git failure never fails the video."""
    from vshort import shapes
    doc = _canvas(run)
    used = {th.get("shape") for th in doc.get("things", []) if isinstance(th, dict)} if isinstance(doc, dict) else set()
    new = [f for f in sorted(run.file("shapes").glob("*.json"))  # only what the finished video draws: the library keeps all
           if f.stem in used and not (shapes.LIBRARY / f.name).exists() and not shapes.problems(shapes._read(f), f.stem)]
    if not new:
        return "Hình mới: không có"
    shapes.LIBRARY.mkdir(parents=True, exist_ok=True)
    for f in new:
        shutil.copy(f, shapes.LIBRARY / f.name)
    names, lib = ", ".join(f.stem for f in new), str(shapes.LIBRARY.relative_to(ROOT))
    for args in (["add", "--", lib], ["commit", "-m", f"shapes: {run.path.name}: {names}", "--", lib],
                 ["pull", "--rebase", "--autostash"], ["push"]):
        code, msg = git(args)
        if code:
            if args[0] == "pull":
                git(["rebase", "--abort"])  # never leave the checkout mid-rebase: every later pull would fail
            return f"Hình mới chưa lên repo ({names}): git {args[0]} lỗi: {(msg.splitlines() or [''])[-1][:200]}"
    return f"Hình mới lên repo: {names}"


def _visuals(run: Run, prompt: str, step: str = "visuals_agent") -> None:
    """The agent's visuals; when they fail: none, then fresh stills with the agent's again, then none for good."""
    if not run.done(step):
        run_claude(run, step, "vs-visuals", prompt, TIMEOUT["vs-visuals"])
        run.mark(step)
    p, mine, kept = str(run.path), run.file("visuals.json"), run.file("visuals.loi.json")
    if not run_vshort(["visuals", p]):
        return
    mine.replace(kept)
    run.write("visuals.json", [])
    if not run_vshort(["visuals", p]):
        return
    if run_vshort(["stills", p]):
        raise Stop(FAILED_CODE, "`vshort stills` lỗi khi làm lại ảnh tĩnh; xem auto.log")
    kept.replace(mine)
    if not run_vshort(["visuals", p]):
        return
    mine.replace(kept)
    run.write("visuals.json", [])
    if code := run_vshort(["visuals", p]):
        raise Stop(code, f"`vshort visuals` lỗi cả khi không có tư liệu (mã {code}); xem auto.log")


def _check_shots(run: Run) -> None:
    """`vshort shots` over the agent's plan: it writes shots/ok.json with the lines that pass, whatever the exit code says;
    the lines that don't render on the old camera, so no code stops the video."""
    run_vshort(["shots", str(run.path)])
    run.mark("shots")  # ends the step's time (run_vshort started it); the check itself is what is done


def _shots(run: Run, prompt: str, step: str = "shots_agent") -> None:
    """The beat plan by the agent. A failed agent or a plan that does not pass never stops the video: the lines that
    pass follow their beats, the rest (all of them, with no plan) keep the old camera."""
    if not run.done(step):
        if run_vshort(["shots", str(run.path), "--prep"]):  # nothing to plan from (no frames, a broken card): don't pay an agent
            print("Nhịp hình: chưa chuẩn bị được dữ liệu (`vshort shots --prep` lỗi); video dùng camera cũ.", flush=True)
        else:
            try:
                run_claude(run, step, "vs-nhip", prompt, TIMEOUT["vs-nhip"])
            except AgentError as e:
                print(f"Nhịp hình: {e}; video dùng camera cũ cho các câu chưa có nhịp.", flush=True)
        run.mark(step)
    _check_shots(run)


def _tts_result(run: Run, code: int) -> None:
    from vshort.cli import QUOTA
    if code == QUOTA:
        raise Stop(code, "Hết hạn mức Gemini TTS trong ngày và ZeroTTS không chạy được; xem auto.log")
    if code:
        raise Stop(code, f"`vshort tts` lỗi (mã {code}); xem auto.log")


def _render(run: Run) -> None:
    if not run.done("render"):
        if run_vshort(["render", str(run.path)]) == 2:
            _check_shots(run)  # the plan may only be stale (the script, pictures or voice changed since): ok.json for what is now
            # as the skill did: check motion again (it may only be stale), drop it only if it no longer passes
            if run_vshort(["motion", str(run.path)]):
                _no_motion(run)
            _vs(run, "render")


def _build(run: Run) -> None:
    p = str(run.path)
    with ThreadPoolExecutor(1) as ex:  # the voice is read while the pictures are made
        tts = None if run.done("tts") else ex.submit(run_vshort, ["tts", p])
        _vs(run, "plates")
        if not run.done("motion"):
            _motion(run, MOTION_BIND.format(run=p))
        _vs(run, "stills")
        if not run.done("visuals"):
            _visuals(run, VISUALS.format(run=p))
        if tts:
            _tts_result(run, tts.result())
    if not run.done("timeline"):
        if run_vshort(["timeline", p]) == 2:  # the voice was made from another script
            run.unmark("tts")
            _tts_result(run, run_vshort(["tts", p]))
            _vs(run, "timeline")
    if not run.done("shots") and not run.done("render"):  # a video rendered before this step existed: no plan to pay for
        _shots(run, NHIP.format(run=p))
    _render(run)


def run_auto(run: Run) -> int:
    """Run from the first unfinished step to the next stop; auto.json always says where it ended."""
    from vshort.cli import FAILED, OK
    timing.close_open(run.path)  # steps the last process died in: not "running for 9 hours"
    set_state(run, "running")
    try:
        code = _flow(run)
    except Stop as e:
        set_state(run, e.state, e.message)
        return e.code
    except AgentError as e:
        set_state(run, "error", str(e))
        return FAILED
    except Exception as e:  # a bug or a file an agent did not write: say so instead of staying "running"
        traceback.print_exc()
        set_state(run, "error", f"lỗi không lường trước: {type(e).__name__}: {e}; xem {run.path}/auto.log")
        return FAILED
    return code
