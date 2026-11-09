import os
import shutil
import time
from pathlib import Path

import pytest

from vshort import hf
from vshort.media import frame_at, probe

ROOT = Path(__file__).resolve().parent.parent
needs_hf = pytest.mark.skipif(not hf.available(), reason="chưa cài vshort/neon (npm ci)")  # the fake-CLI tests below run without it


def copy_gate(tmp_path: Path, duration: int = 3) -> Path:
    """tests/data/hf_gate plus the three fonts and gsap.min.js, in a fresh folder; `duration` rewrites GATE.duration."""
    gate = tmp_path / "gate"
    shutil.copytree(ROOT / "tests" / "data" / "hf_gate", gate)
    for font in ("BeVietnamPro-Bold", "BeVietnamPro-ExtraBold", "IBMPlexMono-SemiBold"):
        shutil.copy(ROOT / "assets" / "fonts" / f"{font}.ttf", gate)
    shutil.copy(hf.NEON / "node_modules" / "gsap" / "dist" / "gsap.min.js", gate)
    page = gate / "index.html"
    html = page.read_text()
    assert '"duration": 3,' in html
    page.write_text(html.replace('"duration": 3,', f'"duration": {duration},'))
    return gate


@needs_hf
def test_gate_is_valid(tmp_path):
    assert hf.validate(copy_gate(tmp_path)) == []


@needs_hf
def test_gate_renders_three_seconds(tmp_path):
    out = tmp_path / "gate.mp4"
    hf.render(copy_gate(tmp_path), out)
    info = probe(out)
    assert (info.width, info.height) == (720, 1280) and abs(info.duration - 3.0) < 0.05
    early = frame_at(out, 0.2)  # the timeline moves: the ring is not drawn yet, the words are not there yet
    assert (early[560:720, 280:440, 2] > 200).sum() < 50 and (early[1050:1110, 100:620].max(axis=2) > 200).sum() < 50
    f = frame_at(out, 2.5)
    assert (f[560:720, 280:440, 2] > 200).sum() > 500  # vòng xanh dương đã vẽ
    assert (f[1050:1110, 100:620].max(axis=2) > 200).sum() > 300  # chữ trắng có mặt


def test_failed_render_leaves_no_output(tmp_path):
    out = tmp_path / "x.mp4"
    with pytest.raises(hf.HFError):
        hf.render(tmp_path / "khong-co", out)
    assert not out.exists()


@needs_hf
def test_hyperframes_failure_is_hferror_and_leaves_nothing(tmp_path):
    empty = tmp_path / "empty"  # a folder with no index.html: HyperFrames itself exits non-zero
    empty.mkdir()
    with pytest.raises(hf.HFError):
        hf.render(empty, tmp_path / "x.mp4")
    assert [p.name for p in tmp_path.iterdir()] == ["empty"]


@needs_hf
def test_timeout_is_hferror_and_leaves_nothing(tmp_path):
    gate = copy_gate(tmp_path, duration=60)  # far more than 5 s of work
    with pytest.raises(hf.HFError, match="quá 5 giây") as e:
        hf.render(gate, tmp_path / "x.mp4", timeout=5)
    assert [p.name for p in tmp_path.iterdir()] == ["gate"]
    lines = str(e.value).splitlines()  # the header, then what HyperFrames had printed (where it stalled), without escapes
    assert len(lines) > 2 and "\x1b" not in str(e.value)


@needs_hf
def test_validate_catches_a_missing_script(tmp_path):
    gate = copy_gate(tmp_path)
    (gate / "gsap.min.js").unlink()  # the page still asks for it: a 404, then a throwing build script
    errors = hf.validate(gate)
    assert any("gsap.min.js" in e for e in errors) and any("timeline" in e for e in errors)


@needs_hf
def test_a_lint_error_blocks_the_render(tmp_path):
    gate = copy_gate(tmp_path)
    page = gate / "index.html"
    html = page.read_text()
    assert 'ease: "power2.inOut" }, 0.5);' in html
    page.write_text(html.replace('ease: "power2.inOut" }, 0.5);', 'ease: "power2.inOut", repeat: -1 }, 0.5);'))  # infinite repeat
    with pytest.raises(hf.HFError, match="gsap_infinite_repeat"):
        hf.render(gate, tmp_path / "x.mp4", timeout=120)
    assert [p.name for p in tmp_path.iterdir()] == ["gate"]


