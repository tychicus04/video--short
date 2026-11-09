"""The web control panel's server: the status of every video, one video's files, final.mp4 with HTTP Range (Safari and
iOS will not play a video without it), the shared access-code login, the edits Tai makes (queue, brief, translation,
approve, retry), the loop that starts what the queue says, and the built UI. Read endpoints are plain `def`: Starlette
runs them in its threadpool, so a slow `ps` or file read does not hold up the others. A write reads its body in async
code and does the rest in the threadpool too (`_post`): it may wait for LOCK, a `vshort` command or an agent."""
import base64
import difflib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, unquote

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from vshort import auto, cms, cover, publish, queue, stages
from vshort.run import config

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
COOKIE = "vshort_token"
YEAR = 365 * 24 * 3600
LOG_LINES = 50
TICK = 5  # seconds between two looks at the queue
# the only files served besides final.mp4
COVERS = {"cover/thumb-9x16.jpg", "cover/thumb-16x9.jpg", *(f"cover/{n}" for n in cover.GEMINI.values())}
COVER_LOCK = threading.Lock()  # one Gemini upload at a time: cover.package builds every export in the same .xuat
LOCK = threading.Lock()  # every load -> change -> save of queue.json, in tick() and in the routes. Not reentrant: take it last.
BAD_BODY = "Dữ liệu gửi lên sai dạng"
BRIEF_SYNC = ("RUN={run}. Tai vừa sửa {run}/brief.vi.md (diff bên dưới). Sửa {run}/brief.en.md cho khớp đúng những chỗ đó, "
              "giữ nguyên phần còn lại. Không tạo notebook, không nạp nguồn, không tìm web.\n\n```diff\n{diff}\n```")


def token() -> str:
    """The shared access code; "" when there is no file, and then nobody can write."""
    try:
        return Path(config()["web_token_file"]).expanduser().read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""


def _same(given: str, want: str) -> bool:
    return bool(want) and hmac.compare_digest(given.encode(), want.encode())  # bytes: compare_digest refuses non-ascii str


def can_write(request: Request) -> bool:
    """Read from the server's token on every call, so changing the token file logs everyone out."""
    return _same(unquote(request.cookies.get(COOKIE, "")), token())


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status)


