import json

import pytest

from vshort import camera, kit, motion
from vshort.fit import phrase_fracs
from vshort.motion import clashes, estimate, load

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
    late = json.loads(json.dumps(design))  # the attacker comes in when the voice brings him in (reviewer 03/11)
    late["things"][0]["beat"] = 3
    late["beats"][0]["acts"], late["beats"][1]["acts"] = [{"do": "red", "thing": "srv", "at": 0.6}], []
    late["beats"][2]["acts"] = [{"do": "move", "thing": "atk", "to": [520, 680], "at": 0.3}]
    assert not any("actor" in p for p in motion.design_problems(late, WORDS, tmp_path))


def test_the_actor_may_enter_after_the_normal_beat(design, tmp_path):
    d = json.loads(json.dumps(design))  # beat 1 tells how it should work; the attacker comes in at beat 2
    d["things"][0]["beat"] = 2
    d["beats"][0]["acts"] = [{"do": "red", "thing": "srv", "at": 0.6}]
    assert not any("actor" in p for p in motion.design_problems(d, WORDS, tmp_path))


def test_carried_things_do_not_count_as_clutter(design, tmp_path):
    design["things"] += [{"id": f"b{k}", "kind": "box", "box": [60, 500 + 60 * k, 340, 550 + 60 * k], "label": "dữ liệu",
                          "beat": 3} for k in range(4)]  # 7 in view
    design["things"].append({"id": "k", "kind": "icon", "icon": "key", "xy": [520, 680], "beat": 3})
    assert any("tối đa 7" in p for p in motion.design_problems(design, WORDS, tmp_path))
    design["beats"][2]["acts"].append({"do": "attach", "thing": "k", "on": "atk", "offset": [0, 0], "at": 0})
    assert not any("tối đa 7" in p for p in motion.design_problems(design, WORDS, tmp_path))


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


SCRIPT = [{"id": i, "phrases": p, "note": ""} for i, p in enumerate([
    "Lỗi mới trong nhân Linux",
    "Ai cũng nên biết | chuyện này",
    "Bản vá đã có | từ tuần trước",
    "Kẻ tấn công gửi | gói tin tới máy chủ.",
    "Trong máy chủ | lộ ra bộ nhớ.",
    "Máy chủ | bị chiếm.",
    "Hãy cập nhật hệ điều hành | ngay hôm nay | để không bị ảnh hưởng.",
    "Nhà cung cấp đã phát hành | bản vá cho mọi phiên bản | đang được hỗ trợ.",
    "Theo dõi để biết thêm | về an ninh mạng mỗi ngày.",
], 1)]
BIND = {"lines": [4, 5, 6], "note": "n", "beats": [{"line": 4}, {"line": 5, "phrase": 2}, {"line": 6}]}


def _start(line, phrase=1, at=0.0):
    p = next(p for p in estimate(SCRIPT) if p.id == line)
    f0, f1 = phrase_fracs(SCRIPT[line - 1]["phrases"])[phrase - 1]
    return p.start + p.dur * (f0 + (f1 - f0) * at)


def test_bind_ok(design, tmp_path):
    assert motion.bind_problems(design, BIND, SCRIPT, tmp_path) == []


def test_bind_rejects_out_of_order_beats(design, tmp_path):
    b = BIND | {"beats": [{"line": 4}, {"line": 6}, {"line": 5}]}
    assert any("tăng dần" in p for p in motion.bind_problems(design, b, SCRIPT, tmp_path))


def test_fewer_than_two_beats_left_is_an_error(design, tmp_path):
    b = BIND | {"beats": [{"line": 4}, None, None]}
    assert any("ít nhất 2" in p for p in motion.bind_problems(design, b, SCRIPT, tmp_path))


def test_first_kept_beat_must_open_the_stretch(design, tmp_path):
    b = BIND | {"beats": [None, {"line": 5}, {"line": 6}]}
    assert any("câu 4" in p for p in motion.bind_problems(design, b, SCRIPT, tmp_path))


