"""HyperFrames (HTML + GSAP composition -> MP4) as a subprocess. The neon diagrams are rendered with it.

Pinned in vshort/neon/package.json (`npm ci` there); this wrapper only runs the local binary, never `npx` and so never
a newer release. hyperframes 0.8.206, from `hyperframes --version`. What `hyperframes render --help` offers and what we use:

    hyperframes render [DIR] -o <out.mp4> -f/--fps 30 [-q looks|draft|delivery] [-w auto|N] [--quiet] [--strict]
        DIR defaults to the cwd and must hold index.html; --format mp4 and -q looks (CRF 16) are the defaults.
        We pass --strict: a lint error (infinite repeat, Math.random...) then stops the render, and its text is printed on
        stdout, not stderr; the errors we raise carry the tail of both streams. Never --strict-all: warnings are left to pass.
        Size comes from the root's data-width/data-height (720x1280 stays 720x1280), length from data-duration.
    hyperframes validate [DIR] --json [--timeout ms]
        Loads the page in headless Chrome: {"ok", "errors": [{"level", "text", "url"}], "warnings", "contrast"}.
        Catches console errors, 404s on fonts/scripts and a throwing build script. "deprecated, use `check`" is printed
        on stderr; `check` also lints and inspects layout, so move to it only together with a version bump.

Render time of the 720x1280 gate composition (a ring and two captions; real scenes will be heavier), render() end to end:
    Mac (M2 Pro, 10 cores):          3 s -> 6.6 s     60 s -> 22.9 s
    pve2 (24 cores, 15 GB, software): 3 s -> 9.5 s     60 s -> 80.9 s   (~1.25 s per second of video + ~6 s fixed)
A 90 s video on pve2 is therefore about 120 s with the gate's content; 3 x that is 360 s, under the 600 s floor, so the
default timeout is 600 s. A scene heavy enough to need more passes its own timeout.

Browser: render uses chrome-headless-shell, not the Chrome you have installed. Order: $HYPERFRAMES_BROWSER_PATH, a shell
already under ~/.cache/hyperframes/chrome, else it downloads one (152.0.7977.30, 204 MB, ~40 s on the first render).
It also needs ffmpeg on PATH (both machines have it).

Our environment switches off what a pinned, unattended renderer should not do: anonymous telemetry, the update check
(it logs a self-upgrade attempt in ~/.hyperframes/auto-update.log) and installing agent skills. NO_COLOR keeps the error text plain.
"""
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

NEON = Path(__file__).resolve().parent / "neon"
_BIN = NEON / "node_modules" / ".bin" / "hyperframes"
FPS = 30
_GRACE = 5  # seconds a stopped render gets to clean up after SIGTERM, before SIGKILL
_ENV = {"HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1", "HYPERFRAMES_SKIP_SKILLS": "1", "NO_COLOR": "1"}


class HFError(Exception):
    """HyperFrames could not run or failed; the message is Vietnamese and ends with the last 20 lines of its stderr."""


def available() -> bool:
    return _BIN.exists()


def _stop(p: subprocess.Popen) -> tuple:
    """Stop the CLI and everything it started (they are one process group): SIGTERM first, since HyperFrames then closes its
    Chrome workers and removes their profile folders in /tmp and its work folders itself (SIGKILL leaves about 3 MB per worker);
    SIGKILL after _GRACE seconds, and for whatever is left once the leader is gone. Returns (stdout, stderr) as far as they got."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(p.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        p.wait(timeout=_GRACE)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(p.pid, signal.SIGKILL)
    try:
        return p.communicate(timeout=_GRACE)
    except subprocess.TimeoutExpired as e:  # something outside the group still holds the pipes: take what we have
        return e.stdout, e.stderr


def _run(args: list[str], comp_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    if not comp_dir.is_dir():
        raise HFError(f"Không thấy thư mục composition: {comp_dir}")
    if not available():
        raise HFError(f"Chưa cài HyperFrames: chạy `npm ci` trong {NEON}")
    try:  # its own session, so that a stop reaches every process it started: ffmpeg writes into the work folder after the node process is gone
        p = subprocess.Popen([str(_BIN), *args], cwd=comp_dir, env={**os.environ, **_ENV}, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as e:
        raise HFError(f"Không chạy được HyperFrames: {e}") from e
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        out, err = _stop(p)  # what it printed before the stop says where it stalled
        raise HFError(f"HyperFrames chạy quá {timeout} giây ({args[0]} {comp_dir}):\n{_said(out, err)}") from None
    except BaseException:  # Ctrl-C and the like: never leave a renderer running
        _stop(p)
        raise
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def _tail(text: str) -> str:
    """The last 20 lines, with terminal escape sequences (colours, cursor show/hide) removed."""
    return "\n".join(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text).strip().splitlines()[-20:])


def _said(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    """What the CLI printed: the tail of stdout, where `--strict` puts its reason, then the tail of stderr. Both, so noise on one
    (a Node deprecation warning) never hides the other; either may be bytes (after a timeout) or None."""
    parts = (_tail(x.decode(errors="replace") if isinstance(x, bytes) else x or "") for x in (stdout, stderr))
    return "\n".join(p for p in parts if p)


def _rm(path: Path) -> None:
    """Remove a folder and never raise: after a stop the last writer may still be dying, so try again briefly; what stays, stays."""
    for _ in range(5):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.2)


def render(comp_dir: Path, out: Path, timeout: int = 600) -> None:
    """Render comp_dir/index.html to out (silent H.264 MP4, FPS; a lint error is a failure, --strict). It renders in a scratch
    folder next to `out` and moves the file into place, so a failure or a timeout leaves neither `out` nor HyperFrames'
    half-done work files behind (and a clean-up that fails never replaces the HFError)."""
    scratch = Path(tempfile.mkdtemp(dir=out.parent, prefix=f".{out.stem}."))
    try:
        tmp = scratch / "render.mp4"
        cp = _run(["render", "-o", str(tmp), "--fps", str(FPS), "--strict"], comp_dir, timeout)
        if cp.returncode != 0 or not tmp.exists():
            raise HFError(f"HyperFrames render lỗi (mã {cp.returncode}):\n{_said(cp.stdout, cp.stderr)}")
        os.replace(tmp, out)
    finally:
        _rm(scratch)


def validate(comp_dir: Path, timeout: int = 120) -> list[str]:
    """The errors `hyperframes validate` finds in comp_dir (console errors, missing fonts/scripts); [] is clean."""
    cp = _run(["validate", "--json"], comp_dir, timeout)
    try:
        return [e["text"] for e in json.loads(cp.stdout)["errors"]]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HFError(f"HyperFrames validate không trả kết quả đọc được (mã {cp.returncode}):\n"
                      f"{_said(cp.stdout, cp.stderr)}") from None
