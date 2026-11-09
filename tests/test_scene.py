import copy
import json
import re

import pytest

from vshort import layout
from vshort.cli import main
from vshort.fit import Placement, phrase_times
from vshort.scene import (ICONS, LAYOUTS, LEAD, Beat, Link, Node, Phrase, SceneError, beat_time, icons, load_scene,
                          phrase_table)

TIMELINE = {"total": 9.0, "placements": [{"id": 1, "start": 0.2, "dur": 2.0}, {"id": 2, "start": 2.7, "dur": 3.0},
                                         {"id": 3, "start": 6.2, "dur": 1.5}]}
SCRIPT = [{"id": 1, "phrases": "Tiêu đề của video"}, {"id": 2, "phrases": "một hai ba | bốn năm sáu"},
          {"id": 3, "phrases": "kết thúc"}]

GOOD = {"sections": [{"id": "s1", "label": "THÔNG THƯỜNG", "tone": "normal", "layout": "ring", "keep": [],
        "nodes": [{"id": "dc", "icon": "server", "label": "nhà cung cấp", "slot": "hub"},
                  {"id": "u1", "icon": "user", "label": "", "slot": "r0"}],
        "links": [{"id": "l1", "a": "u1", "b": "dc", "style": "solid"}],
        "beats": [{"at": 6, "do": "draw", "ids": ["dc"]}, {"at": 7, "do": "show", "ids": ["u1", "l1"]},
                  {"at": 8, "do": "flow", "link": "l1", "dir": "a-b", "repeat": 3},
                  {"at": 9, "do": "state", "ids": ["dc", "l1"], "to": "risk"},
                  {"at": 9, "do": "chip", "text": "PHẢI TIN?", "near": "dc", "tone": "risk", "delay": 0.6}]}]}


def section(sid, nodes=(), keep=(), beats=(), layout="ring"):
    return {"id": sid, "label": "", "tone": "normal", "layout": layout, "keep": list(keep),
            "nodes": [{"id": n, "icon": "user", "label": "", "slot": s} for n, s in nodes], "links": [], "beats": list(beats)}


def problems(data) -> list[str]:
    with pytest.raises(SceneError) as e:
        load_scene(data)
    return e.value.problems


def test_load_scene_reads_the_example():
    sc = load_scene(GOOD)
    s = sc.sections[0]
    assert (s.id, s.label, s.tone, s.layout, s.keep) == ("s1", "THÔNG THƯỜNG", "normal", "ring", ())
    assert s.nodes[0] == Node("dc", "server", "nhà cung cấp", "hub")
    assert s.links == (Link("l1", "u1", "dc", "solid"),)
    assert s.beats[0] == Beat(6, "draw", {"ids": ["dc"]})
    assert s.beats[2] == Beat(8, "flow", {"link": "l1", "dir": "a-b", "repeat": 3})
    assert s.beats[4] == Beat(9, "chip", {"text": "PHẢI TIN?", "near": "dc", "tone": "risk"}, delay=0.6)


def test_flow_repeats_twice_unless_told_and_id_lists_are_lists():
    d = copy.deepcopy(GOOD)
    d["sections"][0]["beats"] = [{"at": 8, "do": "flow", "link": "l1", "dir": "b-a"},
                                 {"at": 9, "do": "split", "node": "dc", "to": "u1"}]
    beats = load_scene(d).sections[0].beats
    assert beats[0].args["repeat"] == 2 and beats[1].args["to"] == ["u1"]


def test_load_scene_reports_all_problems_at_once():
    d = {"sections": [section("s1", [("a", "hub"), ("a", "nowhere")], beats=[
        {"at": 2, "do": "teleport", "ids": ["a"]}, {"at": 3, "do": "state", "ids": ["a"]},
        {"at": 4, "do": "badge", "node": "a", "icon": "unicorn"}], layout="pair")]}
    d["sections"][0]["nodes"][1]["icon"] = "dragon"
    ps = problems(d)
    for expect in ("'teleport'", "thiếu to", "'unicorn'", "'dragon'", "'nowhere'", "trùng id 'a'"):
        assert any(expect in p and "s1" in p for p in ps), (expect, ps)
    assert any("nhịp 0" in p and "'teleport'" in p for p in ps)
    assert any("nhịp 1" in p and "thiếu to" in p for p in ps)
    assert any("nhịp 2" in p and "'unicorn'" in p for p in ps)
    assert len(ps) == 6


