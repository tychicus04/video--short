"""The stages the panel shows for a video (ten in the NotebookLM flow, nine in the neon one: FLOWS), from state.json (what
is done) and times.json (when each step ran): which stage is where, how long it took or has been running, the time left
until Tai is needed and after, and a percent. Plain functions; vshort/queue.py and vshort/web.py hand the result to the
page as it is. `style` is "old" or "neon" (run.json's "style"; style_of)."""
import json
import re
import statistics
from pathlib import Path
from typing import NamedTuple

from vshort import timing

STAGES = [
    ("research", "Tìm hiểu", "Tìm nguồn đáng tin, lập notebook, viết brief"),
    ("brief", "Duyệt brief", "Bạn đọc và duyệt brief; bỏ duyệt thì agent tự kiểm"),
    ("notebooklm", "NotebookLM làm video", "Nạp brief, chờ NotebookLM dựng video tiếng Anh, tải về"),
    ("subtitles", "Lấy phụ đề", "Tách và chép đúng từng chữ phụ đề tiếng Anh"),
    ("translate", "Dịch", "Dịch sát sang tiếng Việt, chia cụm phụ đề, tự kiểm"),
    ("approve", "Duyệt bản dịch", "Máy dừng ở đây chờ bạn đọc và duyệt"),
    ("build", "Giọng đọc và hình", "Gemini đọc, xóa phụ đề Anh từng khung, vá chữ sai"),
    ("render", "Dựng video", "Co giãn video gốc theo lời, ghép giọng, phụ đề, outro"),
    ("review", "Soát và sửa", "Xem từng khung, sửa tối đa 2 vòng"),
    ("cover", "Ảnh bìa và xuất", "Tiêu đề đăng, ảnh bìa, prompt Gemini, kéo về Mac"),
]
STEPS_OF = {
    "research": ("research",),
    "brief": ("approve_brief", "brief_check"),
    "notebooklm": ("source", "fetch"),
    "subtitles": ("detect", "transcribe", "text"),
    "translate": ("translate",),
    "approve": ("approve_script",),
    "build": ("clean", "stills", "visuals", "visuals_agent", "tts"),
    "render": ("timeline", "render"),
    "review": (),  # review0, fix1_visuals, fixed1, review1… (_REVIEW)
    "cover": ("cover",),
}
# seconds; guessed from cost.json of earlier runs and by hand, until five finished runs have times.json
DEFAULT_SECONDS = {"research": 480, "brief": 300, "notebooklm": 900, "subtitles": 180, "translate": 240, "approve": 0,
                   "build": 540, "render": 120, "review": 720, "cover": 60}  # render: one ffmpeg run since 06/11
# The neon style: no NotebookLM, so the voice comes right after the approved narration, then the picture is drawn in code.
# Steps (auto._flow_neon): research, fact_check, brief_check | approve_brief, write, approve_script, tts, timeline, scene, render, then
# review<r>, fix<r>_scene | fix<r>_writer, fixed<r>, and cover.
STAGES_NEON = [("research", "Tìm hiểu", "Tìm nguồn đáng tin, lập notebook, viết brief, rồi một agent khác soát dữ kiện với nguồn"),
               ("brief", "Duyệt brief", "Bạn đọc và duyệt brief; bỏ duyệt thì agent tự kiểm"),
               ("write", "Viết lời", "Claude viết lời Việt từ brief, chia cụm phụ đề, tự kiểm"),
               ("approve", "Duyệt lời", "Máy dừng ở đây chờ bạn đọc và duyệt"),
               ("voice", "Giọng đọc", "Gemini đọc (hết lượt thì ZeroTTS), nối các câu"),
               ("scene", "Kịch bản hình", "Claude dựng sơ đồ neon theo lời, code xếp chỗ và kiểm"),
               ("render", "Dựng video", "Vẽ sơ đồ thành video, ghép giọng, tiếng hiệu ứng, outro"),
               ("review", "Soát và sửa", "Xem từng khung, sửa tối đa 2 vòng"),
               ("cover", "Ảnh bìa và xuất", "Tiêu đề đăng, ảnh bìa, prompt Gemini, kéo về Mac")]
STEPS_OF_NEON = {"research": ("research", "fact_check"), "brief": ("approve_brief", "brief_check"), "write": ("write",),
                 "approve": ("approve_script",), "voice": ("tts", "timeline"), "scene": ("scene",), "render": ("render",),
                 "review": (), "cover": ("cover",)}
# seconds, guessed like the old ones until five neon runs have times.json; scene is Claude's long turn, render HyperFrames' (hf.render's 600 s)
DEFAULT_SECONDS_NEON = {"research": 780, "brief": 300, "write": 240, "approve": 0, "voice": 150, "scene": 900, "render": 600,
                        "review": 900, "cover": 60}


