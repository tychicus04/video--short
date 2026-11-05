"""What the web control panel knows without a server: slugs, the files it may hand out, the queue of topics waiting to
start, one status row per video and which to start next. Plain functions over the run folders, so they test without
a browser."""
import json
import os
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from vshort import auto, stages, timing
from vshort.run import Run, config

SLUG_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,59}\Z")  # \Z, not $: "abc\n" is not a slug
MAX_TOPIC = 500
BAD_FILE = (OSError, ValueError, KeyError, TypeError, AttributeError)  # what a missing, hand-edited or non-object file raises
# the steps in the order `vshort auto` does them (what the panel shows as "Đang ở bước …")
STEPS = [("research", "Tìm hiểu"), ("approve_brief", "Chờ duyệt brief"), ("source", "Nạp brief"),
         ("fetch", "NotebookLM làm video"), ("detect", "Tách phụ đề"), ("transcribe", "Chép phụ đề"), ("text", "Ghép câu"),
         ("translate", "Dịch"), ("approve_script", "Chờ duyệt bản dịch"), ("plates", "Xóa chữ cũ"), ("motion", "Hình động"),
         ("stills", "Ảnh tĩnh"), ("tts", "Đọc giọng"), ("visuals", "Tư liệu"), ("timeline", "Dòng thời gian"),
         ("render", "Dựng video"), ("review0", "Soát")]
# the order of the list: what needs Tai first, finished and untouched last
ORDER = {s: i for i, s in enumerate(["wait_brief", "wait_script", "error", "dead", "running", "queued", "done", "idle"])}
KNOWN = {"running", "wait_brief", "wait_script", "error", "done"}  # what auto.py writes; anything else shows as error


def slugify(topic: str) -> str:
    """A folder name from a topic (or the last part of a URL's path): ascii, lower case, dashes, at most 60 characters.
    May be empty (nothing but symbols); the caller says so."""
    t = topic.strip()
    if re.match(r"https?://", t):
        u = urlparse(t)
        t = unquote(u.path.rstrip("/").rsplit("/", 1)[-1]) or u.netloc  # %C3%A9 is é
    t = unicodedata.normalize("NFKD", t.lower().replace("đ", "d"))
    s = re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if not unicodedata.combining(c))).strip("-")
    if len(s) > 60:  # cut at a dash so the last word is whole, unless there is none to cut at
        head = s[:60]
        s = head if s[60] == "-" else head.rpartition("-")[0] or head
    return s.strip("-")


def runs_dir() -> Path:
    return Path(config()["runs_dir"]).expanduser()


def run_path(slug: str) -> Path:
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"slug không hợp lệ: {slug!r}")
    return runs_dir() / slug


def safe_file(slug: str, name: str) -> Path | None:
    """The file `name` of this run if it is a regular file inside runs_dir/<slug> once symlinks are followed, else None.
    A run folder that is itself a link to somewhere else gives None for everything. Raises ValueError for a bad slug;
    the server checks the slug first."""
    run_path(slug)  # the slug check, before a path is made of it
    root = runs_dir().resolve() / slug
    try:
        p = (root / name).resolve()
    except (OSError, ValueError, RuntimeError):  # an embedded NUL, a symlink loop
        return None
    return p if p.is_relative_to(root) and p.is_file() else None


# --- the queue -----------------------------------------------------------------------------------------------------

@dataclass
class Queue:
    new: list[dict]  # topics not started yet: {"slug", "topic", "auto", "added"}
    resume: list[str]  # slugs of existing runs waiting to be run again


def _queue_file() -> Path:
    return runs_dir() / "queue.json"


def load_queue() -> Queue:
    f = _queue_file()
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return Queue(d.get("new", []), d.get("resume", []))