def test_beat_at_title_is_refused():
    d = copy.deepcopy(GOOD)
    d["sections"][0]["beats"][0]["at"] = 0
    ps = problems(d)
    assert len(ps) == 1 and "cụm 0 là câu tiêu đề" in ps[0] and "s1" in ps[0] and "nhịp 0" in ps[0]


@pytest.mark.parametrize("edit, expect", [
    (lambda s: s["beats"][0].update(at=-2), "cụm -2"),
    (lambda s: s["beats"][0].update(at=True), "'at'"),
    (lambda s: s.update(layout="spiral"), "'spiral'"),
    (lambda s: s.update(tone="purple"), "'purple'"),
    (lambda s: s["links"][0].update(style="wavy"), "'wavy'"),
    (lambda s: s["beats"][2].update(dir="up"), "'up'"),
    (lambda s: s["beats"][2].update(repeat=0), "repeat"),
    (lambda s: s["beats"][3].update(to="blue"), "'blue'"),
    (lambda s: s["beats"][4].update(near="ghost"), "'ghost'"),
    (lambda s: s["links"][0].update(b="ghost"), "'ghost'"),
    (lambda s: s["nodes"][1].pop("icon"), "icon"),
])
def test_one_mistake_is_one_problem_that_names_the_section(edit, expect):
    d = copy.deepcopy(GOOD)
    edit(d["sections"][0])
    ps = problems(d)
    assert len(ps) == 1 and expect in ps[0] and "s1" in ps[0], ps


def test_ids_a_beat_names_must_be_declared_or_kept():
    d = {"sections": [
        section("s1", [("a", "hub")], beats=[{"at": 1, "do": "show", "ids": ["a", "ghost"]},
                                             {"at": 2, "do": "merge", "from": ["a", "x"], "into": "y"}]),
        section("s2", [("b", "r0")], keep=["a", "nope"], beats=[{"at": 3, "do": "show", "ids": ["a", "b"]}])]}
    ps = problems(d)
    assert len(ps) == 4
    assert any("s1" in p and "nhịp 0" in p and "'ghost'" in p for p in ps)
    assert any("s1" in p and "nhịp 1" in p and "'x'" in p for p in ps)
    assert any("s1" in p and "nhịp 1" in p and "'y'" in p for p in ps)
    assert any("s2" in p and "keep" in p and "'nope'" in p for p in ps)


def test_keep_needs_the_id_alive_at_the_end_of_the_section_before():
    ok = [("a", "hub"), ("b", "r0")]
    d = {"sections": [section("s1", ok), section("s2", [("c", "r1")], keep=["a"]),
                      section("s3", [("d", "r2")], keep=["a", "b"])]}
    ps = problems(d)
    assert len(ps) == 1 and "s3" in ps[0] and "keep" in ps[0] and "'b'" in ps[0]
    assert "'x'" in problems({"sections": [section("s1", ok, keep=["x"])]})[0]


def test_ids_are_unique_across_the_scene_and_nodes_share_them_with_links():
    d = {"sections": [section("s1", [("a", "hub")]), section("s2", [("a", "hub")])]}
    ps = problems(d)
    assert len(ps) == 1 and "s2" in ps[0] and "'a'" in ps[0] and "s1" in ps[0]
    d = copy.deepcopy(GOOD)
    d["sections"][0]["links"][0]["id"] = "dc"
    assert "'dc'" in problems(d)[0]
    d = {"sections": [section("s1", [("a", "hub")]), section("s1", [("b", "hub")])]}
    assert "s1" in problems(d)[0] and "trùng" in problems(d)[0]
    d = {"sections": [section("s1", [("a", "hub")]), section("s2", [("b", "r1")], keep=["a"])]}
    d["sections"][1]["nodes"].append({"id": "a", "icon": "user", "label": "", "slot": "r0"})
    assert any("'a'" in p and "s2" in p for p in problems(d))


def beat_on(**beat):
    return lambda s: s["beats"].append({"at": 10, **beat})