class Flow(NamedTuple):
    stages: list[tuple[str, str, str]]
    steps_of: dict[str, tuple[str, ...]]
    default_seconds: dict[str, float]


FLOWS = {"old": Flow(STAGES, STEPS_OF, DEFAULT_SECONDS), "neon": Flow(STAGES_NEON, STEPS_OF_NEON, DEFAULT_SECONDS_NEON)}
FLOOR = 60  # the least time left a running stage shows: never "0 phút" nor less than nothing
HISTORY = 5  # finished runs the typical time is the median of
_REVIEW = re.compile(r"(review|fix|fixed)\d.*")
_ROUND = re.compile(r"fix(\d+)_")
WHAT_FIX = {"visuals": "chữ sai", "translator": "bản dịch", "scene": "kịch bản hình", "writer": "lời"}
LABELS = {"fact_check": "Soát dữ kiện với nguồn", "brief_check": "Agent soát brief", "visuals_agent": "Soát chữ sai trong hình", "cover": "Ảnh bìa, tiêu đề, xuất"}


def style_of(meta) -> str:
    """"neon" or "old" from a run.json already read (cli.style_of reads it from the Run, but cli is too heavy to import here)."""
    return "neon" if isinstance(meta, dict) and meta.get("style") == "neon" else "old"


def _keys(style: str) -> list[str]:
    return [k for k, _, _ in FLOWS[style].stages]


def stage_of(step: str, style: str = "old") -> str | None:
    for key, steps in FLOWS[style].steps_of.items():
        if step in steps:
            return key
    return "review" if _REVIEW.fullmatch(step) else None


def _label(step: str, style: str = "old") -> str:
    from vshort.queue import FLOW_STEPS  # here: queue imports this module
    if m := re.fullmatch(r"review(\d+)", step):
        return "Soát" if m[1] == "0" else f"Soát lại sau vòng sửa {m[1]}"
    if m := re.fullmatch(r"fix(\d+)_(\w+)", step):
        return f"Sửa vòng {m[1]}: {WHAT_FIX.get(m[2], m[2])}"
    return dict(FLOW_STEPS[style]).get(step) or LABELS.get(step, step)


def _covered(spans: list[tuple[float, float]]) -> float:
    """Length of the union of the intervals: steps that ran side by side count once, a wait between two runs not at all."""
    total, reach = 0.0, float("-inf")
    for a, b in sorted(spans):
        total += max(0.0, b - max(a, reach))
        reach = max(reach, b)
    return total


def _spans(times: dict, key: str, now: float | None = None, style: str = "old") -> list[tuple[float, float]]:
    """The stage's timed steps as intervals; an open one ends at `now`, or is left out when now is None."""
    out = []
    for step, t in times.items():
        if stage_of(step, style) != key or "start" not in t:
            continue
        if "end" in t:
            out.append((t["start"], t["end"]))
        elif now is not None:
            out.append((t["start"], now))
    return out


def span(times: dict, key: str, style: str = "old") -> float | None:
    """Time the stage's finished steps took (None if none has both marks). The union of their intervals, not last end
    minus first start: a rerun after an error, or a fix round redoing a step, does not count the time between."""
    spans = _spans(times, key, style=style)
    return _covered(spans) if spans else None


def typical(history: list[dict], style: str = "old") -> dict[str, float]:
    out = {}
    for key in _keys(style):
        got = [s for t in history[:HISTORY] if (s := span(t, key, style)) is not None]
        out[key] = statistics.median(got) if got else FLOWS[style].default_seconds[key]
    return out


