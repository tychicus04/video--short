"""`vshort auto`: run a whole video without a Claude session steering it — fixed steps are `vshort` commands, the
judgement steps are vs-* agents called with `claude -p`. Every call's cost goes to RUN/cost.json."""
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vshort.run import Run

ROOT = Path(__file__).resolve().parent.parent  # agents run here: Sonnet session, advisor off, `model:` of the agent
CLAUDE = ["claude"]
TIMEOUT = {"vs-researcher": 1800, "vs-transcriber": 900, "vs-translator": 1200, "vs-motion": 2400, "vs-visuals": 2400,
           "vs-reviewer": 3600}  # seconds


class AgentError(Exception):
    pass


def _log_cost(run: Run, step: str, agent: str, seconds: float, out: dict, ok: bool) -> None:
    rows = run.read("cost.json") if run.file("cost.json").exists() else []
    rows.append({"step": step, "agent": agent, "seconds": round(seconds), "cost_usd": out.get("total_cost_usd") or 0,
                 "models": list(out.get("modelUsage") or {}), "ok": ok})
    run.write("cost.json", rows)


def run_claude(run: Run, step: str, agent: str, prompt: str, timeout: int) -> str:
    """Run one agent headless; its reply text. AgentError (reason in Vietnamese) when it fails or overruns."""
    t = time.monotonic()
    try:
        cp = subprocess.run([*CLAUDE, "-p", "--agent", agent, "--output-format", "json", prompt], cwd=ROOT,
                            capture_output=True, text=True, timeout=timeout)
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


def set_state(run: Run, state: str, message: str = "", round: int | None = None) -> None:
    old = get_state(run)
    run.write("auto.json", {"state": state, "message": message, "round": old["round"] if round is None else round,
                            "pid": os.getpid()})


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # someone else's process: alive
        return True
    return True


def locked_by(run: Run) -> int | None:
    """The pid of the live `vshort auto` working on this run, if any (a dead one's lock doesn't count)."""
    lock = run.file("auto.lock")
    pid = lock.read_text().strip() if lock.exists() else ""
    return int(pid) if pid.isdigit() and _alive(int(pid)) else None


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
MOTION = ("RUN={run}\n\nĐọc {run}/brief.vi.md (mục \"Cơ chế từng bước\" và \"Lưu ý độ chính xác\") và {run}/script.vi.json "
          "trước khi chọn đoạn câu.")
VISUALS = ("RUN={run}\n\nĐọc {run}/motion.json để biết câu nào đã có hình động (đừng chọn tư liệu cho các câu đó), "
           "{run}/sources.md (nguồn tư liệu thật) và {run}/brief.vi.md (mục \"Lưu ý độ chính xác\") khi vá chữ.")
REVIEW = "RUN={run}. final.mp4 đã render. Soát video cuối; ghi {run}/review.md và {run}/review.json."
RECHECK = ("Soát lại: chỉ các phần đã sửa.\n\nRUN={run}. review.md cũ: {run}/review.md. Đã sửa (lỗi, agent, câu, thời điểm):\n"
           "{fixed}\nGhi kết quả vào cuối review.md và ghi lại review.json cho lần soát này.")