def _not_json(request: Request) -> Response | None:
    """415 unless the body claims to be JSON (`; charset=...` is fine). Cookies are not port-scoped, so a page of another
    service on this host (CMS-Admin on another port) is same-site and could POST `text/plain` with our cookie attached;
    `application/json` cannot be sent cross-origin without a CORS preflight, which this server never approves."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return _error("Chỉ nhận dữ liệu dạng JSON", 415)


def _row(slug: str, typ: dict | None = None) -> dict | None:
    """The Row of one video. Through rows(): it never raises on a broken state.json, status() would."""
    if not queue.SLUG_RE.fullmatch(slug):
        return None
    return next((r for r in queue.rows(queue.load_queue(), typ) if r["slug"] == slug), None)


def _locked(slug: str) -> bool:
    """A live `vshort auto` has the run: it holds auto.lock, or it has just been started (auto.json says running and its
    process is alive) and its child has not made the lock yet. Read from auto.json, not from the Row: the Row shows `queued` in between."""
    run = queue._Folder(queue.run_path(slug))  # _Folder: Run() would raise on a broken state.json
    try:
        return auto.locked_by(run) is not None or (auto.get_state(run).get("state") == "running" and auto.alive_run(run))
    except queue.BAD_FILE:  # auto.json is not JSON, or has no pid
        return False


def _text(slug: str, name: str) -> str | None:
    """A file of the run as text, or None when it is missing or is not a regular file inside the run folder."""
    p = queue.safe_file(slug, name)
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p else None
    except OSError:
        return None


def _json(slug: str, name: str):
    text = _text(slug, name)
    try:
        return None if text is None else json.loads(text)
    except ValueError:
        return None


def _neon(slug: str) -> bool:
    """A neon run: its narration is written from the brief, so there is no English brief, nor English sentences, to show."""
    return stages.style_of(_json(slug, "run.json")) == "neon"


def _translation(slug: str) -> list[dict] | None:
    """The English sentences next to the Vietnamese phrases of the same id; None when either file is missing or odd.
    A neon run has none: its sentences come with "en": "" and the page leaves the English column empty."""
    try:
        en = {} if _neon(slug) else {s["id"]: s["en"] for s in _json(slug, "sentences.en.json")}
        return [{"id": r["id"], "en": en.get(r["id"], ""), "phrases": r["phrases"], "note": r.get("note", "")}
                for r in _json(slug, "script.vi.json")]
    except queue.BAD_FILE:  # a file is missing (None), or was edited by hand into another shape
        return None


def _proposed(slug: str) -> list[dict] | None:
    try:
        return [{"id": r["id"], "phrases": r["phrases"], "note": r.get("note", "")} for r in _json(slug, "script.proposed.json")]
    except queue.BAD_FILE:
        return None


def _stale(slug: str) -> bool:
    """brief.vi.md changed after brief.en.md: NotebookLM would make the video from the old English one (as cmd_approve).
    A neon run makes no video from an English brief."""
    if _neon(slug):
        return False
    vi, en = queue.safe_file(slug, "brief.vi.md"), queue.safe_file(slug, "brief.en.md")
    return bool(vi and en and vi.stat().st_mtime > en.stat().st_mtime)


def state(request: Request) -> JSONResponse:
    rows = queue.rows(queue.load_queue())
    return JSONResponse({"rows": rows, "relogin": queue.relogin_waiting(rows), "can_write": can_write(request),
                         "token_set": bool(token()), "max_running": config()["web_max_running"]})


def run_detail(request: Request) -> JSONResponse:
    slug = request.path_params["slug"]
    typ = queue.typical()
    if (row := _row(slug, typ)) is None:
        return _error("Không có video này", 404)
    locked = _locked(slug)
    run, now = queue._Folder(queue.run_path(slug)), time.time()
    progress = queue.view(run, row["state"], row["auto"], typ, now)
    cost = _json(slug, "cost.json")
    return JSONResponse({"row": row, "locked": locked, "brief_vi": _text(slug, "brief.vi.md"),
                         "brief_en": _text(slug, "brief.en.md"), "brief_en_stale": _stale(slug),
                         "translation": _translation(slug), "proposed": _proposed(slug), "review_md": _text(slug, "review.md"),
                         "cost": cost if isinstance(cost, list) else [],
                         "log_tail": "\n".join((_text(slug, "auto.log") or "").splitlines()[-LOG_LINES:]),
                         "video": queue.safe_file(slug, "final.mp4") is not None and not locked,
                         "cover_v": _version(slug, "cover/cover.json"), "prompt": _text(slug, "cover/prompt.txt"),
                         "prompt_wide": cover.WIDE, "progress": progress, "now": now,
                         "gemini": {shape: _version(slug, f"cover/{n}") for shape, n in cover.GEMINI.items()},
                         "cms": _cms(slug)})


def _cms(slug: str) -> dict:
    """The "Gửi lên CMS" box: whether the server has its settings, which CMS, and how the last send went. The record
    is cms.json's, which never holds the token; Settings stays here."""
    s, missing = cms.load()
    path = queue.run_path(slug)
    return {"configured": s is not None, "missing": missing, "env": s.env if s else None,
            "running": publish.sender(path) is not None, "record": publish.read(path, s.env) if s else {}}


def _version(slug: str, name: str) -> int | None:
    """mtime of a file, for ?v= on a cover's address: a new cover is fetched, an unchanged one comes from the cache."""
    p = queue.safe_file(slug, name)
    return int(p.stat().st_mtime) if p else None


