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
    except subprocess.TimeoutExpired:
        raise HFError(f"HyperFrames chạy quá {timeout} giây ({args[0]} {comp_dir})") from None
    except OSError as e:
        raise HFError(f"Không chạy được HyperFrames: {e}") from e


def _tail(cp: subprocess.CompletedProcess) -> str:
    return "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", cp.stderr or cp.stdout).strip().splitlines()[-20:])


def render(comp_dir: Path, out: Path, timeout: int = 1800) -> None:
    """Render comp_dir/index.html to out (silent H.264 MP4, FPS). Written to <out>.tmp.mp4 first and moved into place, so
    a failure never leaves `out` behind."""
    tmp = out.with_suffix(".tmp.mp4").resolve()  # absolute: HyperFrames runs with cwd=comp_dir
    try:
        cp = _run(["render", "-o", str(tmp), "--fps", str(FPS)], comp_dir, timeout)
        if cp.returncode != 0 or not tmp.exists():
            raise HFError(f"HyperFrames render lỗi (mã {cp.returncode}):\n{_tail(cp)}")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def validate(comp_dir: Path, timeout: int = 120) -> list[str]:
    """The errors `hyperframes validate` finds in comp_dir (console errors, missing fonts/scripts); [] is clean."""
    cp = _run(["validate", "--json"], comp_dir, timeout)
    try:
        return [e["text"] for e in json.loads(cp.stdout)["errors"]]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HFError(f"HyperFrames validate không trả kết quả đọc được (mã {cp.returncode}):\n{_tail(cp)}") from None