def _style_in(d: Path) -> str:
    try:
        return style_of(json.loads((d / "run.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):  # no run.json, or not JSON: the NotebookLM flow
        return "old"


def history(runs_dir: Path, style: str = "old") -> list[dict]:
    """times.json of the last HISTORY finished runs of this style that have one, newest first (by when auto.json was
    written). The two styles' stages are not the same, so their times are not mixed."""
    found = []
    for d in Path(runs_dir).iterdir() if Path(runs_dir).is_dir() else []:
        try:
            if (json.loads((d / "auto.json").read_text(encoding="utf-8")).get("state") == "done" and (d / timing.FILE).exists()
                    and _style_in(d) == style):
                found.append(((d / "auto.json").stat().st_mtime, d))
        except (OSError, ValueError, AttributeError):  # no auto.json, not JSON, not an object
            continue
    return [timing.read(d) for _, d in sorted(found, reverse=True)[:HISTORY]]


def _needed(auto: bool, style: str = "old") -> list[str]:
    """The steps a run always marks, in order (visuals_agent, brief_check… only sometimes)."""
    from vshort.queue import FLOW_STEPS
    steps = [s for s, _ in FLOW_STEPS[style]] + ["cover"]
    return ["brief_check" if auto and s == "approve_brief" else s for s in steps]


def _current(state: str, auto: bool, done: set[str], times: dict, fix_round: int = 0, style: str = "old") -> int | None:
    keys = _keys(style)
    if state == "wait_brief":
        return keys.index("brief")
    if state == "wait_script":
        return keys.index("approve")
    if state not in ("running", "error", "dead"):
        return None
    # auto.json's round too: a round whose fix has not started yet has no fix<r>_* step
    rounds = {m[1] for s in (*done, *times) if (m := _ROUND.match(s))} | ({str(fix_round)} if fix_round > 0 else set())
    if any(f"fixed{r}" not in done for r in rounds):
        # a fix round reruns visuals (the scene) and render: the video is still at "Soát và sửa", not back at stage 7
        return keys.index("review")
    staged = {s: t for s, t in times.items() if "start" in t and stage_of(s, style)}
    if open_ := [keys.index(stage_of(s, style)) for s, t in staged.items() if "end" not in t]:
        # the furthest stage with a step open: a short rerun of an earlier step (the voice after timeline answered 2)
        # does not walk the page back
        return max(open_)
    if staged:  # between two steps: the stage of the last step started
        return keys.index(stage_of(max((t["start"], s) for s, t in staged.items())[1], style))
    # no times (a run from before times.json): the first step not done
    return keys.index(next((stage_of(s, style) for s in _needed(auto, style) if s not in done), "cover"))


def _steps(key: str, auto: bool, done: set[str], times: dict, style: str = "old") -> list[dict]:
    names = [s for s in FLOWS[style].steps_of[key] if s != ("approve_brief" if auto else "brief_check")] or sorted(
        {s for s in (*done, *times) if stage_of(s, style) == key and not s.startswith("fixed")},
        key=lambda s: (times.get(s, {}).get("start", float("inf")), s))
    return [{"step": s, "label": _label(s, style),
             "status": "running" if "start" in times.get(s, {}) and "end" not in times[s] else "done" if s in done else "next"}
            for s in names]


def view(state: str, auto: bool, done: set[str], times: dict, typ: dict[str, float], now: float, fix_round: int = 0,
         style: str = "old") -> dict:
    """`state` is a Row's state (queue.status), `fix_round` auto.json's round, `typ` the typical seconds of this style's
    stages (typical). See the plan, Task 2, for the shape."""
    stage_list, keys = FLOWS[style].stages, _keys(style)
    n = len(stage_list)
    cur = None if state == "done" else _current(state, auto, done, times, fix_round, style)
    if state == "done":
        status = ["done"] * n
    elif cur is None:  # queued, idle: what state.json says is done
        need = _needed(auto, style)
        status = ["done" if all(s in done for s in need if stage_of(s, style) == k) else "next" for k in keys]
    else:
        mode = {"wait_brief": "you", "wait_script": "you", "running": "running"}.get(state, "error")
        status = ["done"] * cur + [mode] + ["next"] * (n - cur - 1)

    seconds: list[float | None] = []
    for k, st in zip(keys, status):
        if st == "done":
            seconds.append(span(times, k, style))
        elif st == "running":
            spans = _spans(times, k, now, style)
            seconds.append(_covered(spans) if spans else None)
        else:
            seconds.append(None)

    def left(i: int) -> float:
        k, st, sec = keys[i], status[i], seconds[i]
        if st in ("done", "you"):
            return 0
        if st == "running" and sec is not None:
            return max(typ[k] - sec, FLOOR)
        return typ[k]

    stops = {"approve"} | (set() if auto else {"brief"})
    stop = next((i for i in range(n) if keys[i] in stops and status[i] != "done"), None)
    if state == "done":
        eta = {"stop": None, "until_stop": None, "after_stop": None}
    elif stop is None:
        eta = {"stop": None, "until_stop": round(sum(left(i) for i in range(n))),
               "after_stop": None}
    else:
        eta = {"stop": stage_list[stop][1], "until_stop": round(sum(left(i) for i in range(stop))),
               "after_stop": round(sum(typ[k] for k in keys[stop + 1:]))}

    total = sum(typ[k] for k in keys)
    got = sum(typ[k] for k, st in zip(keys, status) if st == "done")
    if cur is not None and status[cur] == "running" and seconds[cur] is not None:
        got += min(seconds[cur], typ[keys[cur]])
    percent = 100 if state == "done" else min(99, max(0, round(100 * got / total))) if total else 0

    out = []
    for i, (k, label, what) in enumerate(stage_list):
        sec = seconds[i]
        out.append({"key": k, "label": label, "what": what, "status": status[i],
                    "seconds": None if sec is None else round(sec), "typical": round(typ[k]),
                    "overdue": status[i] == "running" and sec is not None and sec > typ[k],
                    "steps": _steps(k, auto, done, times, style) if status[i] == "running" else []})
    return {"stages": out, "current": cur, "percent": percent, "eta": eta}