def video(request: Request) -> Response:
    """final.mp4, not while `vshort auto` is writing it, and the two headline covers. FileResponse answers Range requests itself."""
    slug, name = request.path_params["slug"], request.path_params["name"]
    if name not in COVERS | {"final.mp4"} or not queue.SLUG_RE.fullmatch(slug) or (p := queue.safe_file(slug, name)) is None:
        return _error("Không có video này", 404)
    if name in COVERS:
        return FileResponse(p, media_type="image/jpeg")
    if _locked(slug):
        return _error("Video đang được dựng lại, chờ xong rồi xem", 409)
    return FileResponse(p, media_type="video/mp4", filename=f"{slug}.mp4" if "download" in request.query_params else None)


async def login(request: Request) -> Response:
    if (bad := _not_json(request)) is not None:
        return bad
    try:
        body = await request.json()
    except ValueError:
        body = None
    given = body.get("token") if isinstance(body, dict) else None
    if not isinstance(given, str) or not _same(given, token()):
        return _error("Mã truy cập sai", 403)
    r = Response(status_code=204)
    # no `secure`: the site is plain http on the LAN, a secure cookie would never be sent back.
    # quote: a header is latin-1, so a code with "đ" in it would otherwise be a 500
    r.set_cookie(COOKIE, quote(given), max_age=YEAR, httponly=True, samesite="strict")
    return r


# --- writes ---------------------------------------------------------------------------------------------------------

def _is_run(slug: str) -> bool:
    """The folder of a video that has started: a real folder in runs_dir (not a link out), not a topic still in the queue."""
    if not queue.SLUG_RE.fullmatch(slug):
        return False
    d = queue.runs_dir().resolve() / slug
    return d.is_dir() and not d.is_symlink()