def test_bind_needs_one_cue_per_beat_inside_its_lines(design, tmp_path):
    assert any("3 phần tử" in p for p in motion.bind_problems(design, BIND | {"beats": [{"line": 4}]}, SCRIPT, tmp_path))
    b = BIND | {"beats": [{"line": 4}, {"line": 5}, {"line": 7}]}
    assert any("7" in p for p in motion.bind_problems(design, b, SCRIPT, tmp_path))
    b = BIND | {"beats": [{"line": 4}, {"line": 5, "phrase": 3}, {"line": 6}]}
    assert any("phrase" in p for p in motion.bind_problems(design, b, SCRIPT, tmp_path))


def test_bind_lines_rules(design, tmp_path):
    assert any("tiêu đề" in p for p in motion.bind_problems(design, BIND | {"lines": [1, 2, 3, 4, 5, 6]}, SCRIPT,
                                                           tmp_path))
    assert any("liền nhau" in p for p in motion.bind_problems(design, BIND | {"lines": [4, 6]}, SCRIPT, tmp_path))
    refs = [{"kind": "svg", "id": 5, "file": "visuals/a.svg"}]
    assert any("câu 5" in p for p in motion.bind_problems(design, BIND, SCRIPT, tmp_path, refs))


def test_labels_override_must_use_spoken_words(design, tmp_path):
    assert any("'vùng'" in p for p in motion.bind_problems(design, BIND | {"labels": {"mem": "vùng nhớ"}}, SCRIPT,
                                                          tmp_path))
    assert motion.bind_problems(design, BIND | {"labels": {"mem": "nhớ"}}, SCRIPT, tmp_path) == []
    design["things"][2]["label"] = "chỗ chứa"  # a brief word the voice never says
    assert any("'chứa'" in p for p in motion.bind_problems(design, BIND, SCRIPT, tmp_path))
    assert motion.bound(design, BIND | {"labels": {"mem": "bộ nhớ"}})["things"][2]["label"] == "bộ nhớ"


def test_bind_timed_puts_beats_on_their_cues(design, tmp_path):
    sc = motion.bind_timed(design, BIND, estimate(SCRIPT), SCRIPT, tmp_path)
    draws = {a.thing: a.t0 for a in sc.acts if a.do == "draw"}
    assert draws["mem"] == pytest.approx(_start(5, 2) - motion.LEAD_WORD) and sc.lines == [4, 5, 6]


def test_dropped_beat_things_appear_with_next_beat(design, tmp_path):
    b = BIND | {"beats": [{"line": 4}, None, {"line": 6}]}
    sc = motion.bind_timed(design, b, estimate(SCRIPT), SCRIPT, tmp_path)
    t_beat3 = _start(6)
    assert all(a.t0 >= t_beat3 - motion.LEAD_IN for a in sc.acts if a.thing == "mem" and a.do == "draw")
    assert [a for a in sc.acts if a.thing == "mem" and a.do == "draw"]
    assert not [a for a in sc.acts if a.do == "move" and a.to == (520, 680)]


def test_things_of_dropped_last_beats_are_not_drawn(design, tmp_path):
    design["things"][2]["beat"] = 3
    sc = motion.timed(design, [0.0, 3.0, None], 9.0, tmp_path)
    assert "mem" not in {th["id"] for th in sc.things} and not [a for a in sc.acts if a.thing == "mem"]


def test_bind_sheet_has_a_column_per_kept_beat(design, tmp_path):
    img = motion.bind_sheet(design, BIND | {"beats": [{"line": 4}, None, {"line": 6}]}, SCRIPT, tmp_path)
    assert 2 * motion.SHEET_W < img.width < 3 * motion.SHEET_W


