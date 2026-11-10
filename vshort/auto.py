"""`vshort auto`: run a whole video without a Claude session steering it — fixed steps are `vshort` commands, the
judgement steps are vs-* agents called with `claude -p`. Every call's cost goes to RUN/cost.json."""
import json
import os
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vshort import script, timing
from vshort.run import Run

ROOT = Path(__file__).resolve().parent.parent  # agents run here: Sonnet session, advisor off, `model:` of the agent
CLAUDE = ["claude"]
TIMEOUT = {"vs-researcher": 1800, "vs-transcriber": 900, "vs-translator": 1200, "vs-visuals": 2400,
           "vs-reviewer": 3600, "vs-writer": 1200, "vs-scene": 2400, "vs-reviewer-neon": 3600}  # seconds
_COST = threading.Lock()  # agents may log their cost from two threads


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
    "Vertical short. Follow the source '# BRIEF (EN) – {slug}' closely: open with its title line, word for word, then its "
    "'Opening detail' line; cover its key points in order, naming the source the brief gives for each figure or claim and "
    "saying aloud what it marks as unconfirmed; end with its call to action. Walk through its 'How it works, step by step' "
    "section in order, unless it says None. Explain at concept level only; do not assert claims the brief marks as disputed."
)
RESEARCH = ("Bước 1 của /video-short.\n\n- Chủ đề: {topic}\n- slug: `{slug}`\n- RUN={run}\n\n"
            "Ghi notebook id (chỉ id, một dòng) vào {run}/notebook.txt.")
BRIEF_CHECK = (
    "RUN={run}. Chế độ tự động: Tai không duyệt brief. Soát brief ({run}/brief.vi.md và {run}/brief.en.md) với {run}/sources.md: "
    "dữ kiện, ngày, điểm tranh cãi. Soát cả mục \"Cơ chế từng bước\" theo luật an toàn: chỉ mức khái niệm, không tên lỗ hổng/"
    "kỹ thuật/công cụ, không mã hay lệnh. Mục đó mở bằng bước 0 \"Bình thường: …\" (bản Anh \"0. Normally: …\") trừ khi "
    "ghi Không có; thiếu thì thêm vào cả hai bản. \"Ý chính\" có một ý về cái giá hay giới hạn (một câu, đúng nguồn) và "
    "\"Câu chốt\" trả lời lại câu mở đầu theo nghĩa mới; thiếu thì thêm vào cả hai bản. Có mục \"Chi tiết mở màn\" (bản Anh "
    "\"Opening detail\"): một câu chi tiết thật, đúng nguồn. Mỗi con số hay cáo buộc trong \"Ý chính\" mở đầu bằng nguồn của nó, "
    "và điều chưa xác nhận được nói thành câu. Nếu {run}/sources.md có chi tiết liên quan Việt Nam thì một ý nói điều đó, "
    "không có thì không thêm. Thiếu thì thêm vào cả hai bản. Lệch thì sửa ở cả hai bản. "
    "Không tạo notebook mới, không nạp nguồn mới.")
# Kiểu neon: the same research (notebook and all, sources are still gathered there), but no English brief, and a mechanism.
RESEARCH_NEON = (
    "\n\nKiểu neon: video này không làm bằng NotebookLM nên KHÔNG viết {run}/brief.en.md. Mục \"Cơ chế từng bước\" của "
    "brief.vi.md là bắt buộc: bước 0 \"Bình thường: …\" rồi ít nhất 2 bước đánh số tiếp, mỗi bước đúng nguồn (ghi nguồn đó "
    "trong {run}/sources.md); không ghi \"Không có\". Không tìm được cơ chế có nguồn thì nói thẳng điều đó trong brief "
    "(run sẽ dừng ở bước duyệt brief cho Tai quyết), đừng bịa bước cho đủ. Video chỉ 60–70 giây, nên \"Cơ chế từng bước\" "
    "tối đa 4 bước sau bước 0 và \"Ý chính\" tối đa 3 ý, kể cả ý cái giá. Notebook và {run}/notebook.txt vẫn làm như trên.")
