"""`vshort auto`: run a whole video without a Claude session steering it — fixed steps are `vshort` commands, the
judgement steps are vs-* agents called with `claude -p`. Every call's cost goes to RUN/cost.json."""
import json
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


def total_cost(run: Run) -> float:
    return sum(r["cost_usd"] for r in run.read("cost.json")) if run.file("cost.json").exists() else 0.0
