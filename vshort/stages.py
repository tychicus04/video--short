"""The ten stages the panel shows for a video, from state.json (what is done) and times.json (when each step ran):
which stage is where, how long it took or has been running, the time left until Tai is needed and after, and a
percent. Plain functions; vshort/queue.py and vshort/web.py hand the result to the page as it is."""
import json
import re
import statistics
from pathlib import Path

from vshort import timing

STAGES = [
    ("research", "Tìm hiểu", "Tìm nguồn đáng tin, lập notebook, viết brief"),
    ("brief", "Duyệt brief", "Bạn đọc và duyệt brief; bỏ duyệt thì agent tự kiểm"),
    ("notebooklm", "NotebookLM làm video", "Nạp brief, chờ NotebookLM dựng video tiếng Anh, tải về"),
    ("subtitles", "Lấy phụ đề", "Tách và chép đúng từng chữ phụ đề tiếng Anh"),
    ("translate", "Dịch", "Dịch sát sang tiếng Việt, chia cụm phụ đề, tự kiểm"),
    ("approve", "Duyệt bản dịch", "Máy dừng ở đây chờ bạn đọc và duyệt"),
    ("build", "Giọng đọc và hình", "Gemini đọc, hình động, ảnh tĩnh, tư liệu thật"),
    ("render", "Dựng video", "Ghép giọng, hình, phụ đề, outro"),
    ("review", "Soát và sửa", "Xem từng khung, sửa tối đa 2 vòng"),
    ("cover", "Ảnh bìa và xuất", "Tiêu đề đăng, ảnh bìa, prompt Gemini, kéo về Mac"),
]
KEYS = [k for k, _, _ in STAGES]
STEPS_OF = {
    "research": ("research",),
    "brief": ("approve_brief", "brief_check"),
    "notebooklm": ("source", "fetch", "motion_design"),
    "subtitles": ("detect", "transcribe", "text"),
    "translate": ("translate",),
    "approve": ("approve_script",),
    "build": ("plates", "motion", "motion_bind", "stills", "visuals", "visuals_agent", "tts"),
    "render": ("timeline", "render"),
    "review": (),  # review0, fix1_motion, fixed1, review1… (_REVIEW)
    "cover": ("cover",),
}
# seconds; guessed from cost.json of earlier runs and by hand, until five finished runs have times.json
DEFAULT_SECONDS = {"research": 480, "brief": 300, "notebooklm": 900, "subtitles": 180, "translate": 240, "approve": 0,
                   "build": 540, "render": 180, "review": 720, "cover": 60}
FLOOR = 60  # the least time left a running stage shows: never "0 phút" nor less than nothing
HISTORY = 5  # finished runs the typical time is the median of
# the canvas agent starts with NotebookLM and often outlives the translation: shown under NotebookLM, but neither
# counted in its time nor taken as the stage the video is at
SIDE = {"motion_design"}
_REVIEW = re.compile(r"(review|fix|fixed)\d.*")
_ROUND = re.compile(r"fix(\d+)_")
WHAT_FIX = {"motion": "hình động", "visuals": "tư liệu", "translator": "bản dịch"}
LABELS = {"brief_check": "Agent soát brief", "motion_design": "Vẽ hình động từ brief",
          "motion_bind": "Gắn hình động vào lời", "visuals_agent": "Chọn tư liệu thật", "cover": "Ảnh bìa, tiêu đề, xuất"}


def stage_of(step: str) -> str | None:
    for key, steps in STEPS_OF.items():
        if step in steps:
            return key
    return "review" if _REVIEW.fullmatch(step) else None


def _label(step: str) -> str:
    from vshort.queue import STEPS  # here: queue imports this module
    if m := re.fullmatch(r"review(\d+)", step):
        return "Soát" if m[1] == "0" else f"Soát lại sau vòng sửa {m[1]}"
    if m := re.fullmatch(r"fix(\d+)_(\w+)", step):
        return f"Sửa vòng {m[1]}: {WHAT_FIX.get(m[2], m[2])}"
    return dict(STEPS).get(step) or LABELS.get(step, step)


def _covered(spans: list[tuple[float, float]]) -> float:
    """Length of the union of the intervals: steps that ran side by side count once, a wait between two runs not at all."""
    total, reach = 0.0, float("-inf")
    for a, b in sorted(spans):
        total += max(0.0, b - max(a, reach))
        reach = max(reach, b)
    return total


def _spans(times: dict, key: str, now: float | None = None) -> list[tuple[float, float]]:
    """The stage's timed steps as intervals; an open one ends at `now`, or is left out when now is None."""
    out = []
    for step, t in times.items():
        if step in SIDE or stage_of(step) != key or "start" not in t:
            continue
        if "end" in t:
            out.append((t["start"], t["end"]))
        elif now is not None:
            out.append((t["start"], now))
    return out


def span(times: dict, key: str) -> float | None:
    """Time the stage's finished steps took (None if none has both marks). The union of their intervals, not last end
    minus first start: a rerun after an error, or a fix round redoing a step, does not count the time between."""
    spans = _spans(times, key)
    return _covered(spans) if spans else None


def typical(history: list[dict]) -> dict[str, float]:
    out = {}
    for key in KEYS:
        got = [s for t in history[:HISTORY] if (s := span(t, key)) is not None]
        out[key] = statistics.median(got) if got else DEFAULT_SECONDS[key]
    return out