BRIEF_CHECK_NEON = (
    "RUN={run}. Chế độ tự động: Tai không duyệt brief. Soát brief ({run}/brief.vi.md) với {run}/sources.md: dữ kiện, ngày, "
    "điểm tranh cãi. Soát mục \"Cơ chế từng bước\" theo luật an toàn: "
    "chỉ mức khái niệm, không tên lỗ hổng/kỹ thuật/công cụ, không mã hay lệnh. Mục đó bắt buộc, mở bằng bước 0 \"Bình "
    "thường: …\" rồi ít nhất 2 bước đánh số, mỗi bước đúng nguồn; thiếu thì thêm nếu {run}/sources.md đủ để viết, không "
    "đủ thì ghi thẳng vào brief rằng không có cơ chế có nguồn (đừng bịa). \"Ý chính\" có một ý về cái giá hay giới hạn (một "
    "câu, đúng nguồn) và \"Câu chốt\" trả lời lại câu mở đầu theo nghĩa mới; thiếu thì thêm. Có mục \"Chi tiết mở màn\": "
    "một câu chi tiết thật, đúng nguồn. Mỗi con số hay cáo buộc trong \"Ý chính\" mở đầu bằng nguồn của nó, và điều chưa "
    "xác nhận được nói thành câu. Nếu {run}/sources.md có chi tiết liên quan Việt Nam thì một ý nói điều đó, không có thì "
    "không thêm. Lệch thì sửa. Không tạo notebook mới, không nạp nguồn mới.")
WRITE = ("RUN={run}\n\nViết lời tiếng Việt thẳng từ {run}/brief.vi.md (Tai đã duyệt) và {run}/sources.md, ghi "
         "{run}/script.vi.json, rồi chạy `vshort check {run}` tới khi mã 0.")
TRANSCRIBE = ("RUN={run}. Đọc các ảnh mảnh phụ đề {sheets} ({n} mảnh, chỉ số 0–{last}, theo {run}/fragments.json) "
              "và ghi {run}/fragments_text.json.")
TRANSLATE = "RUN={run}\n\nĐầu ra nguyên văn của `vshort text`:\n\n```\n{table}\n```"
VISUALS = ("RUN={run}\n\nĐọc {run}/brief.vi.md (mục \"Lưu ý độ chính xác\") và {run}/script.vi.json; chỉ vá chữ sai dữ kiện, "
           "không có gì sai thì ghi [].")
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
SCENE = ("RUN={run}\n\nViết {run}/scene.json cho video này: đọc {run}/brief.vi.md (mục \"Cơ chế từng bước\" và \"Lưu ý độ chính "
         "xác\") và {run}/script.vi.json, chạy `vshort scene {run} --table` lấy số cụm, rồi `vshort scene {run}` tới khi mã 0.")
REVIEW_NEON = ("RUN={run}. final.mp4 đã render (kiểu neon). Soát video cuối; ghi {run}/review.md và {run}/review.json, "
               "mỗi lỗi nặng kèm cách sửa cụ thể trong `fix`.")
RECHECK = ("Soát lại: chỉ các phần đã sửa.\n\nRUN={run}. review.md cũ: {run}/review.md. Đã sửa (lỗi, agent, câu, thời điểm):\n"
           "{fixed}\nGhi kết quả vào cuối review.md và ghi lại review.json cho lần soát này.")
RECHECK_ALL = ("Soát lại: lời đã đổi nên giọng, hình và mọi mốc giờ đều dựng lại — soát cả video như lần đầu.\n\nRUN={run}. "
               "review.md cũ: {run}/review.md. Đã sửa (lỗi, agent, câu, thời điểm):\n{fixed}\n"
               "Ghi kết quả vào cuối review.md và ghi lại review.json cho lần soát này.")
FIX = ("RUN={run}\n\nSửa theo {run}/review.json, các lỗi agent={agent}:\n{items}\n{how}")
FIX_HOW = {
    "visuals": "Sửa visuals.json rồi tự chạy `vshort visuals` tới khi mã 0.",
    "translator": ("Ghi bản sửa vào {run}/script.proposed.json (cùng dạng script.vi.json, sửa cả `note`); "
                   "KHÔNG sửa script.vi.json — Tai duyệt bản đề xuất trước."),
}
FIX_HOW_NEON = {
    "scene": ("Chỉ sửa {run}/scene.json ở chỗ các lỗi nêu, làm theo `fix` của từng lỗi, rồi tự chạy `vshort scene {run}` "
              "tới khi mã 0."),
    "writer": ("Ghi bản sửa vào {run}/script.proposed.json (cùng dạng script.vi.json, sửa cả `note`); "
               "KHÔNG sửa script.vi.json — Tai duyệt bản đề xuất trước."),
}
MAX_ROUNDS = 2
BUDGET = {"old": 5.0, "neon": 30.0}  # dollars a video may cost, by style: the neon flow pays for a planner and an Opus reviewer (Ruling 33)
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