@pytest.mark.parametrize("edit, expect", [
    (beat_on(do="chip", text="x", neer="dc"), "'neer'"),  # a typo for `near` would silently lose the anchor
    (beat_on(do="flow", link="l1", dir="a-b", repeats=3), "'repeats'"),
    (beat_on(do="chip", text="x", color="#f00"), "'color'"),
    (beat_on(do="statement", text="x", tone="risk"), "'tone'"),  # a statement is white
    (beat_on(do="state", ids=["dc"], to="risk", tone="safe"), "'tone'"),
    (beat_on(do="hero", icon="shield", x=5), "'x'"),
    (lambda s: s["nodes"][1].update(x=10), "'x'"),
    (lambda s: s["links"][0].update(curve=1), "'curve'"),
    (lambda s: s.update(background="black"), "'background'"),
])
def test_a_key_the_vocabulary_does_not_have_is_a_problem(edit, expect):
    d = copy.deepcopy(GOOD)
    edit(d["sections"][0])
    ps = problems(d)
    assert len(ps) == 1 and "khóa lạ" in ps[0] and expect in ps[0] and "s1" in ps[0], ps


def test_coordinates_and_colours_are_each_a_problem_naming_the_beat():
    d = copy.deepcopy(GOOD)
    beat_on(do="chip", text="x", x=100, y=200, color="#f00")(d["sections"][0])
    ps = problems(d)
    assert len(ps) == 3 and all("nhịp 5" in p for p in ps)


def test_the_optional_keys_of_a_verb_are_allowed():
    d = copy.deepcopy(GOOD)
    for edit in (beat_on(do="hero", icon="shield", label="KHIÊN", tone="safe"),
                 beat_on(do="quote", text="x", who="công ty", tone="claim"),
                 beat_on(do="chip", text="x", near="dc", tone="risk", delay=1.0),
                 beat_on(do="flow", link="l1", dir="b-a", repeat=1)):
        edit(d["sections"][0])
    assert len(load_scene(d).sections[0].beats) == 9


@pytest.mark.parametrize("edit, expect", [
    (beat_on(do="flow", link="dc", dir="a-b"), "đường nối"),
    (beat_on(do="badge", node="l1", icon="lock"), "nút"),
    (beat_on(do="chip", text="x", near="l1"), "nút"),
    (beat_on(do="merge", **{"from": ["u1", "l1"]}, into="dc"), "'l1'"),
    (beat_on(do="merge", **{"from": ["u1"]}, into="l1"), "'l1'"),
    (beat_on(do="split", node="dc", to=["l1"]), "'l1'"),
    (beat_on(do="split", node="l1", to=["u1"]), "'l1'"),
    (lambda s: s["links"][0].update(a="l1"), "'l1'"),
])
def test_a_reference_must_name_the_right_kind_of_thing(edit, expect):
    d = copy.deepcopy(GOOD)
    edit(d["sections"][0])
    ps = problems(d)
    assert len(ps) == 1 and expect in ps[0] and "s1" in ps[0] and ("là nút" in ps[0] or "là đường nối" in ps[0]), ps


@pytest.mark.parametrize("beat, key", [
    (dict(do="hero", icon=None), "icon"),
    (dict(do="badge", node="dc", icon=5), "icon"),
    (dict(do="chip", text=42), "text"),
    (dict(do="quote", text="x", who=None), "who"),
    (dict(do="statement", text=""), "text"),
    (dict(do="hero", icon="shield", label=3), "label"),
])
def test_a_text_or_icon_arg_must_be_a_non_empty_string(beat, key):
    d = copy.deepcopy(GOOD)
    beat_on(**beat)(d["sections"][0])
    ps = problems(d)
    assert len(ps) == 1 and key in ps[0] and "nhịp 5" in ps[0], ps


def test_a_slot_holds_one_node():
    d = copy.deepcopy(GOOD)
    d["sections"][0]["nodes"].append({"id": "u2", "icon": "user", "label": "", "slot": "hub"})
    ps = problems(d)
    assert len(ps) == 1 and "'hub'" in ps[0] and "'dc'" in ps[0] and "u2" in ps[0]


def two(layout, keep, nodes=(), links=(), beats=()):
    """GOOD (a ring: hub dc, u1 at r0, link l1) and a second section."""
    d = copy.deepcopy(GOOD)
    d["sections"].append({"id": "s2", "label": "", "tone": "normal", "layout": layout, "keep": keep, "links": list(links),
                          "nodes": [{"id": n, "icon": "user", "label": "", "slot": s} for n, s in nodes], "beats": list(beats)})
    return d


def test_a_hub_is_kept_from_a_ring_into_a_pair_and_a_ring_continues():
    s2 = load_scene(two("pair", ["dc"], [("x", "left")])).sections[1]
    assert s2.keep == ("dc",)
    s2 = load_scene(two("ring", ["dc", "u1", "l1"], [("u2", "r1")])).sections[1]
    assert s2.keep == ("dc", "u1", "l1")


