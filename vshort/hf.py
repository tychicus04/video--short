"""HyperFrames (HTML + GSAP composition -> MP4) as a subprocess. The neon diagrams are rendered with it.

Pinned in vshort/neon/package.json (`npm ci` there); this wrapper only runs the local binary, never `npx` and so never
a newer release. hyperframes 0.8.206, from `hyperframes --version`. What `hyperframes render --help` offers and what we use:

    hyperframes render [DIR] -o <out.mp4> -f/--fps 30 [-q looks|draft|delivery] [-w auto|N] [--quiet] [--strict]
        DIR defaults to the cwd and must hold index.html; --format mp4 and -q looks (CRF 16) are the defaults.
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
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

NEON = Path(__file__).resolve().parent / "neon"
_BIN = NEON / "node_modules" / ".bin" / "hyperframes"
FPS = 30
_ENV = {"HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1", "HYPERFRAMES_SKIP_SKILLS": "1", "NO_COLOR": "1"}


class HFError(Exception):
    """HyperFrames could not run or failed; the message is Vietnamese and ends with the last 20 lines of its stderr."""


def available() -> bool:
    return _BIN.exists()


def _run(args: list[str], comp_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    if not comp_dir.is_dir():
        raise HFError(f"Không thấy thư mục composition: {comp_dir}")
    if not available():
        raise HFError(f"Chưa cài HyperFrames: chạy `npm ci` trong {NEON}")
    try:  # killed on a timeout, it takes its Chrome workers with it (they exit when the pipe to the parent closes)
        return subprocess.run([str(_BIN), *args], cwd=comp_dir, env={**os.environ, **_ENV}, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:  # what it printed before the kill says where it stalled; it arrives as bytes even with text=True
        seen = (e.stderr or e.stdout or b"").decode(errors="replace")
        raise HFError(f"HyperFrames chạy quá {timeout} giây ({args[0]} {comp_dir}):\n{_tail(seen)}") from None
    except OSError as e:
        raise HFError(f"Không chạy được HyperFrames: {e}") from e


def _tail(text: str) -> str:
    """The last 20 lines, with terminal escape sequences (colours, cursor show/hide) removed."""
    return "\n".join(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text).strip().splitlines()[-20:])


def render(comp_dir: Path, out: Path, timeout: int = 600) -> None:
    """Render comp_dir/index.html to out (silent H.264 MP4, FPS). It renders in a scratch folder next to `out` and moves
    the file into place, so a failure or a timeout leaves neither `out` nor HyperFrames' half-done work files behind."""
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=f".{out.stem}.") as scratch:
        tmp = Path(scratch) / "render.mp4"
        cp = _run(["render", "-o", str(tmp), "--fps", str(FPS)], comp_dir, timeout)
        if cp.returncode != 0 or not tmp.exists():
            raise HFError(f"HyperFrames render lỗi (mã {cp.returncode}):\n{_tail(cp.stderr or cp.stdout)}")
        os.replace(tmp, out)


def validate(comp_dir: Path, timeout: int = 120) -> list[str]:
    """The errors `hyperframes validate` finds in comp_dir (console errors, missing fonts/scripts); [] is clean."""
    cp = _run(["validate", "--json"], comp_dir, timeout)
    try:
        return [e["text"] for e in json.loads(cp.stdout)["errors"]]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HFError(f"HyperFrames validate không trả kết quả đọc được (mã {cp.returncode}):\n{_tail(cp.stderr or cp.stdout)}") from None