def _research(run: Run, extra: str = "") -> dict:
    """The researcher's step, after a NotebookLM login check; run.json as it is once the notebook id is in it."""
    from vshort.cli import FAILED
    meta, p = run.read("run.json"), run.path
    if not run.done("research"):
        # Fail before the researcher agent is paid for, not at the first NotebookLM call after it.
        # ponytail: this command once hung for over 2 minutes on the Mac; if it hangs on the server, add a timeout to run_notebooklm.
        if code := notebooklm(["auth", "check", "--test"]):
            from vshort.cli import AUTH, RELOGIN
            raise Stop(code, RELOGIN if code == AUTH else "Không kiểm được phiên NotebookLM; xem auto.log")
        run_claude(run, "research", "vs-researcher",
                   (RESEARCH + extra).format(topic=meta["topic"], slug=meta["slug"], run=p), TIMEOUT["vs-researcher"])
        nb = run.file("notebook.txt").read_text().strip() if run.file("notebook.txt").exists() else ""
        if not nb:
            raise Stop(FAILED, f"researcher không ghi notebook id vào {p}/notebook.txt")
        run.write("run.json", meta | {"notebook_id": nb})
        run.mark("research")
    return run.read("run.json")


def _brief_stop(run: Run, check: str, message: str) -> None:
    """Auto mode: an agent checks the brief. Otherwise stop until Tai has approved it."""
    from vshort.cli import WAIT_BRIEF
    if run.read("run.json").get("auto"):
        _agent(run, "brief_check", "vs-researcher", check.format(run=run.path))
    elif not run.done("approve_brief"):
        raise Stop(WAIT_BRIEF, message, "wait_brief")


def _flow(run: Run) -> int:
    from vshort.cli import FAILED, OK, WAIT_SCRIPT, style_of
    if style_of(run) == "neon":
        return _flow_neon(run)
    p = run.path
    meta = _research(run)
    _brief_stop(run, BRIEF_CHECK, f"Duyệt brief: {p}/brief.vi.md (sửa thì sửa cả brief.en.md), rồi "
                                  f"`vshort approve {p} brief` và `vshort auto {p}`.")
    if not run.done("source"):
        timing.start(run.path, "source")
        if code := notebooklm(["source", "add", "-n", meta["notebook_id"], "--type", "text", "--title",
                               f"# BRIEF (EN) – {meta['slug']}", run.file("brief.en.md").read_text()]):
            from vshort.cli import AUTH, RELOGIN
            raise Stop(code, RELOGIN if code == AUTH else "NotebookLM không nạp được brief tiếng Anh; xem auto.log")
        run.mark("source")
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
    if not run.done("approve_script"):
        run.file("translation.md").write_text(_translation_md(run), encoding="utf-8")
        raise Stop(WAIT_SCRIPT, f"Duyệt bản dịch: {p}/translation.md (sửa thì sửa {p}/script.vi.json), rồi "
                                f"`vshort approve {p} script` và `vshort auto {p}`.", "wait_script")
    _build(run)
    _review(run)
    return OK


def script_md(run: Run) -> str:
    """loi.md, what Tai approves in the neon style: a row per sentence (what is said, syllables, the seconds they take at
    the pace of the voice, the writer's note) and the total with the length of the video, what Tai checks."""
    rows = ["| id | lời | âm tiết | giây ước tính | note |", "|---|---|---|---|---|"]
    total, lines = 0, run.read("script.vi.json")
    for r in lines:
        n = script.syllables(r["phrases"])
        total += n
        secs = f"{n / script.NEON_PACE:.1f}".replace(".", ",")
        rows.append(f"| {r['id']} | {' '.join(r['phrases'].replace('|', ' ').split())} | {n} | {secs} | {r.get('note', '')} |")
    secs = script.video_secs(lines)
    end = f"Tổng: {total} âm tiết; video ~{secs:.0f} giây, kể cả nghỉ giữa câu và outro (cần {script.VIDEO_MIN}–{script.VIDEO_MAX})"
    return "\n".join(rows + ["", end]) + "\n"


def _no_mechanism(run: Run) -> bool:
    """The brief lacks the steps the diagram is drawn from: step 0, "Bình thường", and two more."""
    steps = script.mechanism_steps(run.file("brief.vi.md").read_text(encoding="utf-8"))
    return len(steps) < 3 or not steps[0].startswith("0.")


