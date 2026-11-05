"""RUN/times.json: when each step started and ended, {"step": {"start": epoch, "end": epoch}}. The panel turns it into
time spent and time left (vshort/stages.py). state.json stays the record of what is done; this file is only for show,
so a broken one reads as empty and never fails a step."""
import json
import math
import os
import threading
import time
from pathlib import Path

FILE = "times.json"
# ponytail: one lock per process; two processes writing at once (an agent's `vshort` and `vshort auto`) may lose one
# mark, as with state.json. Move to fcntl.flock if marks go missing for real.
_LOCK = threading.Lock()


def read(run_dir: Path) -> dict[str, dict[str, float]]:
    """{} when the file is missing, not JSON or not an object; entries that are not {start/end: number} are left out."""
    try:
        data = json.loads((Path(run_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for step, v in data.items():
        marks = {k: v[k] for k in ("start", "end") if k in v} if isinstance(v, dict) else {}
        # finite: 1e999 parses as infinity, and one infinite time would break every page that rounds it
        if marks and all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in marks.values()):
            out[step] = marks
    return out


def _save(run_dir: Path, times: dict) -> None:
    # whole file or nothing, as Run._save
    f = Path(run_dir) / FILE
    tmp = f.with_name(f".times.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(times, indent=1), encoding="utf-8")
    tmp.replace(f)


def start(run_dir: Path, step: str, now: float | None = None) -> None:
    """The step starts (again): its old end goes. A step already open keeps its start (`vshort cover` inside the cover
    agent's step)."""
    with _LOCK:
        times = read(run_dir)
        if "start" in times.get(step, {}) and "end" not in times[step]:
            return
        times[step] = {"start": time.time() if now is None else now}
        _save(run_dir, times)


def end(run_dir: Path, step: str, now: float | None = None) -> None:
    with _LOCK:
        times = read(run_dir)
        times[step] = times.get(step, {}) | {"end": time.time() if now is None else now}
        _save(run_dir, times)


def close_open(run_dir: Path) -> None:
    """Drop the steps that started and never ended: the process doing them died. A rerun must not show them as running
    for hours."""
    with _LOCK:
        times = read(run_dir)
        kept = {s: v for s, v in times.items() if not ("start" in v and "end" not in v)}
        if kept != times:
            _save(run_dir, kept)
