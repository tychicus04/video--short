import json

import pytest

from vshort import motion
from vshort.motion import clashes, load

WORDS = motion.brief_words("**Cơ chế:** kẻ tấn công gửi gói tin tới máy chủ; bộ nhớ (memory) nứt.")


@pytest.fixture
def design(tmp_path):
    (tmp_path / "shapes").mkdir()
    (tmp_path / "shapes" / "bo-nho.json").write_text(json.dumps(
        {"name": "bộ nhớ", "strokes": [[[0, 0], [100, 0], [100, 60], [0, 60], [0, 0]], [[0, 30], [100, 30]]]}))
    return {"note": "n", "idea": "gói tin làm nứt bộ nhớ", "actor": "atk",
            "things": [
                {"id": "atk", "kind": "dot", "xy": [120, 300], "label": "kẻ tấn công", "beat": 1},
                {"id": "srv", "kind": "server", "box": [400, 200, 640, 420], "label": "máy chủ", "beat": 1, "at": 0.3},
                {"id": "mem", "kind": "shape", "shape": "bo-nho", "box": [400, 600, 640, 760], "label": "bộ nhớ",
                 "beat": 2}],
            "beats": [
                {"idea": "gói tin tới máy chủ", "acts": [{"do": "move", "thing": "atk", "to": [520, 310], "at": 0.5}]},
                {"idea": "bộ nhớ lộ ra", "acts": [{"do": "move", "thing": "atk", "to": [520, 680], "at": 0.4}]},
                {"idea": "máy chủ bị chiếm", "acts": [{"do": "red", "thing": "srv", "at": 0.2}]}]}


def test_brief_words_drop_marks():
    assert {"cơ", "chế", "memory", "nứt", "chủ"} <= WORDS and "**cơ" not in WORDS


def test_design_ok_and_actor_rules(design, tmp_path):
    assert motion.design_problems(design, WORDS, tmp_path) == []
    bad = design | {"beats": design["beats"] + [{"idea": "x", "acts": [{"do": "hide", "thing": "atk", "at": 0}]}]}
    assert any("actor" in p for p in motion.design_problems(bad, WORDS, tmp_path))
    late = json.loads(json.dumps(design))
    late["things"][0]["beat"] = 2
    assert any("actor" in p for p in motion.design_problems(late, WORDS, tmp_path))


def test_more_than_seven_things_is_clutter(design, tmp_path):
    design["things"] += [{"id": f"b{k}", "kind": "box", "box": [60, 500, 340, 600], "label": "dữ liệu", "beat": 3}
                         for k in range(5)]
    assert any("tối đa 7" in p for p in motion.design_problems(design, WORDS, tmp_path))


def test_more_than_six_beats_rejected(design, tmp_path):
    design["beats"] = [{"idea": "x", "acts": []}] * 7
    assert any("1–6" in p for p in motion.design_problems(design, WORDS, tmp_path))


def test_unknown_shape_rejected(design, tmp_path):
    design["things"][2]["shape"] = "khong-co"
    assert any("khong-co" in p for p in motion.design_problems(design, WORDS, tmp_path))


def test_label_word_outside_brief_rejected(design, tmp_path):
    design["things"][1]["label"] = "chữ lạ"
    assert any("'lạ'" in p for p in motion.design_problems(design, WORDS, tmp_path))


def test_thing_beat_must_exist(design, tmp_path):
    design["things"][2]["beat"] = 4
    assert any("beat" in p for p in motion.design_problems(design, WORDS, tmp_path))


def test_old_format_is_rejected_plainly(tmp_path):
    probs = motion.design_problems({"lines": [1], "note": "n", "scenes": []}, WORDS, tmp_path)
    assert probs == ["motion.json dạng cũ (scenes): viết lại theo dạng nhịp (beats)"]


def test_timed_puts_each_beat_on_its_start(design, tmp_path):
    sc = motion.timed(design, [0.0, 3.0, 6.0], 9.0, tmp_path)
    draws = {a.thing: a.t0 for a in sc.acts if a.do == "draw"}
    assert draws["atk"] == pytest.approx(-motion.LEAD_IN) and draws["srv"] == pytest.approx(0.9)
    assert draws["mem"] == pytest.approx(3.0)
    moves = [a.t0 for a in sc.acts if a.do == "move"]
    assert moves == pytest.approx([1.5, 4.2])
    mem = next(th for th in sc.things if th["id"] == "mem")
    assert len(mem["strokes"]) == 2 and min(x for s in mem["strokes"] for x, _ in s) >= 400


def test_earlier_beat_dims_and_comes_back(design, tmp_path):
    sc = motion.timed(design, [0.0, 3.0, 6.0], 9.0, tmp_path)
    dims = [(a.do, a.thing) for a in sc.acts if a.do in ("dim", "undim")]
    assert ("dim", "srv") in dims and ("undim", "srv") in dims  # nhịp 3 có act "red" trên srv
    assert ("dim", "mem") in dims
    assert all(t != "atk" for _, t in dims)


def test_design_sheet_has_one_column_per_beat(design, tmp_path):
    img = motion.design_sheet(design, tmp_path)
    assert img.width > 3 * motion.SHEET_W


def test_reference_on_an_animated_line_clashes():
    refs = [{"kind": "svg", "id": 9, "file": "visuals/a.svg"}, {"kind": "svg", "id": 4, "file": "visuals/b.svg"},
            {"kind": "patch", "ids": [8, 9]}]
    assert [p for p in clashes(refs, {7, 8, 9}) if "9" in p]
    assert not [p for p in clashes(refs, {7, 8, 9}) if "4" in p]


def test_load_treats_null_and_missing_as_no_animation(tmp_path):
    assert load(tmp_path / "motion.json") is None
    (tmp_path / "motion.json").write_text("null")
    assert load(tmp_path / "motion.json") is None
    (tmp_path / "motion.json").write_text("{oops")
    with pytest.raises(ValueError):
        load(tmp_path / "motion.json")