FIX = ("RUN={run}\n\nSửa theo {run}/review.json, các lỗi agent={agent}:\n{items}\n{how}")
FIX_HOW = {
    "motion": "Sửa motion.json rồi tự chạy `vshort motion` tới khi mã 0.",
    "visuals": "Sửa visuals.json rồi tự chạy `vshort visuals` tới khi mã 0.",
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
    from vshort import cli
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


def read_review(run: Run) -> dict:
    """RUN/review.json as the reviewer wrote it: {"verdict": "Đạt"|"Cần sửa", "findings": [{agent, ids, at, what}]}."""
    try:
        rev = run.read("review.json")
        assert rev["verdict"] in ("Đạt", "Cần sửa") and isinstance(rev["findings"], list)
        assert all(f["agent"] in ("motion", "visuals", "translator", "none") for f in rev["findings"])
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        raise AgentError(f"review.json không đọc được (thiếu hoặc sai dạng) — xem {run.path}/review.md") from None
    return rev


def _items(fs: list[dict]) -> str:
    return "\n".join(f"- {f['agent']}, câu {', '.join(map(str, f.get('ids', [])))}, {f.get('at', '')}: {f['what']}"
                      for f in fs)


def _review(run: Run) -> None:
    """Review; while it finds what an agent can fix, fix it and have a fresh reviewer check the fix (≤ MAX_ROUNDS)."""
    from vshort.cli import WAIT_SCRIPT
    p = run.path
    while True:
        r = get_state(run)["round"]
        if not run.done(f"review{r}"):
            prompt = REVIEW.format(run=p) if r == 0 else RECHECK.format(run=p, fixed=run.file(f"fix{r}.txt").read_text())
            run.file("review.json").unlink(missing_ok=True)  # never act on the previous reviewer's findings
            run_claude(run, f"review{r}", "vs-reviewer", prompt, TIMEOUT["vs-reviewer"])
            run.mark(f"review{r}")
        rev = read_review(run)
        todo = [f for f in rev["findings"] if f["agent"] != "none"]
        if rev["verdict"] == "Đạt" or not todo or r >= MAX_ROUNDS:
            _finish(run, rev, r)
            return
        r += 1
        set_state(run, "running", round=r)
        run.file(f"fix{r}.txt").write_text(_items(todo) + "\n", encoding="utf-8")
        by = {a: [f for f in todo if f["agent"] == a] for a in ("motion", "visuals", "translator")}
        for agent in ("motion", "visuals"):
            if by[agent]:
                prompt = FIX.format(run=p, agent=agent, items=_items(by[agent]), how=FIX_HOW[agent])
                (_motion if agent == "motion" else _visuals)(run, prompt, step=f"fix{r}_{agent}")
                run.unmark("render")
        if by["translator"] and not run.done(f"fix{r}_translator"):
            run_claude(run, f"fix{r}_translator", "vs-translator",
                       FIX.format(run=p, agent="translator", items=_items(by["translator"]),
                                  how=FIX_HOW["translator"].format(run=p)), TIMEOUT["vs-translator"])
            if not run.file("script.proposed.json").exists():
                raise AgentError("vs-translator không ghi script.proposed.json khi sửa theo review")
            run.mark(f"fix{r}_translator")
            run.unmark("approve_script", "tts", "timeline", "render", "motion")
            raise Stop(WAIT_SCRIPT, _proposal(run), "wait_script")
        _render(run)


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


def _finish(run: Run, rev: dict, rounds: int) -> None:
    p, slug = run.path, run.path.name
    out = [f"Video: {p}/final.mp4",
           f"Chép về Mac (gõ trong terminal Mac): scp tai@pve2:~/notebooklm-videos/{slug}/final.mp4 ~/Downloads/{slug}.mp4",
           f"Giọng: {_voice(run)}"]
    if run.file("motion.json").exists():
        out.append("Hình động: câu " + ", ".join(map(str, run.read("motion.json").get("lines", []))))
    else:
        out.append("Hình động: không có" + (" (motion.json không qua kiểm, xem motion.loi.json)"
                                             if run.file("motion.loi.json").exists() else ""))
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


def _no_motion(run: Run) -> None:
    """motion.json failed its check: keep it as motion.loi.json and go on with stills only."""
    if run.file("motion.json").exists():
        run.file("motion.json").replace(run.file("motion.loi.json"))
    if code := run_vshort(["motion", str(run.path)]):
        raise Stop(code, f"`vshort motion` lỗi cả khi không có hình động (mã {code}); xem auto.log")


def _motion(run: Run, prompt: str, step: str = "motion_agent") -> None:
    if not run.done(step):
        run_claude(run, step, "vs-motion", prompt, TIMEOUT["vs-motion"])
        run.mark(step)
    if run_vshort(["motion", str(run.path)]):  # don't take the agent's word for it
        _no_motion(run)


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


def _render(run: Run) -> None:
    if not run.done("render"):
        if run_vshort(["render", str(run.path)]) == 2:  # usually: motion.json no longer matches
            _no_motion(run)
            _vs(run, "render")


def _build(run: Run) -> None:
    p = str(run.path)
    with ThreadPoolExecutor(1) as ex:  # the voice is read while the pictures are made
        tts = None if run.done("tts") else ex.submit(run_vshort, ["tts", p])
        _vs(run, "plates")
        if not run.done("motion"):
            _motion(run, MOTION.format(run=p))
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
    _render(run)


def run_auto(run: Run) -> int:
    """Run from the first unfinished step to the next stop; auto.json always says where it ended."""
    from vshort.cli import FAILED, OK
    set_state(run, "running")
    try:
        code = _flow(run)
    except Stop as e:
        set_state(run, e.state, e.message)
        return e.code
    except AgentError as e:
        set_state(run, "error", str(e))
        return FAILED
    return code