def test_a_dropped_move_that_leaves_the_actor_off_its_next_path_is_reported(design, tmp_path):
    design["things"].append({"id": "p2", "kind": "path", "points": [[520, 310], [520, 680]], "beat": 2})
    design["beats"][1]["acts"] = [{"do": "move", "thing": "atk", "path": "p2", "at": 0.4}]
    assert motion.bind_problems(design, BIND, SCRIPT, tmp_path) == []
    b = BIND | {"beats": [{"line": 4}, {"line": 5}, None]}
    assert motion.bind_problems(design, b, SCRIPT, tmp_path) == []
    b = BIND | {"beats": [{"line": 4}, None, {"line": 6}]}  # fine: beat 3 has no path move
    assert motion.bind_problems(design, b, SCRIPT, tmp_path) == []
    design["beats"][0]["acts"] = []  # the dot never reaches the start of p2
    assert any("nhảy" in p for p in motion.bind_problems(design, BIND, SCRIPT, tmp_path))


def test_bind_survives_a_thing_id_that_is_not_a_string(design, tmp_path):
    design["things"][1]["id"] = ["srv"]
    assert motion.bind_problems(design, BIND, SCRIPT, tmp_path)


def test_ui_problems_keep_the_canvas_clear_of_the_platforms():
    doc = {"things": [{"id": "a", "kind": "box", "box": [60, 300, 680, 500], "label": "A", "beat": 1},  # wide, above the buttons
                      {"id": "b", "kind": "box", "box": [60, 600, 640, 800], "beat": 1},  # into the button column
                      {"id": "c", "kind": "box", "box": [60, 100, 300, 200], "beat": 1},  # under the top bar
                      {"id": "d", "kind": "dot", "xy": [300, 900], "beat": 1}],
           "beats": [{"acts": [{"do": "move", "thing": "d", "to": [650, 900]}]}]}
    assert [p.split(":")[0] for p in motion.ui_problems(doc)] == ["thing 'b'", "thing 'c'", "nhịp 1"]
    shape = {"things": [{"id": "s", "kind": "shape", "shape": "x", "box": [100, 600, 200, 700], "beat": 1}],
             "beats": [{"acts": [{"do": "move", "thing": "s", "to": [600, 650]}]}]}  # moves by its box's centre
    assert [p.split(":")[0] for p in motion.ui_problems(shape)] == ["nhịp 1"]


def test_timed_scene_ends_on_the_full_canvas(design, tmp_path):
    sc = motion.timed(design, *motion.estimated(design), tmp_path)
    assert len(sc.cams) == 1 + 2 * (len(design["beats"]) - 1) + 2
    assert sc.cams[-1][1:] == kit.FULL


def test_camera_focus_covers_where_a_mover_goes(design, tmp_path):
    sc = motion.timed(design, *motion.estimated(design), tmp_path)
    v = camera.at(sc.cams, 5.0)  # mid beat 2: atk has reached (520, 680)
    x, y = kit.screen(v, 520, 680)
    assert kit.SAFE[0] <= x <= kit.SAFE[2] and kit.SAFE[1] <= y <= kit.SAFE[3]
    assert v[2] > 1.0


def test_beat_view_overrides_and_is_checked(design, tmp_path):
    ok = json.loads(json.dumps(design))
    ok["beats"][0]["view"] = [100, 200, 400, 500]
    assert motion.design_problems(ok, WORDS, tmp_path) == []
    assert motion.timed(ok, *motion.estimated(ok), tmp_path).cams[0][1:] == camera.view((100, 200, 400, 500))
    bad = json.loads(json.dumps(design))
    bad["beats"][0]["view"] = [0, 0, 10, 10]
    assert any("view" in p for p in motion.design_problems(bad, WORDS, tmp_path))