def history(runs_dir: Path) -> list[dict]:
    """times.json of the last HISTORY finished runs that have one, newest first (by when auto.json was written)."""
    found = []
    for d in Path(runs_dir).iterdir() if Path(runs_dir).is_dir() else []:
        try:
            if json.loads((d / "auto.json").read_text(encoding="utf-8")).get("state") == "done" and (d / timing.FILE).exists():
                found.append(((d / "auto.json").stat().st_mtime, d))
        except (OSError, ValueError, AttributeError):  # no auto.json, not JSON, not an object
            continue
    return [timing.read(d) for _, d in sorted(found, reverse=True)[:HISTORY]]


def _needed(auto: bool) -> list[str]:
    """The steps a run always marks, in order (motion_bind, visuals_agent… only sometimes)."""
    from vshort.queue import STEPS
    steps = [s for s, _ in STEPS] + ["cover"]
    return ["brief_check" if auto and s == "approve_brief" else s for s in steps]


def _current(state: str, auto: bool, done: set[str], times: dict) -> int | None:
    if state == "wait_brief":
        return KEYS.index("brief")
    if state == "wait_script":
        return KEYS.index("approve")
    if state not in ("running", "error", "dead"):
        return None
    rounds = {m[1] for s in (*done, *times) if (m := _ROUND.match(s))}
    if any(f"fixed{r}" not in done for r in rounds):
        # a fix round reruns motion, visuals and render: the video is still at "Soát và sửa", not back at stage 7
        return KEYS.index("review")
    started = [(t["start"], s) for s, t in times.items() if "start" in t and s not in SIDE and stage_of(s)]
    if started:
        return KEYS.index(stage_of(max(started)[1]))
    # no times (a run from before times.json): the first step not done
    return KEYS.index(next((stage_of(s) for s in _needed(auto) if s not in done), "cover"))


def _steps(key: str, auto: bool, done: set[str], times: dict) -> list[dict]:
    names = [s for s in STEPS_OF[key] if s != ("approve_brief" if auto else "brief_check")] or sorted(
        {s for s in (*done, *times) if stage_of(s) == key and not s.startswith("fixed")},
        key=lambda s: (times.get(s, {}).get("start", float("inf")), s))
    return [{"step": s, "label": _label(s),
             "status": "running" if "start" in times.get(s, {}) and "end" not in times[s] else "done" if s in done else "next"}
            for s in names]


def view(state: str, auto: bool, done: set[str], times: dict, typ: dict[str, float], now: float) -> dict:
    """`state` is a Row's state (queue.status). See the plan, Task 2, for the shape."""
    n = len(STAGES)
    cur = None if state == "done" else _current(state, auto, done, times)
    if state == "done":
        status = ["done"] * n
    elif cur is None:  # queued, idle: what state.json says is done
        need = _needed(auto)
        status = ["done" if all(s in done for s in need if stage_of(s) == k) else "next" for k in KEYS]
    else:
        mode = {"wait_brief": "you", "wait_script": "you", "running": "running"}.get(state, "error")
        status = ["done"] * cur + [mode] + ["next"] * (n - cur - 1)

    seconds: list[float | None] = []
    for k, st in zip(KEYS, status):
        if st == "done":
            seconds.append(span(times, k))
        elif st == "running":
            spans = _spans(times, k, now)
            seconds.append(_covered(spans) if spans else None)
        else:
            seconds.append(None)

    def left(i: int) -> float:
        k, st, sec = KEYS[i], status[i], seconds[i]
        if st in ("done", "you"):
            return 0
        if st == "running" and sec is not None:
            # ponytail: a stage whose steps are all closed (the canvas agent still at work) sits at FLOOR until the
            # next step starts; show the side step's time here if Tai finds that confusing
            return max(typ[k] - sec, FLOOR)
        return typ[k]

    stops = {"approve"} | (set() if auto else {"brief"})
    stop = next((i for i in range(n) if KEYS[i] in stops and status[i] != "done"), None)
    if state == "done":
        eta = {"stop": None, "until_stop": None, "after_stop": None}
    elif stop is None:
        eta = {"stop": None, "until_stop": round(sum(left(i) for i in range(n))), "after_stop": None}
    else:
        eta = {"stop": STAGES[stop][1], "until_stop": round(sum(left(i) for i in range(stop))),
               "after_stop": round(sum(typ[k] for k in KEYS[stop + 1:]))}

    total = sum(typ[k] for k in KEYS)
    got = sum(typ[k] for k, st in zip(KEYS, status) if st == "done")
    if cur is not None and status[cur] == "running" and seconds[cur] is not None:
        got += min(seconds[cur], typ[KEYS[cur]])
    percent = 100 if state == "done" else min(99, max(0, round(100 * got / total))) if total else 0

    out = []
    for i, (k, label, what) in enumerate(STAGES):
        sec = seconds[i]
        out.append({"key": k, "label": label, "what": what, "status": status[i],
                    "seconds": None if sec is None else round(sec), "typical": round(typ[k]),
                    "overdue": status[i] == "running" and sec is not None and sec > typ[k],
                    "steps": _steps(k, auto, done, times) if status[i] == "running" else []})
    return {"stages": out, "current": cur, "percent": percent, "eta": eta}