def _flow_neon(run: Run) -> int:
    """The neon style: no NotebookLM video. The brief, then `vs-writer` writes the narration from it, Tai approves it,
    then the voice; then the picture: `vs-scene` plans the diagram, `vshort scene` checks it, `vshort render` makes the
    video, `vs-reviewer-neon` looks at its frames (≤ MAX_ROUNDS fix rounds)."""
    from vshort.cli import FAILED, OK, WAIT_BRIEF, WAIT_SCRIPT
    p = run.path
    _research(run, RESEARCH_NEON)
    lack = f"Brief chưa có cơ chế từng bước (cần bước 0 và ít nhất 2 bước có nguồn) — sửa {p}/brief.vi.md"
    # a brief that already fails the gate says so at the first stop too: Tai should not approve it, then be stopped again
    _brief_stop(run, BRIEF_CHECK_NEON, (f"{lack} trước khi duyệt. " if _no_mechanism(run) else "")
                + f"Duyệt brief: {p}/brief.vi.md, rồi `vshort approve {p} brief` và `vshort auto {p}`.")
    if _no_mechanism(run):
        raise Stop(WAIT_BRIEF, f"{lack}, rồi `vshort auto {p}`.", "wait_brief")
    if not run.done("write"):
        run_claude(run, "write", "vs-writer", WRITE.format(run=p), TIMEOUT["vs-writer"])
        if code := run_vshort(["check", str(p)]):
            raise Stop(FAILED, f"lời chưa qua `vshort check` (mã {code}); xem auto.log")
        run.mark("write")
    if not run.done("approve_script"):
        run.file("loi.md").write_text(script_md(run), encoding="utf-8")
        raise Stop(WAIT_SCRIPT, f"Duyệt lời: {p}/loi.md (sửa thì sửa {p}/script.vi.json), rồi "
                                f"`vshort approve {p} script` và `vshort auto {p}`.", "wait_script")
    if not run.done("tts"):
        _tts_result(run, run_vshort(["tts", str(p)]))
    _timeline(run)
    if not _fixing(run):  # else `_review` finishes the round's fixes first: they unmarked scene and render on purpose
        _scene(run)
        _render(run)
    _review(run)
    return OK


def _neon(run: Run) -> bool:
    from vshort.cli import style_of
    return style_of(run) == "neon"


def _fixing(run: Run) -> bool:
    """A fix round was begun and not finished (the process died in it, or `vshort scene` refused the fix)."""
    r = get_state(run)["round"]
    return bool(r) and not run.done(f"fixed{r}")


def _scene_check(run: Run) -> None:
    """`vshort scene` has to pass (it marks `scene` itself): the render is drawn from its scene.resolved.json."""
    if code := run_vshort(["scene", str(run.path)]):
        raise Stop(FAILED_CODE, f"kịch bản hình chưa qua `vshort scene` (mã {code}); xem auto.log")


def _scene(run: Run) -> None:
    if not run.done("scene"):
        run.unmark("render")  # a diagram made again is rendered again (`vshort scene` unmarks `render` itself; this covers a run left with `render` marked and no `scene`)
        run_claude(run, "scene", "vs-scene", SCENE.format(run=run.path), TIMEOUT["vs-scene"])
        _scene_check(run)


def read_review(run: Run, kinds: tuple[str, ...] = ("visuals", "translator", "none")) -> dict:
    """RUN/review.json as the reviewer wrote it: {"verdict": "Đạt"|"Cần sửa", "findings": [{agent, ids, at, what, fix}]}; `agent`
    is one of `kinds`, `fix` (how to fix it) a string if there is one."""
    try:
        rev = run.read("review.json")
        assert rev["verdict"] in ("Đạt", "Cần sửa") and isinstance(rev["findings"], list)
        for f in rev["findings"]:
            assert f["agent"] in kinds
            assert isinstance(f["what"], str) and isinstance(f.get("ids", []), list)
            assert f.get("fix") is None or isinstance(f["fix"], str)
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        raise AgentError(f"review.json không đọc được (thiếu hoặc sai dạng) — xem {run.path}/review.md") from None
    return rev


def _items(fs: list[dict]) -> str:
    return "\n".join(f"- {f['agent']}, câu {', '.join(map(str, f.get('ids', [])))}, {f.get('at', '')}: {f['what']}"
                     + (f" — sửa: {f['fix']}" if f.get("fix") else "") for f in fs)