def test_a_kept_node_holds_its_slot():
    ps = problems(two("pair", ["dc"], [("x", "hub")]))
    assert len(ps) == 1 and "s2" in ps[0] and "'hub'" in ps[0] and "'dc'" in ps[0] and "x" in ps[0]
    ps = problems(two("ring", ["dc", "u1"], [("u2", "r0")]))
    assert len(ps) == 1 and "'r0'" in ps[0] and "'u1'" in ps[0]


def test_a_kept_node_keeps_its_spot_so_the_new_layout_needs_a_slot_there():
    ps = problems(two("pair", ["u1"], [("x", "left")]))  # u1 stood at the ring's r0 (558, 560)
    assert len(ps) == 1 and "s2" in ps[0] and "'u1'" in ps[0] and "(558, 560)" in ps[0] and "pair" in ps[0]
    assert "(330, 560)" in problems(two("grid", ["dc"], [("x", "g0")]))[0]  # a grid has no centre
    assert "'u1'" in problems(two("none", ["u1"]))[0]


def test_a_kept_link_needs_both_its_nodes_kept():
    ps = problems(two("pair", ["l1"], [("x", "left")]))
    assert len(ps) == 1 and "s2" in ps[0] and "'l1'" in ps[0] and "'u1'" in ps[0] and "'dc'" in ps[0]
    ps = problems(two("ring", ["dc", "l1"], [("x", "r1")]))
    assert len(ps) == 1 and "'u1'" in ps[0] and "'dc'" not in ps[0]


def test_a_link_ends_at_a_kept_node_not_at_a_kept_link():
    d = two("ring", ["dc", "u1", "l1"], [("x", "r1")], links=[{"id": "l9", "a": "x", "b": "l1"}])
    ps = problems(d)
    assert len(ps) == 1 and "s2" in ps[0] and "'l1'" in ps[0] and "là đường nối" in ps[0]
    d["sections"][1]["links"][0]["b"] = "dc"
    assert load_scene(d).sections[1].links[0].b == "dc"


def _ghost_in_s2_and_s3():
    d = two("ring", ["dc", "ghost"])
    d["sections"].append(section("s3", keep=["dc", "ghost"]))  # the refused keep is carried on, and not reported twice
    return d


@pytest.mark.parametrize("make, who", [  # a keep that was refused has no kind and no ends: never a KeyError
    (lambda: two("ring", ["dc", "nope"], beats=[{"at": 7, "do": "badge", "node": "nope", "icon": "lock"}]), "nope"),
    (lambda: two("ring", ["dc", "nope"], links=[{"id": "l2", "a": "dc", "b": "nope"}]), "nope"),
    (lambda: two("ring", ["dc", "nope"], beats=[{"at": 7, "do": "show", "ids": ["nope"]}]), "nope"),
    (_ghost_in_s2_and_s3, "ghost"),
])
def test_a_refused_keep_is_one_problem_whatever_uses_the_id_after(make, who):
    ps = problems(make())
    assert len(ps) == 1 and ps[0].startswith(f"mục s2: keep nhắc tới '{who}'"), ps


def test_keeping_a_link_that_was_declared_with_a_problem_adds_no_second_one():
    d = two("ring", ["dc", "l2"])
    d["sections"][0]["links"].append({"id": "l2", "b": "dc"})  # no `a`
    ps = problems(d)
    assert len(ps) == 1 and "s1" in ps[0] and "l2" in ps[0] and "thiếu a" in ps[0], ps


@pytest.mark.parametrize("bad_id", [["l2"], {"x": 1}, 7])
def test_an_id_that_is_not_text_is_one_problem_not_a_crash(bad_id):
    d = copy.deepcopy(GOOD)
    d["sections"][0]["links"].append({"id": bad_id, "a": "u1", "b": "dc"})
    ps = problems(d)
    assert len(ps) == 1 and "s1" in ps[0] and "thiếu id" in ps[0], ps


def test_wrong_shape_is_a_problem_not_a_crash():
    assert problems({}) and problems({"sections": "x"})
    ps = problems({"sections": [3, {"id": "s1", "nodes": [7], "beats": [{"do": "show"}]}]})
    assert len(ps) >= 3 and any("s1" in p for p in ps)