def save_queue(q: Queue) -> None:
    f = _queue_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    # whole file or nothing, as Run._save: a reader never sees it half written
    tmp = f.with_name(f".queue.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(asdict(q), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def add_topics(q: Queue, items: list[dict], auto: bool) -> list[str]:
    """Queue new topics. One message per item ("" = fine); nothing is added unless every item is fine."""
    errs, seen = [], {it["slug"] for it in q.new}
    for it in items:
        slug, topic = it.get("slug"), it.get("topic")
        if not (isinstance(slug, str) and isinstance(topic, str)):
            errs.append("Dữ liệu gửi lên sai dạng")
        elif not slug:
            errs.append("Chủ đề không có chữ hay số nào để đặt tên thư mục")
        elif not SLUG_RE.fullmatch(slug):
            errs.append("Tên thư mục chỉ gồm a-z, 0-9 và dấu -, tối đa 60 ký tự")
        elif not topic.strip():
            errs.append("Chủ đề trống")
        elif len(topic.strip()) > MAX_TOPIC:
            errs.append(f"Chủ đề dài quá {MAX_TOPIC} ký tự")
        elif slug in seen or (runs_dir() / slug).exists():
            errs.append(f"Đã có video hoặc chủ đề tên {slug}")
        else:
            errs.append("")
            seen.add(slug)
    if not any(errs):
        now = time.time()
        q.new += [{"slug": it["slug"], "topic": it["topic"].strip(), "auto": auto, "added": now} for it in items]
    return errs


def add_resume(q: Queue, slug: str) -> None:
    if slug not in q.resume:
        q.resume.append(slug)


# --- one row per video ---------------------------------------------------------------------------------------------

def _read(run: Run, name: str) -> dict:
    """run.json and the like as a dict; {} when the file is missing, not JSON or not an object. A video that is being
    written or was edited by hand must still show up in the list."""
    try:
        data = run.read(name)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _step(run: Run, auto_mode: bool) -> str | None:
    """The label of the first step `run.done` says is not done; an automatic run never marks approve_brief."""
    try:
        return next((label for step, label in STEPS if not (auto_mode and step == "approve_brief") and not run.done(step)), None)
    except BAD_FILE:  # state.json is not JSON, or not an object: nothing is known to be done
        return STEPS[0][1]


def done_steps(run: Run) -> set[str]:
    """The steps state.json has done; none when it is missing, not JSON or not an object."""
    try:
        st = run._load()
    except BAD_FILE:
        return set()
    return {k for k, v in st.items() if v == "done"} if isinstance(st, dict) else set()


def typical() -> dict[str, float]:
    return stages.typical(stages.history(runs_dir()))


PROGRESS = {"running", "wait_brief", "wait_script", "error", "dead"}  # the rows whose card shows a stage


def status(run: Run, queued: bool, typ: dict[str, float] | None = None) -> dict:
    """The Row for one run folder. Never raises on a missing or broken file. `relogin` is read from auto.json even for a
    queued row: once Tai has queued the runs that stopped for the login, the queue must start again. `typ`: the
    typical stage times (stages.typical), worked out once by the caller for every row."""
    meta = _read(run, "run.json")
    try:
        a = auto.get_state(run)
    except BAD_FILE:  # auto.json is not JSON: as if there were none
        a = {}
    a = a if isinstance(a, dict) else {}  # JSON, but not an object
    raw = str(a.get("state", "none"))
    message = str(a.get("message") or "")
    if raw == "none":
        state = "idle"
    elif raw not in KNOWN:
        state = "error"  # stays in the part of the list that needs Tai
    elif raw == "running":  # `ps` once per call, so only for the rows that say running
        try:
            state = "running" if auto.alive_run(run) else "dead"
        except BAD_FILE:
            state = "dead"
    else:
        state = raw
    relogin = False
    if raw == "error":
        from vshort.cli import RELOGIN  # heavy import: only when there is an error to compare
        relogin = message == RELOGIN
    try:
        cost = auto.total_cost(run)
    except BAD_FILE:
        cost = 0.0
    seconds = _read(run, "timeline.json").get("total")
    stamped = next((f for f in (run.file("auto.json"), run.file("run.json")) if f.exists()), None)
    pic = next((n for n in ("cover/gemini-9x16.jpg", "cover/thumb-9x16.jpg") if run.file(n).is_file()), None)
    progress = None
    if not queued and state in PROGRESS:
        v = stages.view(state, bool(meta.get("auto")), done_steps(run), timing.read(run.path),
                        typical() if typ is None else typ, time.time())
        at = v["stages"][v["current"]]
        progress = {"percent": v["percent"], "n": v["current"] + 1, "label": at["label"], "status": at["status"],
                    "eta": v["eta"], "elapsed": sum(st["seconds"] or 0 for st in v["stages"])}
    return {"slug": run.path.name, "topic": str(meta.get("topic") or ""), "auto": bool(meta.get("auto")),
            "title": str(_read(run, "cover/cover.json").get("title") or ""),
            "state": "queued" if queued else state,
            "message": "\n".join(ln for ln in message.splitlines() if not ln.startswith("Chép về Mac")),
            "step": _step(run, bool(meta.get("auto"))),
            "since": stamped.stat().st_mtime if stamped else None,
            "cost": cost, "verdict": _read(run, "review.json").get("verdict"), "seconds": seconds,
            "relogin": relogin, "removable": False, "progress": progress,
            # the card's picture: Tai's Gemini cover, else the composed one
            "cover": {"name": pic, "v": int(run.file(pic).stat().st_mtime)} if pic else None}


class _Folder(Run):
    """A run folder opened without parsing state.json: Run() does, and a broken one would raise before status() could
    show the video. done/mark/unmark read the file as in Run; _step() catches what done() raises."""

    def __init__(self, path: Path):
        self.path, self._state_file, self.state = Path(path), Path(path) / "state.json", {}


def rows(q: Queue, typ: dict[str, float] | None = None) -> list[dict]:
    """Every run folder and every topic waiting to start, in the order the panel lists them."""
    root = runs_dir()
    typ = typical() if typ is None else typ
    found = [status(_Folder(p), p.name in q.resume, typ) for p in sorted(root.iterdir())
             if p.is_dir() and SLUG_RE.fullmatch(p.name)] if root.is_dir() else []
    have = {r["slug"] for r in found}
    waiting = [{"slug": it["slug"], "topic": it["topic"], "auto": it["auto"], "title": "", "state": "queued", "message": "",
                "step": STEPS[0][1], "since": it["added"], "cost": 0.0, "verdict": None, "seconds": None,
                "relogin": False, "removable": True, "progress": None, "cover": None} for it in q.new if it["slug"] not in have]
    place = {s: i for i, s in enumerate([*q.resume, *(it["slug"] for it in q.new)])}
    # queued: in the order of the queue; done: the newest first
    return sorted(found + waiting, key=lambda r: (ORDER[r["state"]], place[r["slug"]] if r["state"] == "queued"
                                                  else -(r["since"] or 0) if r["state"] == "done" else 0))


def relogin_waiting(rs: list[dict]) -> list[str]:
    """Runs that stopped because NotebookLM wants a new login and have not been queued again. While there are any, the
    queue starts nothing: every new run would stop at the same place."""
    # ponytail: Claude quota/login errors have no code of their own yet, so they don't pause the queue (every video just
    # fails by itself). Give them a code like RELOGIN and pause on it here if they happen for real.
    return [r["slug"] for r in rs if r["relogin"] and r["state"] != "queued"]


def next_to_start(q: Queue, rs: list[dict], max_running: int) -> list[tuple[str, str]]:
    """("resume" | "new", slug) to start now: runs to continue first, then new topics, each in the order queued."""
    if relogin_waiting(rs):
        return []
    todo = [("resume", s) for s in q.resume] + [("new", it["slug"]) for it in q.new]
    return todo[:max(max_running - sum(r["state"] == "running" for r in rs), 0)]