def test_attach_rules(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["beats"][0]["acts"].append({"do": "attach", "thing": "srv", "on": "atk", "offset": [0, 0], "at": 0.6})
    assert any("attach" in p for p in motion.design_problems(d, WORDS, tmp_path))
    d = json.loads(json.dumps(design))
    d["things"] += [{"id": "k1", "kind": "icon", "icon": "key", "xy": [150, 600], "beat": 1},
                    {"id": "k2", "kind": "icon", "icon": "lock", "xy": [300, 600], "beat": 1}]
    d["beats"][0]["acts"].append({"do": "attach", "thing": "k1", "on": "k2", "offset": [0, 0], "at": 0.6})
    d["beats"][1]["acts"].append({"do": "attach", "thing": "k2", "on": "k1", "offset": [0, 0], "at": 0.6})
    assert any("vòng" in p for p in motion.design_problems(d, WORDS, tmp_path))


def test_figure_can_be_the_actor(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"][0] = {"id": "atk", "kind": "figure", "role": "attacker", "xy": [160, 300], "label": "kẻ tấn công",
                      "beat": 1}
    assert [p for p in motion.design_problems(d, WORDS, tmp_path) if "đè" not in p] == []
    d["things"][0]["role"] = "wizard"  # (a figure walking into the server box trips the overlap rule: not this test)
    assert any("role" in p for p in motion.design_problems(d, WORDS, tmp_path))


def test_open_needs_a_hinged_shape(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["beats"][2]["acts"].append({"do": "open", "thing": "mem", "at": 0.5})
    assert any("hinge" in p for p in motion.design_problems(d, WORDS, tmp_path))
    (tmp_path / "shapes" / "barie-thu.json").write_text(json.dumps(
        {"name": "barie", "strokes": [[[0, 50], [100, 50]], [[0, 40], [0, 100]]],
         "hinge": {"strokes": [0], "pivot": [0, 50], "turn": -80}}))
    d["things"][2]["shape"] = "barie-thu"
    assert motion.design_problems(d, WORDS, tmp_path) == []
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    assert next(th for th in sc.things if th["id"] == "mem")["hinge"]["turn"] == -80


def test_metaphor_words_may_label_but_not_mean(design, tmp_path):
    (tmp_path / "an-du.md").write_text("cổng soát vé = chứng chỉ")  # "soát", "vé" are not in COMMON
    d = json.loads(json.dumps(design))
    d["things"][1]["label"] = "soát vé"
    assert motion.design_problems(d, WORDS, tmp_path) == []
    d["things"][1]["means"] = "chứng chỉ"  # in an-du.md, not in WORDS
    assert any("means" in p for p in motion.design_problems(d, WORDS, tmp_path))
    d["things"][1]["means"] = "bộ nhớ"
    assert motion.design_problems(d, WORDS, tmp_path) == []


def test_missing_metaphor_file_adds_no_words(tmp_path):
    assert motion._metaphor(tmp_path) == set() and motion._metaphor(None) == set()


def test_means_needs_a_label(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"][1] = {k: v for k, v in d["things"][1].items() if k != "label"} | {"means": "bộ nhớ"}
    assert any("means" in p for p in motion.design_problems(d, WORDS, tmp_path))


def test_timed_adds_plain_at_the_next_kept_beat(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"][1]["means"] = "bộ nhớ"
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    assert [(a.thing, a.t0) for a in sc.acts if a.do == "plain"] == [("srv", 3.0)]


def test_bind_means_override(design, tmp_path):
    design["things"][1]["means"] = "nứt"  # a brief word the voice never says
    assert any("'nứt'" in p for p in motion.bind_problems(design, BIND, SCRIPT, tmp_path))
    assert motion.bind_problems(design, BIND | {"means": {"srv": ""}}, SCRIPT, tmp_path) == []
    assert motion.bind_problems(design, BIND | {"means": {"srv": "bộ nhớ"}}, SCRIPT, tmp_path) == []
    assert "means" not in motion.bound(design, BIND | {"means": {"srv": ""}})["things"][1]
    assert any("means" in p for p in motion.bind_problems(design, BIND | {"means": {"mem": "x"}}, SCRIPT, tmp_path))



def test_a_quiet_stretch_is_reported(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["beats"][1]["acts"] = []  # beat 2 only draws mem: ~2.2 s with nothing moving
    assert any("không có gì chuyển động" in p for p in motion.design_problems(d, WORDS, tmp_path))
    assert motion.design_problems(design, WORDS, tmp_path) == []


def test_pulse_does_not_count_as_motion(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["beats"][1]["acts"] = [{"do": "pulse", "thing": "atk", "at": 0.2}]
    assert any("không có gì chuyển động" in p for p in motion.design_problems(d, WORDS, tmp_path))


def test_mechanism_may_take_55_percent():
    def text(n_title, n_mech, n_rest):
        return {1: " ".join(["ba"] * n_title), 2: " ".join(["ba"] * n_mech), 3: " ".join(["ba"] * n_rest)}
    assert motion._lines_problems([2], text(10, 26, 14)) == []  # 52 %
    assert any("55 %" in p for p in motion._lines_problems([2], text(10, 30, 10)))  # 60 %


def test_beats_after_the_first_start_a_little_before_their_words(design, tmp_path):
    sc = motion.bind_timed(design, BIND, estimate(SCRIPT), SCRIPT, tmp_path)
    draws = {a.thing: a.t0 for a in sc.acts if a.do == "draw"}
    assert draws["atk"] == pytest.approx(_start(4) - motion.LEAD_IN)  # the first beat opens on its line
    assert draws["mem"] == pytest.approx(_start(5, 2) - 0.2)
    assert motion.LEAD_WORD == 0.2


def test_drift_alone_is_still_quiet(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["beats"][1]["acts"] = []
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    assert sc.view(4.0)[2] < sc.view(5.9)[2]  # the camera drifts through the quiet stretch
    assert any("không có gì chuyển động" in p for p in motion.design_problems(d, WORDS, tmp_path))



def test_an_attach_frames_and_wakes_its_carrier_too(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"] += [{"id": "f", "kind": "figure", "xy": [160, 600], "label": "kỹ sư", "beat": 1},
                    {"id": "k", "kind": "icon", "icon": "key", "xy": [150, 900], "beat": 3}]
    d["beats"][2]["acts"] = [{"do": "attach", "thing": "k", "on": "f", "offset": [50, 20], "at": 0.2}]
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    assert [(a.do, a.t0) for a in sc.acts if a.thing == "f" and a.do in ("dim", "undim")] == [("dim", 3.0), ("undim", 6.0)]



def test_hiding_a_carrier_hides_what_it_carries(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"] += [{"id": "f", "kind": "figure", "xy": [160, 600], "label": "kỹ sư", "beat": 1},
                    {"id": "k", "kind": "icon", "icon": "key", "xy": [210, 620], "beat": 1},
                    {"id": "m", "kind": "icon", "icon": "mail", "xy": [420, 900], "beat": 1}]
    d["beats"][0]["acts"] += [{"do": "attach", "thing": "k", "on": "f", "offset": [50, 20], "at": 0.2},
                              {"do": "attach", "thing": "m", "on": "f", "offset": [-50, 20], "at": 0.2}]
    d["beats"][1]["acts"] += [{"do": "move", "thing": "m", "to": [420, 900], "at": 0.1},  # put down: no longer carried
                              {"do": "hide", "thing": "f", "at": 0.6}]
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    hides = {a.thing: a.t0 for a in sc.acts if a.do == "hide"}
    assert hides == {"f": 4.8, "k": 4.8}



# --- final review fixes (03/11)

def test_quiet_is_a_style_rule_not_a_render_gate(design, tmp_path):
    # C1: an old canvas with a quiet stretch still renders; only `vshort motion` (agents) reports it
    d = json.loads(json.dumps(design))
    d["beats"][1]["acts"] = []
    assert any("không có gì chuyển động" in p for p in motion.bind_problems(d, BIND, SCRIPT, tmp_path))
    assert motion.bind_problems(d, BIND, SCRIPT, tmp_path, style=False) == []
    assert motion.design_problems(d, WORDS, tmp_path, style=False) == []


def test_camera_frames_a_mover_all_through_its_beat(design, tmp_path):
    # I1: a bounce mid-beat goes far from where the beat starts and ends; the camera must still hold it
    d = json.loads(json.dumps(design))
    d["things"] = [th for th in d["things"] if th["id"] != "mem"]
    d["beats"][1]["acts"] = [{"do": "bounce", "thing": "atk", "to": [520, 900], "at": 0.3, "dur": 1.2}]
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    for t in [3.9 + 0.05 * k for k in range(25)]:
        x, y = kit._position(next(th for th in sc.things if th["id"] == "atk"), sc.acts, t)
        sx, sy = kit.screen(sc.view(t), x, y)
        assert kit.SAFE[1] - 1 <= sy <= kit.SAFE[3] + 1, (t, sy)


def test_a_short_last_beat_still_ends_on_the_full_canvas(design, tmp_path):
    # I2: the pull back must finish before the canvas ends, however short the last beat
    starts, _ = motion.estimated(design)
    sc = motion.timed(design, starts, starts[-1] + 1.5, tmp_path)
    assert sc.view(starts[-1] + 1.5) == kit.FULL


def test_carried_things_fade_and_wake_with_their_carrier(design, tmp_path):
    # I5: a key in the attacker's hand never fades while he stays bright
    d = json.loads(json.dumps(design))
    d["things"].append({"id": "k", "kind": "icon", "icon": "key", "xy": [170, 320], "beat": 1})
    d["beats"][0]["acts"].append({"do": "attach", "thing": "k", "on": "atk", "offset": [50, 20], "at": 0})
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    assert not [a for a in sc.acts if a.thing == "k" and a.do == "dim"]



def test_the_camera_keeps_the_actor_in_frame(design, tmp_path):
    # acceptance 03/11: in a beat where the attacker stands still the camera zoomed past him and cut him in half
    d = json.loads(json.dumps(design))
    d["beats"][2]["acts"] = [{"do": "red", "thing": "srv", "at": 0.2}]  # beat 3 acts only on the server
    sc = motion.timed(d, *motion.estimated(d), tmp_path)
    atk = next(th for th in sc.things if th["id"] == "atk")
    x0, y0, x1, y1 = kit.bbox(kit.at_pos(atk, kit._position(atk, sc.acts, 7.0)))
    v = sc.view(7.0)
    (sx0, sy0), (sx1, sy1) = kit.screen(v, x0, y0), kit.screen(v, x1, y1)
    assert sx0 >= 0 and sx1 <= kit.W and sy0 >= 0 and sy1 <= kit.H



# --- Tai 03/11: "lộn xộn, ghi đè lên nhau" — code checks overlaps, not the agent's eye

def _overlaps(d, tmp_path):
    return [p for p in motion.design_problems(d, WORDS, tmp_path) if "đè" in p]


def test_labels_that_overlap_are_reported(design, tmp_path):
    assert _overlaps(design, tmp_path) == []
    d = json.loads(json.dumps(design))
    d["things"].append({"id": "t", "kind": "text", "xy": [520, 166], "label": "dữ liệu", "beat": 1})  # on srv's label
    assert any("'t'" in p and "'srv'" in p for p in _overlaps(d, tmp_path))


def test_a_thing_half_over_another_is_reported_but_nesting_is_fine(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"].append({"id": "b", "kind": "box", "box": [560, 380, 660, 470], "label": "tệp", "beat": 1})  # half over srv
    assert any("'b'" in p for p in _overlaps(d, tmp_path))
    d["things"][-1]["box"] = [410, 210, 500, 280]  # inside srv, clear of atk
    assert not any("'b'" in p for p in _overlaps(d, tmp_path))


def test_what_someone_carries_may_sit_on_them(design, tmp_path):
    d = json.loads(json.dumps(design))
    d["things"].append({"id": "k", "kind": "icon", "icon": "key", "xy": [150, 330], "beat": 1})  # on atk's label
    assert any("'k'" in p for p in _overlaps(d, tmp_path))
    d["beats"][0]["acts"].append({"do": "attach", "thing": "k", "on": "atk", "offset": [10, 0], "at": 0})
    assert not any("'k'" in p for p in _overlaps(d, tmp_path))


def test_overlap_is_checked_where_things_come_to_rest_not_mid_move(design, tmp_path):
    # atk flies across srv on its way to mem: only where it stops counts
    assert _overlaps(design, tmp_path) == []