# ---- what HyperFrames says reaches the error, from both streams: `--strict` prints its reason on stdout, and any noise on stderr
# (a Node deprecation warning on pve2) must not hide it. Faked with a script that says the same on each.

NOISE, REASON = "(node:1) [DEP0040] DeprecationWarning: noise-on-stderr", "x gsap_infinite_repeat: reason-on-stdout"


def fake_cli(tmp_path, monkeypatch, tail: str) -> Path:
    script = tmp_path / "hyperframes"
    script.write_text(f"#!/bin/sh\necho '{NOISE}' >&2\necho '{REASON}'\n{tail}\n")
    script.chmod(0o755)
    monkeypatch.setattr(hf, "_BIN", script)
    comp = tmp_path / "comp"
    comp.mkdir()
    return comp


def test_a_failed_render_shows_stdout_and_stderr(tmp_path, monkeypatch):
    comp = fake_cli(tmp_path, monkeypatch, "exit 1")
    with pytest.raises(hf.HFError) as e:
        hf.render(comp, tmp_path / "x.mp4")
    assert REASON in str(e.value) and NOISE in str(e.value)
    assert str(e.value).index(REASON) < str(e.value).index(NOISE)  # stdout's tail, then stderr's


def test_a_validate_that_prints_no_json_shows_stdout_and_stderr(tmp_path, monkeypatch):
    comp = fake_cli(tmp_path, monkeypatch, "exit 1")
    with pytest.raises(hf.HFError) as e:
        hf.validate(comp)
    assert REASON in str(e.value) and NOISE in str(e.value)


def test_a_timeout_shows_what_both_streams_had_said(tmp_path, monkeypatch):
    comp = fake_cli(tmp_path, monkeypatch, "exec sleep 30")  # exec: the shell is the one killed, nothing keeps the pipes open
    with pytest.raises(hf.HFError, match="quá 2 giây") as e:
        hf.render(comp, tmp_path / "x.mp4", timeout=2)
    assert REASON in str(e.value) and NOISE in str(e.value)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.parametrize("stubborn", [False, True], ids=["stops on SIGTERM", "ignores SIGTERM"])
def test_a_timeout_stops_what_the_cli_started_and_leaves_nothing(tmp_path, monkeypatch, stubborn):
    # Like HyperFrames' ffmpeg: a child in the CLI's process group that keeps writing into the folder `-o` points at (HyperFrames
    # keeps its work files there). Killing only the CLI leaves it writing while the clean-up removes the folder: OSError.
    pidfile, stop, outdir = tmp_path / "child.pid", tmp_path / "stop", tmp_path / "out"
    outdir.mkdir()
    comp = fake_cli(tmp_path, monkeypatch, f"""{'trap "" TERM' if stubborn else ''}
d=$(dirname "$3")
( i=0; while [ ! -e {stop} ]; do : > "$d/w$((i % 200))" 2>/dev/null; i=$((i+1)); done ) &
echo $! > {pidfile}
exec sleep 30""")
    monkeypatch.setattr(hf, "_GRACE", 0.5 if stubborn else 30)  # 30: were SIGTERM not enough, the test would visibly hang
    t = time.monotonic()
    try:
        with pytest.raises(hf.HFError, match="quá 2 giây") as e:
            hf.render(comp, outdir / "x.mp4", timeout=2)
    finally:
        stop.touch()  # whatever happened, the child ends
    assert time.monotonic() - t < 10 and REASON in str(e.value)
    assert list(outdir.iterdir()) == []
    pid, deadline = int(pidfile.read_text()), time.monotonic() + 3
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(pid)


def test_a_clean_up_that_cannot_finish_does_not_replace_the_error(tmp_path, monkeypatch):
    comp = fake_cli(tmp_path, monkeypatch, 'mkdir "$(dirname "$3")/locked" && : > "$(dirname "$3")/locked/f" && chmod 000 "$(dirname "$3")/locked"; exit 1')
    try:
        with pytest.raises(hf.HFError, match="mã 1"):  # not an OSError from removing a folder it cannot enter
            hf.render(comp, tmp_path / "x.mp4")
    finally:
        for locked in tmp_path.glob(".x.*/locked"):
            locked.chmod(0o700)
