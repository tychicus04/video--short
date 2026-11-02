"""`vshort auto`: run a whole video without a Claude session steering it — fixed steps are `vshort` commands, the
judgement steps are vs-* agents called with `claude -p`. Every call's cost goes to RUN/cost.json."""
import json
import os
import subprocess
import time
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


def acquire_lock(run: Run) -> bool:
    """One `vshort auto` per run folder; the lock of a process that died is taken over."""
    lock = run.file("auto.lock")
    if lock.exists() and lock.read_text().strip().isdigit() and _alive(int(lock.read_text())):
        return False
    lock.write_text(str(os.getpid()))
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
    return OK


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
    set_state(run, "done", get_state(run)["message"])
    return code if code is not None else OK