def _put(slug: str, name: str, text: str) -> None:
    """A file of the run, whole or not at all (as Run._save), so `vshort` never reads half of it. replace() swaps a link
    for the new file instead of writing through it to somewhere outside the folder."""
    p = queue.run_path(slug) / name
    tmp = p.with_name(f".{name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def vshort(args: list[str]) -> subprocess.CompletedProcess:
    """One `vshort` command in a process of its own, as Tai would type it."""
    return subprocess.run([sys.executable, "-m", "vshort.cli", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def _log(line: str) -> None:
    try:
        f = queue.runs_dir() / "web.log"
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:  # the log is the last place to complain about a disk that does not work
        pass


def start(kind: str, slug: str, item: dict | None) -> None:
    """Ask `vshort auto` to start one video in the background (it returns at once). It may refuse, e.g. the folder
    appeared meanwhile: then the item is dropped and one line goes to web.log."""
    try:
        # --topic=...: as two arguments, a topic that begins with "-" is read by argparse as an option
        args = (["auto", slug, f"--topic={item['topic']}", *(["--auto"] if item["auto"] else [])] if kind == "new"
                else ["auto", str(queue.run_path(slug))])
        cp = vshort(args)
        why = None if cp.returncode == 0 else (cp.stderr or cp.stdout)
    except Exception as e:  # not only a timeout: a NUL in the topic makes subprocess raise ValueError. One item must not block the rest.
        why = repr(e)
    if why is not None:
        # ponytail: item hỏng bị bỏ, chỉ ghi log; hiện lên trang nếu thấy xảy ra
        _log(f"không bắt đầu được {kind} {slug}: {' '.join(why.split())[:300]}")


def tick() -> None:
    """One look at the queue: start what may start now, as many as max_running leaves room for."""
    with LOCK:
        q = queue.load_queue()
        todo = queue.next_to_start(q, queue.rows(q), config()["web_max_running"])
        try:
            for kind, slug in todo:
                item = next(i for i in q.new if i["slug"] == slug) if kind == "new" else None
                start(kind, slug, item)
                if item:
                    q.new.remove(item)
                else:
                    q.resume.remove(slug)
        finally:  # whatever was started must not be started again next time
            if todo:
                queue.save_queue(q)


async def _loop() -> None:
    last = None
    while True:
        await anyio.sleep(TICK)
        try:
            await anyio.to_thread.run_sync(tick)
            last = None
        except Exception as e:  # one bad pass must not end the loop; the same message is not logged every 5 seconds
            if repr(e) != last:
                _log(f"tick lỗi: {e!r}")
            last = repr(e)


@asynccontextmanager
async def _lifespan(app: Starlette):
    async with anyio.create_task_group() as tg:
        tg.start_soon(_loop)
        yield
        tg.cancel_scope.cancel()


def _post(fn, *, run: bool = False):
    """A POST route. In this order: the access code (403); a JSON Content-Type (415); for a video's route, that it has started (404) and that no
    `vshort auto` holds it (409); the JSON object body, which may be left out (400). Then `fn(body)`, or
    `fn(slug, body)` for a video, in the threadpool."""
    def checked(slug, body):
        if run and not _is_run(slug):
            return _error("Không có video này", 404)
        if run and _locked(slug):
            return _error("Video đang chạy, đợi nó dừng rồi sửa", 409)
        if not isinstance(body, dict):
            return _error(BAD_BODY, 400)
        return fn(slug, body) if run else fn(body)

    async def endpoint(request: Request) -> Response:
        if not can_write(request):
            return _error("Cần mã truy cập", 403)
        if (bad := _not_json(request)) is not None:
            return bad
        raw = await request.body()
        try:
            body = json.loads(raw) if raw.strip() else {}
        except ValueError:
            body = None
        return await run_in_threadpool(checked, request.path_params.get("slug"), body)

    return endpoint


def _requeue(slug: str) -> None:
    with LOCK:
        q = queue.load_queue()
        queue.add_resume(q, slug)
        queue.save_queue(q)


def add_to_queue(body: dict) -> Response:
    items, run_auto = body.get("items"), body.get("auto", False)
    if not (isinstance(items, list) and all(isinstance(i, dict) for i in items) and isinstance(run_auto, bool)):
        return _error(BAD_BODY, 400)
    with LOCK:
        q = queue.load_queue()
        errors = queue.add_topics(q, items, run_auto)
        if not any(errors):
            queue.save_queue(q)
    return JSONResponse({"errors": errors}, 400 if any(errors) else 200)


def remove_from_queue(body: dict) -> Response:
    slug = body.get("slug")
    if not isinstance(slug, str):
        return _error(BAD_BODY, 400)
    with LOCK:
        q = queue.load_queue()
        n = len(q.new)
        q.new = [i for i in q.new if i["slug"] != slug]
        if len(q.new) == n:
            return _error("Chủ đề này không còn trong hàng đợi (có thể đã bắt đầu chạy)", 404)
        queue.save_queue(q)
    return Response(status_code=204)


def resume_queue(body: dict) -> Response:
    """Queue again the runs that stopped for the NotebookLM login, after Tai has logged in."""
    with LOCK:
        q = queue.load_queue()
        for slug in queue.relogin_waiting(queue.rows(q)):
            queue.add_resume(q, slug)
        queue.save_queue(q)
    return Response(status_code=204)


def save_brief(slug: str, body: dict) -> Response:
    """Save the Vietnamese brief; a cheap agent brings the English one in line with what changed (a neon run has none)."""
    vi = body.get("vi")
    if not isinstance(vi, str):
        return _error(BAD_BODY, 400)
    old = _text(slug, "brief.vi.md") or ""
    if vi != old:  # unchanged is not written: a newer brief.vi.md would make brief.en.md look stale
        _put(slug, "brief.vi.md", vi)
        if not _neon(slug):
            run = queue._Folder(queue.run_path(slug))
            diff = "\n".join(difflib.unified_diff(old.splitlines(), vi.splitlines(), "brief.vi.md (cũ)", "brief.vi.md (mới)", lineterm=""))
            try:
                auto.run_claude(run, "brief_sync", "vs-researcher", BRIEF_SYNC.format(run=run.path, diff=diff), 600)
            except auto.AgentError as e:
                return _error(f"Đã lưu bản tiếng Việt, nhưng chưa sửa được bản tiếng Anh: {e}", 502)
    return JSONResponse({"brief_en": _text(slug, "brief.en.md"), "brief_en_stale": _stale(slug)})


def save_brief_en(slug: str, body: dict) -> Response:
    en = body.get("en")
    if not isinstance(en, str):
        return _error(BAD_BODY, 400)
    _put(slug, "brief.en.md", en)
    return Response(status_code=204)


def save_script(slug: str, body: dict) -> Response:
    rows = body.get("rows")
    if not (isinstance(rows, list) and all(
            isinstance(r, dict) and type(r.get("id")) is int and isinstance(r.get("phrases"), str) and isinstance(r.get("note", ""), str)
            for r in rows)):
        return _error(BAD_BODY, 400)
    try:
        want = sorted(r["id"] for r in _json(slug, "script.vi.json"))
    except queue.BAD_FILE:
        return _error("Chưa có bản dịch để sửa", 400)
    if sorted(r["id"] for r in rows) != want:  # sorted lists, not sets: a repeated id is a mistake too
        return _error("Các câu gửi lên không khớp bản dịch hiện có: thiếu, thừa hoặc trùng số câu", 400)
    _put(slug, "script.vi.json", json.dumps([{"id": r["id"], "phrases": r["phrases"], **({"note": r["note"]} if r.get("note") else {})}
                                             for r in rows], ensure_ascii=False, indent=1))
    cp = vshort(["check", str(queue.run_path(slug))])
    return JSONResponse({"ok": cp.returncode == 0, "problems": [ln.strip() for ln in cp.stderr.splitlines() if ln.strip()]})


def answer_proposal(slug: str, body: dict) -> Response:
    """Take the translator's proposal as the translation, or leave it; either way it is gone: `vshort approve` refuses while it exists."""
    use = body.get("use")
    if not isinstance(use, bool):
        return _error(BAD_BODY, 400)
    if use:
        text = _text(slug, "script.proposed.json")
        if text is None or _proposed(slug) is None:
            return _error("Không có bản đề xuất, hoặc bản đề xuất hỏng", 400)
        _put(slug, "script.vi.json", text)
    (queue.run_path(slug) / "script.proposed.json").unlink(missing_ok=True)
    return Response(status_code=204)


def approve(slug: str, body: dict) -> Response:
    what = body.get("what")
    if what not in ("brief", "script"):
        return _error(BAD_BODY, 400)
    if (_row(slug) or {}).get("state") != f"wait_{what}":  # also queued: the first click already did it
        return _error("Video không đang chờ duyệt bước này (có thể đã duyệt rồi)", 400)
    cp = vshort(["approve", str(queue.run_path(slug)), what])
    if cp.returncode != 0:
        return _error((cp.stderr or cp.stdout).strip() or "Không duyệt được", 400)
    _requeue(slug)
    return Response(status_code=204)


def retry(slug: str, body: dict) -> Response:
    if (_row(slug) or {}).get("state") not in ("error", "dead"):
        return _error("Chỉ chạy lại được video đang lỗi hoặc đã dừng giữa chừng", 400)
    _requeue(slug)
    return Response(status_code=204)


def save_cover(slug: str, body: dict) -> Response:
    """A cover Tai drew in the Gemini app, as base64 in JSON (a form upload could come from another site, see _not_json);
    the export folder is laid out again so the Mac pulls it."""
    data = body.get("data")
    if not isinstance(data, str):
        return _error(BAD_BODY, 400)
    if len(data) > cover.MAX_UPLOAD * 4 // 3 + 4:
        return _error(f"Ảnh lớn quá {cover.MAX_UPLOAD // 1_000_000} MB", 413)
    try:
        raw = base64.b64decode(data, validate=True)
    except ValueError:  # binascii.Error, or a character that is not ascii
        return _error("Ảnh gửi lên bị hỏng, thử chọn lại file", 400)
    run_dir = queue.run_path(slug)
    with COVER_LOCK:
        try:
            cover.save_gemini(run_dir, body.get("shape"), raw)
        except ValueError as e:
            return _error(str(e), 400)
        if (run_dir / "final.mp4").is_file() and (run_dir / "cover" / "cover.json").is_file():
            try:
                cover.package(run_dir)
            except (OSError, ValueError, KeyError) as e:
                return _error(f"Đã lưu ảnh, nhưng chưa làm lại được thư mục xuất: {e}", 500)
    return Response(status_code=204)


def send_cms(slug: str, body: dict) -> Response:
    """Start `vshort cms` for a finished video; it runs in the background, the page reads cms.json as it goes."""
    recreate = body.get("recreate", False)
    if not isinstance(recreate, bool):
        return _error(BAD_BODY, 400)
    if (_row(slug) or {}).get("state") != "done":
        return _error("Chỉ gửi được video đã xong", 400)
    path = queue.run_path(slug)
    if publish.sender(path):
        return _error("Đang gửi, đợi xong", 409)
    s, missing = cms.load()
    if s is None:
        return _error("Chưa cấu hình CMS trên máy chủ: " + "; ".join(missing), 400)
    cp = vshort(["cms", str(path), *(["--recreate"] if recreate else [])])
    if cp.returncode != 0:
        return _error((cp.stderr or cp.stdout).strip() or "Không bắt đầu gửi được", 409)
    return JSONResponse({"started": True}, 202)


def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    """Starlette's own 404 and 405 are English text."""
    return _error({404: "Không có trang này", 405: "Không dùng được cách gọi này"}.get(exc.status_code, "Có lỗi"), exc.status_code)


def _crash(request: Request, exc: Exception) -> JSONResponse:
    return _error("Máy chủ gặp lỗi, xem log của `vshort web`", 500)


ROUTES = [
    Route("/api/state", state),
    Route("/api/runs/{slug}", run_detail),
    Route("/files/{slug}/{name:path}", video),
    Route("/api/login", login, methods=["POST"]),
    Route("/api/queue", _post(add_to_queue), methods=["POST"]),
    Route("/api/queue/remove", _post(remove_from_queue), methods=["POST"]),
    Route("/api/resume", _post(resume_queue), methods=["POST"]),
    Route("/api/runs/{slug}/brief", _post(save_brief, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/brief_en", _post(save_brief_en, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/script", _post(save_script, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/proposal", _post(answer_proposal, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/approve", _post(approve, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/retry", _post(retry, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/cover", _post(save_cover, run=True), methods=["POST"]),
    Route("/api/runs/{slug}/cms", _post(send_cms, run=True), methods=["POST"]),
]
class Dist(StaticFiles):
    """The built UI. Assets have a hash in their name and may be cached; index.html names them, so it is revalidated
    every time (it carries an ETag, so that costs a 304): else Safari keeps an old index pointing at deleted assets."""
    def file_response(self, full_path, stat_result, scope, status_code=200):
        r = super().file_response(full_path, stat_result, scope, status_code)
        if Path(full_path).name == "index.html":
            r.headers["Cache-Control"] = "no-cache"
        return r


# last, and only when built: StaticFiles on a missing folder answers 500 to everything it is asked
STATIC = [Mount("/", Dist(directory=DIST, html=True))] if DIST.is_dir() else []

app = Starlette(routes=ROUTES + STATIC, lifespan=_lifespan, exception_handlers={HTTPException: _http_error, Exception: _crash})


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=config()["web_port"])


if __name__ == "__main__":
    main()
