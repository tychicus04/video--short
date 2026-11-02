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