def _fix(run: Run, r: int, todo: list[dict]) -> None:
    """Round r's fixes; each agent step is marked, so a run that died midway redoes only what is left."""
    if _neon(run):
        return _fix_neon(run, r, todo)
    from vshort.cli import WAIT_SCRIPT
    p = run.path
    by = {a: [f for f in todo if f["agent"] == a] for a in ("visuals", "translator")}
    if by["visuals"]:
        _visuals(run, FIX.format(run=p, agent="visuals", items=_items(by["visuals"]), how=FIX_HOW["visuals"]),
                 step=f"fix{r}_visuals")
        run.unmark("render")
    if by["translator"]:
        if not run.done(f"fix{r}_translator"):
            run_claude(run, f"fix{r}_translator", "vs-translator",
                       FIX.format(run=p, agent="translator", items=_items(by["translator"]),
                                  how=FIX_HOW["translator"].format(run=p)), TIMEOUT["vs-translator"])
            if not run.file("script.proposed.json").exists():
                raise AgentError("vs-translator không ghi script.proposed.json khi sửa theo review")
            run.mark(f"fix{r}_translator")
        # the voice, stills (a line may no longer be empty) and visuals all follow the words
        run.unmark("approve_script", "tts", "timeline", "render", "stills", "visuals")
        run.mark(f"fixed{r}")  # what is left (read the voice again, render) happens once Tai approves
        raise Stop(WAIT_SCRIPT, _proposal(run), "wait_script")
    _render(run)
    run.mark(f"fixed{r}")


def _fix_neon(run: Run, r: int, todo: list[dict]) -> None:
    """Round r's fixes of a neon run: the scene first (the agent, then `vshort scene` must pass, then the render), the words last
    (a proposal for Tai: the voice, the scene and the render all follow them)."""
    from vshort.cli import WAIT_SCRIPT
    p = run.path
    by = {a: [f for f in todo if f["agent"] == a] for a in ("scene", "writer")}
    if by["scene"] and not run.done(f"fix{r}_scene"):  # marked only once `vshort scene` passes: until then a rerun asks again
        run_claude(run, f"fix{r}_scene", "vs-scene",
                   FIX.format(run=p, agent="scene", items=_items(by["scene"]), how=FIX_HOW_NEON["scene"].format(run=p)),
                   TIMEOUT["vs-scene"])
        run.unmark("scene", "render")
        _scene_check(run)
        run.mark(f"fix{r}_scene")
    if by["writer"]:
        if not run.done(f"fix{r}_writer"):
            run.file("script.proposed.json").unlink(missing_ok=True)  # an old proposal is not this round's
            run_claude(run, f"fix{r}_writer", "vs-writer",
                       FIX.format(run=p, agent="writer", items=_items(by["writer"]), how=FIX_HOW_NEON["writer"].format(run=p)),
                       TIMEOUT["vs-writer"])
            if not run.file("script.proposed.json").exists():
                raise AgentError("vs-writer không ghi script.proposed.json khi sửa theo review")
            run.mark(f"fix{r}_writer")
        run.unmark("approve_script", "tts", "timeline", "scene", "render")
        run.mark(f"fixed{r}")  # what is left (the voice, the scene, the render) happens once Tai approves
        raise Stop(WAIT_SCRIPT, _proposal(run), "wait_script")
    _render(run)
    run.mark(f"fixed{r}")


def _review(run: Run) -> None:
    """Review; while it finds what an agent can fix, fix it and have a fresh reviewer check the fix (≤ MAX_ROUNDS)."""
    p = run.path
    neon = _neon(run)
    agent, kinds = ("vs-reviewer-neon", ("scene", "writer", "none")) if neon else ("vs-reviewer", ("visuals", "translator", "none"))
    while True:
        r = get_state(run)["round"]
        if _fixing(run):  # died during round r's fixes: finish them first
            _fix(run, r, run.read(f"fix{r}.json"))
        if not run.done(f"review{r}"):
            fixed = run.read(f"fix{r}.json") if r else []
            recheck = RECHECK_ALL if neon and any(f["agent"] == "writer" for f in fixed) else RECHECK  # the words changed: all redone
            prompt = (REVIEW_NEON if neon else REVIEW).format(run=p) if r == 0 else recheck.format(run=p, fixed=_items(fixed))
            run.file("review.json").unlink(missing_ok=True)  # never act on the previous reviewer's findings
            run_claude(run, f"review{r}", agent, prompt, TIMEOUT[agent])
            read_review(run, kinds)  # a bad file is not marked done: a rerun asks a reviewer again
            run.mark(f"review{r}")
        rev = read_review(run, kinds)
        todo = [f for f in rev["findings"] if f["agent"] != "none"]
        if rev["verdict"] == "Đạt" or not todo or r >= MAX_ROUNDS:
            _finish(run, rev, r)
            return
        run.write(f"fix{r + 1}.json", todo)  # before the round number moves: a resume finds what to fix
        set_state(run, "running", round=r + 1)


