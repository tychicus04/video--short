import json
import shutil

from PIL import Image

from vshort.cli import main
from vshort.media import frame_at
from vshort.plates import Plate
from vshort.render import clean_video
from vshort.run import Run
from vshort.stills import pick_still, scene_of


def test_pick_still_prefers_the_fully_drawn_frame(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "drawn")], captions=[])
    assert 1.0 <= pick_still(v, 0.0, 2.0, []) < 2.0


def test_pick_still_widens_from_a_blank_window(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "drawn"), (2, 3, "#202020")], captions=[])
    assert 1.0 <= pick_still(v, 0.0, 0.8, [2.0]) < 2.0  # window is blank paper; same scene, not the next one


def test_pick_still_skips_the_frames_right_after_a_cut(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#F3EFE6"), (1, 2, "flash")], captions=[])
    assert pick_still(v, 1.0, 2.0, [1.0]) >= 1.25  # the checkerboard at 1.0-1.2 scores highest but is a transition


def test_scene_of():
    assert [scene_of(t, [1.0, 2.5]) for t in (0, 0.99, 1.0, 2.4, 2.5, 9)] == [0, 0, 1, 1, 2, 2]


def test_stills_cmd_one_still_per_spoken_line(make_video, tmp_path):
    run = tmp_path / "run"
    (run / "plates").mkdir(parents=True)
    shutil.copy(make_video(tmp_path, scenes=[(0, 3, "drawn")], captions=[]), run / "source.mp4")
    (run / "plates" / "plates.json").write_text("[]")
    (run / "sentences.en.json").write_text(json.dumps(
        [{"id": i, "start": i - 1, "end": i, "en": "x."} for i in (1, 2, 3)]))
    (run / "script.vi.json").write_text(json.dumps(
        [{"id": 1, "phrases": "a"}, {"id": 2, "phrases": ""}, {"id": 3, "phrases": "b"}]))
    assert main(["stills", str(run)]) == 0
    rows = json.loads((run / "stills.json").read_text())
    assert [r["id"] for r in rows] == [1, 3] and all(r["scene"] == 0 for r in rows)
    assert 1.0 <= rows[0]["t"] < 2.0 and 2.0 <= rows[1]["t"] < 3.0
    for i in (1, 3):
        assert Image.open(run / "stills" / f"{i}.png").size == (720, 1280)
        assert Image.open(run / "stills" / "grid" / f"{i}.png").size == (720, 1280)
    assert not (run / "stills" / "2.png").exists()
    assert (run / "stills" / "sheet.png").exists() and (run / "clean.mp4").exists()
    assert Run(run).done("stills")


def test_plate_applies_from_its_first_frame(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000")], captions=[])
    Image.new("RGB", (50, 50), "white").save(tmp_path / "p00.png")
    plates = [Plate("p00", 100, 100, 0.0667, 0.5, "clean", False)]  # as build_plates rounds frame 2 (2/30 s)
    out = tmp_path / "o.mp4"
    clean_video(v, plates, tmp_path, end=1.0, out=out)
    assert frame_at(out, 2 / 30)[125, 125].min() > 200 and frame_at(out, 1 / 30)[125, 125].max() < 60


def test_stills_cmd_refuses_to_run_without_plates(tmp_path, capsys):
    assert main(["stills", str(tmp_path)]) == 2  # the old English captions would be baked into every still
    err = capsys.readouterr().err
    assert "thiếu plates/plates.json" in err and "chạy `vshort plates` trước" in err
    assert not (tmp_path / "clean.mp4").exists() and not Run(tmp_path).done("stills")
