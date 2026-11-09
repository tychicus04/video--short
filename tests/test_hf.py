import shutil
from pathlib import Path

import pytest

from vshort import hf
from vshort.media import frame_at, probe

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not hf.available(), reason="chưa cài vshort/neon (npm ci)")


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


def test_gate_is_valid(tmp_path):
    assert hf.validate(copy_gate(tmp_path)) == []


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


def test_hyperframes_failure_is_hferror_and_leaves_nothing(tmp_path):
    empty, out = tmp_path / "empty", tmp_path / "x.mp4"  # a folder with no index.html: HyperFrames itself exits non-zero
    empty.mkdir()
    with pytest.raises(hf.HFError):
        hf.render(empty, out)
    assert list(tmp_path.glob("x*")) == []