def _proposal(run: Run) -> str:
    old = {r["id"]: r for r in run.read("script.vi.json")}
    lines = [f"Reviewer thấy lỗi ở {'lời' if _neon(run) else 'bản dịch'}; bản sửa đề xuất: {run.path}/script.proposed.json"]
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
    neon = _neon(run)  # no retiming, no patched pictures: the picture is drawn from scene.json
    if not neon:
        out.append(_retime_note(run))
    elif run.file("timeline.json").exists():  # the length Tai's rule is about: the voice as it was read, and the outro
        secs = run.read("timeline.json")["total"] + script.OUTRO
        out.append(f"Độ dài: {secs:.1f} s".replace(".", ",")
                   + ("" if script.VIDEO_MIN <= secs <= script.VIDEO_MAX else
                      f" — ngoài {script.VIDEO_MIN}–{script.VIDEO_MAX} s dù giọng đã chỉnh hết mức; rút hoặc thêm lời rồi duyệt lại"))
    fx =run.read("sfx.json") if run.file("sfx.json").exists() else []
    out.append("Hiệu ứng âm thanh: " + (", ".join(f"{c['name']} {c['at']:.1f} s" for c in fx) or "không có"))
    for v in run.read("visuals.json") if not neon and run.file("visuals.json").exists() else []:
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
    budget = BUDGET["neon" if neon else "old"]
    if total > budget:
        out.append(f"Vượt ngân sách ${budget:.0f}.")
    set_state(run, "done", "\n".join(out))


def _retime_note(run: Run) -> str:
    """The final message's line on the retiming: lines whose picture stands still over 2 s, or lose a tail over 0.5 s."""
    try:
        ps = run.read("pieces.json")
    except (OSError, ValueError):
        return "Co giãn: chưa có pieces.json"
    bits = [f"câu {p['id']} giữ {p['hold']:.1f} s".replace(".", ",") for p in ps if p["hold"] > 2]
    bits += [f"câu {p['id']} bỏ đuôi {p['dropped']:.1f} s".replace(".", ",") for p in ps if p["dropped"] > 0.5]
    return "Co giãn: " + ("; ".join(bits) if bits else "không câu nào phải giữ hay bỏ đuôi")


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


def _tts_result(run: Run, code: int) -> None:
    from vshort.cli import QUOTA
    if code == QUOTA:
        raise Stop(code, "Hết hạn mức Gemini TTS trong ngày và ZeroTTS không chạy được; xem auto.log")
    if code:
        raise Stop(code, f"`vshort tts` lỗi (mã {code}); xem auto.log")


def _timeline(run: Run) -> None:
    p = str(run.path)
    if not run.done("timeline"):
        if run_vshort(["timeline", p]) == 2:  # the voice was made from another script
            run.unmark("tts")
            if _neon(run):  # the diagram is timed to the old voice
                run.unmark("scene", "render")
            _tts_result(run, run_vshort(["tts", p]))
            _vs(run, "timeline")


def _render(run: Run) -> None:
    if not run.done("render") and (code := run_vshort(["render", str(run.path)])):
        raise Stop(code, f"`vshort render {run.path}` lỗi (mã {code}); xem auto.log")


def _build(run: Run) -> None:
    p = str(run.path)
    with ThreadPoolExecutor(1) as ex:  # the voice is read while the pictures are made
        tts = None if run.done("tts") else ex.submit(run_vshort, ["tts", p])
        if not run.done("clean"):
            run.unmark("stills", "visuals", "render")  # a run from before 06/11/2026: its stills came from the old plates
            _vs(run, "clean")
        _vs(run, "stills")
        if not run.done("visuals"):
            _visuals(run, VISUALS.format(run=p))
        if tts:
            _tts_result(run, tts.result())
    _timeline(run)
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
