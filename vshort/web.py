"""The web control panel's server, read side: the status of every video, one video's files, final.mp4 with HTTP Range
(Safari and iOS will not play a video without it), the shared access-code login and the built UI. Endpoints are plain
`def`: Starlette runs them in its threadpool, so a slow `ps` or file read does not hold up the others."""
import hmac
import json
from pathlib import Path
from urllib.parse import quote, unquote

import uvicorn
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from vshort import auto, queue
from vshort.run import config

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
COOKIE = "vshort_token"
YEAR = 365 * 24 * 3600
LOG_LINES = 50


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


def _row(slug: str) -> dict | None:
    """The Row of one video. Through rows(): it never raises on a broken state.json, status() would."""
    if not queue.SLUG_RE.fullmatch(slug):
        return None
    return next((r for r in queue.rows(queue.load_queue()) if r["slug"] == slug), None)


def _locked(slug: str) -> bool:
    return auto.locked_by(queue._Folder(queue.run_path(slug))) is not None  # _Folder: Run() would raise on a broken state.json


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


def _translation(slug: str) -> list[dict] | None:
    """The English sentences next to the Vietnamese phrases of the same id; None when either file is missing or odd."""
    try:
        en = {s["id"]: s["en"] for s in _json(slug, "sentences.en.json")}
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
    """brief.vi.md changed after brief.en.md: NotebookLM would make the video from the old English one (as cmd_approve)."""
    vi, en = queue.safe_file(slug, "brief.vi.md"), queue.safe_file(slug, "brief.en.md")
    return bool(vi and en and vi.stat().st_mtime > en.stat().st_mtime)


def state(request: Request) -> JSONResponse:
    rows = queue.rows(queue.load_queue())
    return JSONResponse({"rows": rows, "relogin": queue.relogin_waiting(rows), "can_write": can_write(request),
                         "token_set": bool(token()), "max_running": config()["web_max_running"]})


def run_detail(request: Request) -> JSONResponse:
    slug = request.path_params["slug"]
    if (row := _row(slug)) is None:
        return _error("Không có video này", 404)
    locked = _locked(slug)
    cost = _json(slug, "cost.json")
    return JSONResponse({"row": row, "locked": locked, "brief_vi": _text(slug, "brief.vi.md"),
                         "brief_en": _text(slug, "brief.en.md"), "brief_en_stale": _stale(slug),
                         "translation": _translation(slug), "proposed": _proposed(slug), "review_md": _text(slug, "review.md"),
                         "cost": cost if isinstance(cost, list) else [],
                         "log_tail": "\n".join((_text(slug, "auto.log") or "").splitlines()[-LOG_LINES:]),
                         "video": queue.safe_file(slug, "final.mp4") is not None and not locked})


def video(request: Request) -> Response:
    """Only final.mp4, and not while `vshort auto` is writing it. FileResponse answers Range requests itself."""
    slug, name = request.path_params["slug"], request.path_params["name"]
    if name != "final.mp4" or not queue.SLUG_RE.fullmatch(slug) or (p := queue.safe_file(slug, name)) is None:
        return _error("Không có video này", 404)
    if _locked(slug):
        return _error("Video đang được dựng lại, chờ xong rồi xem", 409)
    return FileResponse(p, media_type="video/mp4", filename=f"{slug}.mp4" if "download" in request.query_params else None)


async def login(request: Request) -> Response:
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


def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    """Starlette's own 404 and 405 are English text."""
    return _error({404: "Không có trang này", 405: "Không dùng được cách gọi này"}.get(exc.status_code, "Có lỗi"), exc.status_code)


def _crash(request: Request, exc: Exception) -> JSONResponse:
    return _error("Máy chủ gặp lỗi, xem log của `vshort web`", 500)


ROUTES = [
    Route("/api/state", state),
    Route("/api/runs/{slug}", run_detail),
    Route("/files/{slug}/{name}", video),
    Route("/api/login", login, methods=["POST"]),
]
# last, and only when built: StaticFiles on a missing folder answers 500 to everything it is asked
STATIC = [Mount("/", StaticFiles(directory=DIST, html=True))] if DIST.is_dir() else []

app = Starlette(routes=ROUTES + STATIC, exception_handlers={HTTPException: _http_error, Exception: _crash})


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=config()["web_port"])


if __name__ == "__main__":
    main()