def test_scene_error_takes_one_string_or_a_list():
    e = SceneError("nhãn của u1: không còn chỗ trống")
    assert e.problems == ["nhãn của u1: không còn chỗ trống"] and str(e) == "nhãn của u1: không còn chỗ trống"
    e = SceneError(["một", "hai"])
    assert e.problems == ["một", "hai"] and str(e) == "một\nhai"
    with pytest.raises(SceneError, match="hai"):
        raise e


def test_phrase_table_matches_subtitles():
    table = phrase_table(TIMELINE, SCRIPT)
    assert [(p.start, p.end, p.text) for p in table] == phrase_times([Placement(**p) for p in TIMELINE["placements"]], SCRIPT)
    assert [p.i for p in table] == [0, 1, 2, 3] and isinstance(table[0], Phrase)
    assert table[0].start == 0.0 and table[0].text == "Tiêu đề của video"


def test_beat_time_leads_the_phrase():
    table = phrase_table(TIMELINE, SCRIPT)
    assert LEAD == 0.15
    assert beat_time(Beat(3, "show", {"ids": ["a"]}), table) == table[3].start - 0.15
    assert beat_time(Beat(2, "chip", {"text": "x"}, delay=0.6), table) == pytest.approx(table[2].start - 0.15 + 0.6)


def test_slots_match_the_layouts():
    s = layout.SLOTS
    assert set(s) == set(LAYOUTS) and s["none"] == {} and s["center"] == {"hub": layout.C} and layout.C == (330.0, 560.0)
    assert s["pair"] == {"hub": (330, 560), "left": (150, 560), "right": (510, 560), "above": (330, 380), "below": (330, 760)}
    assert list(s["ring"]) == ["hub", *(f"r{k}" for k in range(6))]
    assert s["ring"]["r0"] == pytest.approx((558, 560)) and s["ring"]["r4"] == pytest.approx((183.4, 385.3), abs=0.1)
    assert s["chain"] == {f"c{k}": (330, 330 + 150 * k) for k in range(4)}
    assert s["grid"]["g0"] == (162, 480) and s["grid"]["g2"] == (498, 480) and s["grid"]["g5"] == (498, 650) and len(s["grid"]) == 6


NAMES = ("user user-x users server hard-drive monitor smartphone cpu cloud globe building-2 file file-lock mail lock lock-open "
         "key-round shield shield-check shield-x eye eye-off check x triangle-alert door-open router database network wifi "
         "send package bug zap clock calendar newspaper scale badge-check layers").split()


def test_icon_set_is_the_briefs_list_as_paths_with_its_licence():
    raw = json.loads(ICONS.read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d+\.\d+\.\d+", raw["_version"])
    assert "ISC License" in raw["_license"] and "Cole Bemis" in raw["_license"]  # Lucide's, and Feather's MIT notice
    assert sorted(icons()) == sorted(NAMES)
    assert all(ds and all(re.fullmatch(r"[MmLlHhVvCcSsAaZz0-9 .,-]+", d) for d in ds) for ds in icons().values())


def _run(tmp_path):
    (tmp_path / "timeline.json").write_text(json.dumps(TIMELINE))
    (tmp_path / "script.vi.json").write_text(json.dumps(SCRIPT))
    (tmp_path / "brief.vi.md").write_text(
        "# Brief\n\n## Cơ chế từng bước\n0. Bình thường: máy chủ ở giữa\n1. Kẻ tấn công gửi yêu cầu\n\n## Lưu ý\nx\n")
    return str(tmp_path)


def test_scene_table_prints_each_phrase_then_the_mechanism(tmp_path, capsys):
    assert main(["scene", _run(tmp_path), "--table"]) == 0
    assert capsys.readouterr().out == (
        "0  0.00  Tiêu đề của video\n1  2.70  một hai ba\n2  4.20  bốn năm sáu\n3  6.20  kết thúc\n\n"
        "0. Bình thường: máy chủ ở giữa\n1. Kẻ tấn công gửi yêu cầu\n")


def test_scene_without_table_is_not_done_yet(tmp_path, capsys):
    assert main(["scene", _run(tmp_path)]) == 2
    assert "--table" in capsys.readouterr().err


def test_scene_table_names_what_is_missing(tmp_path, capsys):
    assert main(["scene", str(tmp_path), "--table"]) == 2
    assert "timeline.json" in capsys.readouterr().err
