import copy
import json
import re

import pytest

from vshort import layout, render
from vshort.cli import main
from vshort.fit import Placement, phrase_times
from vshort.scene import (ICONS, LAYOUTS, LEAD, MAX_GAP, Beat, Link, Node, Phrase, SceneError, beat_time, check, icons,
                          load_scene, phrase_table, resolve)

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
    assert s["pair"] == {"hub": (330, 560), "left": (100, 560), "right": (560, 560), "above": (330, 340), "below": (330, 780)}
    assert list(s["ring"]) == ["hub", *(f"r{k}" for k in range(6))]
    assert s["ring"]["r0"] == pytest.approx((558, 560)) and s["ring"]["r4"] == pytest.approx((183.4, 385.3), abs=0.1)
    assert s["chain"] == {f"c{k}": (330, 330 + 150 * k) for k in range(4)}
    assert s["grid"]["g0"] == (162, 460) and s["grid"]["g2"] == (498, 460) and s["grid"]["g5"] == (498, 660) and len(s["grid"]) == 6


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


def test_scene_table_names_what_is_missing(tmp_path, capsys):
    assert main(["scene", str(tmp_path), "--table"]) == 2
    assert "timeline.json" in capsys.readouterr().err


# ---- resolve: the scene timed to the voice; check: what it refuses

TABLE = phrase_table(TIMELINE, SCRIPT)
SAID = (0.2, 2.2)  # the title's spoken span: the first placement's start and start + dur
TITLE = "Tiêu đề của video"
ALL = [Phrase(i, 3.0 * i, 3.0 * i + 3.0, f"cụm {i}") for i in range(15)]  # a table long enough for the two sections below


def el(id, kind, box, tone="normal", **more):
    return {"id": id, "kind": kind, "tone": tone, "box": box, **more}


def chip(id, text, box, tone="claim"):
    return el(id, "chip", box, tone, text=text)


def act(t, do, *ids, **more):
    return {"t": t, "do": do, "ids": list(ids), **more}


def hero(id, label="", tone="safe", x=330, y=554):
    """As `place` makes it: the big icon's ink box, and its label under it (`box` holds both)."""
    ink, lab = [x - 73.08, y - 73.08, x + 73.08, y + 73.08], [x - 85, 756, x + 85, 790] if label else [x, 756, x, 756]
    box = [min(ink[0], lab[0]), ink[1], max(ink[2], lab[2]), lab[3] if label else ink[3]]
    return el(id, "hero", box, tone, icon="shield", x=x, y=y, size=170, label=label, label_box=lab)


def rt_of(els, acts, total=20.0, title=None):
    return {"total": total, "title": title, "captions": [], "elements": els, "actions": acts}


def test_check_overlap():
    a, b = chip("s2.3", "PHẢI TIN?", [100, 300, 260, 340]), chip("s2.4", "AN TOÀN", [200, 310, 360, 350])
    got = check(rt_of([a, b], [act(3, "on", "s2.3"), act(6, "on", "s2.4"), act(9, "off", "s2.3", "s2.4")], 12), "")
    assert len(got) == 1 and got[0].startswith("6,0 s") and "'s2.3'" in got[0] and "'s2.4'" in got[0] and "PHẢI TIN?" in got[0]
    # the first is gone (its fade is over) when the second comes: they never share the screen
    gone = rt_of([a, b], [act(3, "on", "s2.3"), act(5, "off", "s2.3", d=0.35), act(6, "on", "s2.4")], 9)
    assert check(gone, "") == []
    # a swap: the old icon leaves as the new comes, in the same box
    old, new = el("u", "icon", [10, 300, 90, 380]), el("s1.2", "icon", [10, 300, 90, 380], of="u")
    assert check(rt_of([old, new], [act(2, "on", "u"), act(4, "swap", "u", "s1.2")], 8), "") == []


def test_check_text_on_a_link_and_a_solid_and_solids_on_each_other():
    link = el("l1", "link", [100, 400, 400, 400], x1=100, y1=400, x2=400, y2=400, style="solid")
    c, dc = chip("s1.2", "PHẢI TIN?", [200, 380, 300, 420]), el("dc", "icon", [250, 300, 330, 380])
    got = check(rt_of([link, c, dc], [act(2, "on", "l1"), act(3, "on", "s1.2"), act(4, "on", "dc")], 8), "")
    assert any("chip 's1.2' 'PHẢI TIN?' đè lên nối 'l1'" in p and p.startswith("3,0 s") for p in got)
    assert any("chip 's1.2'" in p and "nút 'dc'" in p and p.startswith("4,0 s") for p in got)
    a, b = el("a", "icon", [100, 300, 180, 380]), el("b", "icon", [170, 300, 250, 380])
    got = check(rt_of([a, b], [act(2, "on", "a"), act(4, "on", "b")], 8), "")
    assert len(got) == 1 and "nút 'a' đè lên nút 'b'" in got[0]


def test_check_a_hero_is_an_icon_and_a_label_not_the_box_around_both():
    h = hero("s1.3", "BẰNG CHỨNG MẬT MÃ")  # its box runs from the icon's top to the label's foot and across to both ends
    corner = chip("c1", "GÓC", [60, 600, 200, 640])  # inside the box, clear of the drawn icon and the label
    over_label = chip("c2", "ĐÈ", [260, 760, 400, 790])
    on_icon = chip("c3", "TRÊN", [300, 500, 380, 540])
    got = check(rt_of([h, corner, over_label, on_icon], [act(2, "draw", "s1.3"), act(5, "on", "c1", "c2", "c3")], 8), "")
    assert len(got) == 2  # (and the hero's colour with the chips': two colours, no third)
    assert not any("'c1'" in p for p in got) and any("'c2'" in p and "hero" in p for p in got) and any("'c3'" in p for p in got)


def test_check_tiles_of_one_beat_may_touch():
    a, b = el("s1.2.0", "tile", [300, 440, 332, 472]), el("s1.2.1", "tile", [300, 440, 332, 472])
    other = el("s1.3.0", "tile", [310, 450, 342, 482])
    assert check(rt_of([a, b], [act(2, "move", "s1.2.0", "s1.2.1", **{"from": [[0, 0], [9, 9]]})], 6), "") == []
    got = check(rt_of([a, other], [act(2, "on", "s1.2.0"), act(4, "on", "s1.3.0")], 8), "")
    assert len(got) == 1


def test_check_safe_zone():
    far = chip("c1", "XA QUÁ", [560, 680, 640, 720])  # x 640 under y 535: the buttons
    top = chip("c2", "TRÊN", [200, 100, 300, 130])
    low = chip("c3", "DƯỚI", [200, 980, 300, 1010])  # into the caption band
    ok = chip("c4", "VỪA", [500, 300, 640, 340])  # above y 535 the right edge is free
    got = check(rt_of([far, top, low, ok], [act(2, "on", "c1", "c2", "c3", "c4")], 6), "")
    assert len(got) == 3 and all(p.startswith("2,0 s") for p in got)
    assert "'c1'" in got[0] and "618" in got[0] and "'c2'" in got[1] and "141" in got[1] and "'c3'" in got[2] and "1000" in got[2]


def test_check_a_dimmed_element_shown_again_is_whole_again():
    node = el("dc", "icon", [500, 300, 580, 380], "risk")
    claim = chip("s1.1", "CHƯA XÁC NHẬN", [60, 300, 300, 340], "claim")
    ok = el("k1", "icon", [100, 600, 180, 680], "safe")
    acts = [act(1, "on", "dc"), act(2, "tone", "dc", to="dim"), act(3, "on", "s1.1"), act(4, "on", "k1")]
    assert check(rt_of([node, claim, ok], acts, 8), "") == []  # dim, so two colours
    for again in (act(5, "on", "dc"), act(5, "draw", "dc", d=0.6), act(5, "type", "dc", d=0.5), act(5, "move", "dc", **{"from": [[0, 0]]})):
        got = check(rt_of([node, claim, ok], acts + [again], 8), "")
        assert len(got) == 1 and got[0].startswith("5,0 s") and "3 màu" in got[0], (again, got)


def test_check_three_tones():
    claim = chip("s1.1", "CHƯA XÁC NHẬN", [60, 300, 300, 340], "claim")
    node = el("dc", "icon", [500, 300, 580, 380], "risk")
    hero_ = hero("s1.2")
    acts = [act(2, "on", "dc"), act(3, "on", "s1.1"), act(5, "draw", "s1.2", d=0.7)]
    got = check(rt_of([claim, node, hero_], acts, 9), "")
    assert len(got) == 1 and got[0].startswith("5,0 s") and "3 màu" in got[0] and "đỏ" in got[0] and "'dc'" in got[0]
    dimmed = [acts[0], acts[1], act(4, "tone", "dc", to="dim"), acts[2]]  # dim takes effect at its own time
    assert check(rt_of([claim, node, hero_], dimmed, 9), "") == []
    again = dimmed + [act(7, "tone", "dc", to="risk")]  # a colour brings it back
    assert len(check(rt_of([claim, node, hero_], again, 9), "")) == 1
    white = el("s1.4", "statement", [60, 870, 600, 960], None, text="mỗi máy một phần")  # white is not a colour
    assert check(rt_of([claim, node, white], [acts[0], acts[1], act(5, "type", "s1.4", d=1)], 9), "") == []


@pytest.mark.parametrize("acts, total, title, times", [
    ([act(2, "on", "c"), act(8.5, "on", "c")], 10, None, ("2,0 s", "8,5 s")),  # between two actions
    ([act(2, "on", "c"), act(7, "on", "c")], 9, None, None),  # exactly 5 s is allowed
    ([act(9, "on", "c")], 12, {"out": 3.86}, ("3,9 s", "9,0 s")),  # from the title leaving to the first action
    ([act(1, "on", "c")], 6.5, None, ("1,0 s", "6,5 s")),  # from the last action to the end
    ([act(1, "on", "c")], 6.0, {"out": 0.5}, None),
])
def test_check_gap(acts, total, title, times):
    got = check(rt_of([chip("c", "VỪA", [60, 300, 200, 340])], acts, total, title), "")
    if times is None:
        assert got == []
    else:
        assert len(got) == 1 and "5 giây" in got[0] and all(t in got[0] for t in times)


def test_a_title_without_a_bar_is_a_caption_and_the_gap_clock_starts_when_it_has_been_said():
    d = one_section([{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 2, "do": "chip", "text": "PHẢI TIN?", "near": "dc"}])
    long_title = [{"id": 1, "start": 0.2, "dur": 6.0}, {"id": 2, "start": 6.7, "dur": 1.5}, {"id": 3, "start": 8.4, "dur": 1.0}]
    table = phrase_table({"total": 10.0, "placements": long_title}, SCRIPT)
    rt = resolved(d, table, 10.0, (0.2, 6.2), "CHỮ " * 80)
    assert rt["title"] is None and rt["captions"][0][1] == pytest.approx(6.7) and check(rt, "") == []
    rt["captions"] = []  # nothing to say when it ended: from 0
    assert "0,0 s đến" in check(rt, "")[0]


def test_check_an_action_outside_the_video():
    c = chip("c", "VỪA", [60, 300, 200, 340])
    got = check(rt_of([c], [act(2, "on", "c"), act(5, "type", "c", d=1), act(11, "off", "c")], 8), "")
    assert len(got) == 1 and "11,0 s" in got[0] and "'c'" in got[0] and "ngoài video" in got[0]


def test_check_number_not_in_brief():
    c = chip("s1.1", "1000 lần", [60, 300, 200, 340])
    got = check(rt_of([c], [act(2, "on", "s1.1")], 6), "Có 5 lần.")
    assert len(got) == 1 and "1000" in got[0] and "'s1.1'" in got[0] and got[0].startswith("2,0 s") and "brief" in got[0]
    date = chip("s1.2", "05.11.2026", [60, 300, 200, 340])  # the brief writes it another way (Review Focus 4)
    assert check(rt_of([date], [act(2, "on", "s1.2")], 6), "ngày 5/11/2026") == []
    never = chip("s1.3", "9999", [60, 400, 200, 440])  # never shown, never on a frame
    assert check(rt_of([c, never], [act(2, "on", "s1.1"), act(4, "off", "s1.1")], 6), "Có 1000 lần.") == []


def test_check_numbers_in_a_quote_a_statement_a_hero_label_and_a_section_label():
    q = el("s1.1", "quote", [60, 380, 600, 750], "claim", text="giảm 40 %", who="CÔNG TY 77")
    s = el("s1.2", "statement", [60, 870, 600, 960], None, text="mất 12 giờ")
    h = hero("s1.3", "CẤP 3")
    sec = el("s1.label", "section", [60, 190, 300, 220], "claim", text="MỤC 8")
    acts = [act(2, "on", "s1.label", "s1.1"), act(4, "off", "s1.1"), act(5, "on", "s1.2"), act(7, "off", "s1.2"), act(8, "on", "s1.3")]
    got = check(rt_of([q, s, h, sec], acts, 11), "")  # at most two colours at once and nothing overlaps: only the numbers are wrong
    assert len(got) == 5
    for who, num in (("s1.1", "40"), ("s1.1", "77"), ("s1.2", "12"), ("s1.3", "3"), ("s1.label", "8")):
        assert any(f"'{who}'" in p and f"số {num} không có trong brief" in p for p in got), (who, num, got)


def test_check_names_are_checked_unless_all_capitals_or_a_section_label():
    brief = "OpenMatter tuyên bố về AI."
    ok = chip("c1", "OpenMatter tuyên bố", [60, 300, 300, 340])
    bad = chip("c2", "do Veritas tuyên bố", [60, 400, 300, 440])
    caps = chip("c3", "PHẢI TIN VERITAS?", [60, 500, 300, 540])  # ponytail: all capitals get the number check only
    sec = el("s1.label", "section", [60, 190, 300, 220], "normal", text="Veritas Đề Xuất")  # a section label is exempt
    q = el("s1.1", "quote", [60, 600, 600, 750], "claim", text="AI an toàn", who="công ty Veritas")
    got = check(rt_of([ok, bad, caps, sec, q], [act(2, "on", "c1", "c2", "c3", "s1.label"), act(5, "on", "s1.1")], 8), brief)
    assert len(got) == 2 and "'c2'" in got[0] and "Veritas" in got[0] and "'s1.1'" in got[1] and "Veritas" in got[1]


# a scene on the four-row TABLE above: sentences 1-3 are said at 2.7, 4.2 and 6.2 s
def one_section(beats, nodes=None, **more):
    return {"sections": [{"id": "s1", "label": "", "tone": "normal", "layout": "pair", "keep": [], "links": [], "beats": beats,
                          "nodes": nodes or [{"id": "dc", "icon": "server", "label": "máy chủ", "slot": "hub"}], **more}]}


def resolved(data, table=TABLE, total=9.0, said=SAID, title=TITLE):
    return resolve(load_scene(data), table, title, total, said)


def test_phrase_out_of_range():
    d = one_section([{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 41, "do": "chip", "text": "PHẢI TIN?", "near": "dc"},
                     {"at": 3, "do": "show", "ids": ["dc"]}])
    with pytest.raises(SceneError) as e:
        resolved(d)
    assert len(e.value.problems) == 1 and "cụm 41 không có" in e.value.problems[0]
    assert "s1" in e.value.problems[0] and "nhịp 1" in e.value.problems[0]


def test_a_section_without_beats_is_a_problem():
    with pytest.raises(SceneError) as e:
        resolved(one_section([]))
    assert "mục s1" in e.value.problems[0]


def test_title_matches_cover():
    rt = resolved(one_section([{"at": 1, "do": "draw", "ids": ["dc"]}]))
    p0 = TIMELINE["placements"][0]  # cover.py grabs its frame once the spoken title is typed
    assert rt["title"]["t1"] == render.title_times(p0["start"], p0["start"] + p0["dur"])[1]
    assert rt["title"]["out"] == render.title_times(p0["start"], p0["start"] + p0["dur"])[2]
    assert (rt["title"]["size"], rt["title"]["lines"]) == render.title_fit(TITLE)
    assert render.title_times(TABLE[0].start, TABLE[0].end)[1] != rt["title"]["t1"]  # row 0 runs on to the next sentence
    assert [c[2] for c in rt["captions"]] == ["một hai ba", "bốn năm sáu", "kết thúc"]  # the title is not also a caption
    assert rt["total"] == 9.0


def test_no_bar_for_a_title_that_does_not_fit_and_the_caption_keeps_the_line():
    rt = resolved(one_section([{"at": 1, "do": "draw", "ids": ["dc"]}]), title="CHỮ " * 80)
    assert rt["title"] is None and rt["captions"][0] == [0.0, 2.7, "Tiêu đề của video"] and len(rt["captions"]) == 4


def test_captions_are_plain_text():
    script = [SCRIPT[0], {"id": 2, "phrases": "phần mềm *hợp lệ* | bốn năm sáu"}, SCRIPT[2]]
    rt = resolved(one_section([{"at": 1, "do": "draw", "ids": ["dc"]}]), phrase_table(TIMELINE, script))
    assert [c[2] for c in rt["captions"]] == ["phần mềm hợp lệ", "bốn năm sáu", "kết thúc"]


def test_a_beat_is_timed_to_its_phrase():
    rt = resolved(one_section([{"at": 2, "do": "draw", "ids": ["dc"]}, {"at": 3, "do": "chip", "text": "PHẢI TIN?",
                                                                       "near": "dc", "delay": 0.5}]))
    first = next(a for a in rt["actions"] if a["do"] == "draw")
    assert first["t"] == pytest.approx(TABLE[2].start - LEAD) and 0.3 <= first["d"] <= 0.8 and first["ids"] == ["dc"]
    assert next(a for a in rt["actions"] if a["ids"] == ["s1.1"])["t"] == pytest.approx(TABLE[3].start - LEAD + 0.5)
    assert [a["t"] for a in rt["actions"]] == sorted(a["t"] for a in rt["actions"])


def test_place_errors_come_out_of_resolve_too():
    d = one_section([{"at": 1, "do": "draw", "ids": ["dc"]}], nodes=[{"id": "dc", "icon": "server", "slot": "hub",
                                                                      "label": "một cái nhãn dài hơn cả chiều rộng cho phép"}])
    with pytest.raises(SceneError) as e:
        resolved(d)
    assert "nhãn của dc" in e.value.problems[0]


def test_a_section_may_not_begin_before_the_one_before_has_stopped():
    d = one_section([{"at": 2, "do": "draw", "ids": ["dc"]}, {"at": 3, "do": "chip", "text": "A", "near": "dc"}])
    d["sections"].append({"id": "s2", "label": "", "tone": "normal", "layout": "pair", "keep": [],
                          "nodes": [{"id": "x", "icon": "user", "label": "", "slot": "left"}], "links": [],
                          "beats": [{"at": 3, "do": "draw", "ids": ["x"]}]})
    with pytest.raises(SceneError) as e:
        resolved(d)
    assert "s2" in e.value.problems[0] and "s1" in e.value.problems[0] and "6,05 s" in e.value.problems[0]


TWO = {"sections": [
    {"id": "s1", "label": "THÔNG THƯỜNG", "tone": "normal", "layout": "ring", "keep": [],
     "nodes": [{"id": "dc", "icon": "server", "label": "máy chủ", "slot": "hub"},
               {"id": "u1", "icon": "user", "label": "", "slot": "r0"}, {"id": "u2", "icon": "user", "label": "", "slot": "r3"}],
     "links": [{"id": "l1", "a": "u1", "b": "dc", "style": "solid"}, {"id": "l2", "a": "u2", "b": "dc", "style": "dashed"}],
     "beats": [{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 2, "do": "show", "ids": ["u1", "l1", "u2", "l2"]},
               {"at": 3, "do": "flow", "link": "l1", "dir": "a-b", "repeat": 2},
               {"at": 4, "do": "state", "ids": ["dc", "l1"], "to": "risk"},
               {"at": 4, "do": "chip", "text": "PHẢI TIN?", "near": "dc", "tone": "risk", "delay": 0.6},
               {"at": 5, "do": "badge", "node": "u1", "icon": "lock"},
               {"at": 6, "do": "swap", "node": "u2", "icon": "user-x"}]},
    {"id": "s2", "label": "KIỂM CHỨNG", "tone": "safe", "layout": "pair", "keep": ["dc"],
     "nodes": [{"id": "k1", "icon": "key-round", "label": "khóa A", "slot": "left"},
               {"id": "k2", "icon": "key-round", "label": "khóa B", "slot": "right"}], "links": [],
     "beats": [{"at": 7, "do": "show", "ids": ["k1", "k2"]},
               {"at": 8, "do": "split", "node": "dc", "to": ["k1", "k2"]},
               {"at": 9, "do": "merge", "from": ["k1", "k2"], "into": "dc"},
               {"at": 10, "do": "state", "ids": ["dc"], "to": "safe"},
               {"at": 11, "do": "statement", "text": "Mỗi máy chỉ thấy một phần"},
               {"at": 12, "do": "hide", "ids": ["dc", "k1", "k2"]},
               {"at": 13, "do": "hero", "icon": "shield", "label": "BẰNG CHỨNG MẬT MÃ"}]}]}
DOS = {"on", "draw", "type", "off", "tone", "flow", "move", "swap"}


def assert_contract(rt):
    """What Task 7's kit relies on (runtime-contract.md): known verbs with their fields, ids that exist, and a tone that never brings
    back an element that is not on screen (it ends at opacity 1)."""
    kinds = {e["id"]: e["kind"] for e in rt["elements"]}
    assert len(kinds) == len(rt["elements"]) and [a["t"] for a in rt["actions"]] == sorted(a["t"] for a in rt["actions"])
    shown, gone = set(), set()
    for a in rt["actions"]:
        do, ids = a["do"], a["ids"]
        assert do in DOS and ids and all(i in kinds for i in ids), a
        if do == "draw":
            assert all(kinds[i] in ("icon", "badge", "link", "hero", "quote") for i in ids) and 0.3 <= a["d"] <= 0.8
        elif do == "type":
            assert all(kinds[i] in ("label", "section", "chip", "statement", "quote", "hero") for i in ids) and a["d"] > 0
        elif do == "flow":
            assert kinds[ids[0]] == "link" and a["dir"] in ("a-b", "b-a") and a["repeat"] >= 1 and a["d"] > 0
        elif do == "move":
            assert all(kinds[i] == "tile" for i in ids) and len(a["from"]) == len(ids) and a["d"] > 0
        elif do == "swap":
            assert len(ids) == 2 and ids[0] in shown and ids[1] not in shown
        elif do == "tone":
            assert a["to"] in ("normal", "risk", "claim", "safe", "dim") and all(i in shown and i not in gone for i in ids), a
        elif do == "off":
            assert all(i in shown for i in ids)
        if do == "off":
            gone |= set(ids)
        elif do == "swap":
            gone.add(ids[0])
            shown.add(ids[1])
        elif do != "flow":
            shown |= set(ids)
            gone -= set(ids)


def test_two_sections_resolve_into_the_runtime_contract_and_pass_the_check():
    rt = resolved(TWO, ALL, 42.0, (0.2, 2.8))
    assert check(rt, "") == []
    assert_contract(rt)
    by = {e["id"]: e for e in rt["elements"]}
    assert set(by) >= {"dc", "dc.label", "u1", "l1", "s1.label", "s1.4", "s1.5", "s1.6", "s2.label", "k1", "k1.label", "s2.1.0",
                       "s2.2.1", "s2.4", "s2.6"}
    # state reaches what belongs to the node
    tone = next(a for a in rt["actions"] if a["do"] == "tone" and a["to"] == "risk")
    assert set(tone["ids"]) == {"dc", "dc.label", "l1"}
    # s2 opens by turning off what s1 leaves, but the kept hub and its label, 0.35 s before its first beat
    start = ALL[7].start - LEAD
    off = next(a for a in rt["actions"] if a["do"] == "off" and a["t"] == pytest.approx(start - 0.35))
    assert off["d"] == 0.35 and {"u1", "l1", "l2", "s1.label", "s1.4", "s1.5", "s1.6"} <= set(off["ids"])  # u2 was swapped out already
    assert not {"dc", "dc.label"} & set(off["ids"])
    assert next(a for a in rt["actions"] if a["ids"] == ["s2.label"])["t"] == pytest.approx(start)
    # a split's tiles fly out of the source node to their nodes; a merge's fly in from over their nodes to one spot over the target
    split = [a for a in rt["actions"] if a["do"] == "move" and a["ids"][0].startswith("s2.1.")]
    assert [a["from"] for a in split] == [[[by["dc"]["x"], by["dc"]["y"]]]] * 2
    merge = [a for a in rt["actions"] if a["do"] == "move" and a["ids"][0].startswith("s2.2.")]
    assert len(merge) == 2 and all(by[a["ids"][0]]["x"] == by["dc"]["x"] for a in merge) and by["s2.2.0"]["box"] == by["s2.2.1"]["box"]
    for a, k in zip(merge, ("k1", "k2")):
        spot = by["s2.1.0" if k == "k1" else "s2.1.1"]  # the split's tile rests over the same node
        assert a["from"] == [[spot["x"], spot["y"]]]
    assert {i for a in rt["actions"] if a["do"] == "off" for i in a["ids"]} >= {"s2.2.0", "s2.2.1"}


def test_a_tunnel_has_two_rails_so_text_must_stand_further_from_it():
    link = lambda style: el("l1", "link", [100, 400, 400, 400], x1=100, y1=400, x2=400, y2=400, style=style)
    c = chip("c", "PHẢI TIN?", [200, 360, 300, 392])  # 8 px over the line
    acts = [act(2, "on", "l1"), act(3, "on", "c")]
    assert check(rt_of([link("solid"), c], acts, 6), "") == []
    assert "đè lên nối 'l1'" in check(rt_of([link("tunnel"), c], acts, 6), "")[0]


def test_a_state_before_the_element_is_shown_colours_it_from_the_start():
    d = one_section([{"at": 1, "do": "state", "ids": ["dc"], "to": "risk"}, {"at": 2, "do": "draw", "ids": ["dc"]}])
    rt = resolved(d)
    assert not [a for a in rt["actions"] if a["do"] == "tone"]
    assert {e["id"]: e["tone"] for e in rt["elements"]} == {"dc": "risk", "dc.label": "risk"}


def test_a_kept_node_goes_on_across_three_sections():
    def sec(sid, layout, keep, beats, nodes=()):
        return {"id": sid, "label": "", "tone": "normal", "layout": layout, "keep": keep, "links": [], "nodes": list(nodes),
                "beats": beats}
    d = {"sections": [
        sec("s1", "pair", [], [{"at": 1, "do": "draw", "ids": ["dc"]}],
            [{"id": "dc", "icon": "server", "label": "máy chủ", "slot": "hub"}]),
        sec("s2", "center", ["dc"], [{"at": 2, "do": "chip", "text": "PHẢI TIN?", "near": "dc"}]),
        sec("s3", "pair", ["dc"], [{"at": 3, "do": "statement", "text": "Mỗi máy chỉ thấy một phần"}])]}
    rt = resolved(d)
    assert [e["id"] for e in rt["elements"]].count("dc") == 1
    off = [i for a in rt["actions"] if a["do"] == "off" for i in a["ids"]]
    assert off == ["s2.0"] and check(rt, "") == []  # only the chip goes, at s3's start; the hub and its label never do


def test_a_hide_reaches_the_tiles_of_a_node_and_a_beat_that_does_nothing_is_no_crash():
    d = one_section([{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 2, "do": "split", "node": "dc", "to": "dc"},
                     {"at": 3, "do": "hide", "ids": ["dc"]}, {"at": 3, "do": "hide", "ids": ["dc"]}])
    rt = resolved(d)
    assert [sorted(a["ids"]) for a in rt["actions"] if a["do"] == "off"] == [["dc", "dc.label", "s1.1.0"]]
    d = one_section([{"at": 1, "do": "dim", "ids": ["dc"]}])
    d["sections"].append({"id": "s2", "label": "", "tone": "normal", "layout": "pair", "keep": ["dc"], "nodes": [], "links": [],
                          "beats": [{"at": 2, "do": "dim", "ids": ["dc"]}]})
    assert resolved(d)["actions"] == []


def test_a_swap_in_a_later_section_starts_in_the_colour_its_kept_node_has_now():
    d = one_section([{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 2, "do": "state", "ids": ["dc"], "to": "risk"}])
    d["sections"].append({"id": "s2", "label": "", "tone": "normal", "layout": "pair", "keep": ["dc"], "nodes": [], "links": [],
                          "beats": [{"at": 3, "do": "swap", "node": "dc", "icon": "lock"}]})
    rt = resolved(d)
    new = next(e for e in rt["elements"] if e["id"] == "s2.0")
    assert new["tone"] == "risk" and next(a for a in rt["actions"] if a["do"] == "swap")["ids"] == ["dc", "s2.0"]
    assert check(rt, "") == []
    assert_contract(rt)


def test_a_dim_and_a_hide_reach_the_labels_and_swap_back_in_order():
    d = one_section([{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 2, "do": "swap", "node": "dc", "icon": "lock"},
                     {"at": 3, "do": "dim", "ids": ["dc"]}])
    rt = resolved(d)
    swap = next(a for a in rt["actions"] if a["do"] == "swap")
    dim = next(a for a in rt["actions"] if a["do"] == "tone")
    assert swap["ids"] == ["dc", "s1.1"] and set(dim["ids"]) == {"dc.label", "s1.1"} and dim["to"] == "dim"


# ---- vshort scene RUN

SCENE_OK = {"sections": [{"id": "s1", "label": "THÔNG THƯỜNG", "tone": "normal", "layout": "pair", "keep": [],
            "nodes": [{"id": "dc", "icon": "server", "label": "máy chủ", "slot": "hub"}], "links": [],
            "beats": [{"at": 1, "do": "draw", "ids": ["dc"]}, {"at": 2, "do": "chip", "text": "PHẢI TIN?", "near": "dc"},
                      {"at": 3, "do": "statement", "text": "Mỗi máy chỉ thấy một phần"}]}]}


def _scene_run(tmp_path, scene, style="neon"):
    run = _run(tmp_path)
    (tmp_path / "scene.json").write_text(json.dumps(scene))
    if style:
        (tmp_path / "run.json").write_text(json.dumps({"style": style}))
    return run


def test_scene_writes_the_resolved_file_and_marks_the_step(tmp_path, capsys):
    assert main(["scene", _scene_run(tmp_path, SCENE_OK)]) == 0
    rt = json.loads((tmp_path / "scene.resolved.json").read_text(encoding="utf-8"))
    assert rt["total"] == 9.0 and rt["title"]["lines"] and rt["elements"] and rt["actions"]
    assert json.loads((tmp_path / "state.json").read_text())["scene"] == "done"
    assert "scene.resolved.json" in capsys.readouterr().out


def test_a_refused_round_leaves_no_pass_behind(tmp_path, capsys):
    run = _scene_run(tmp_path, SCENE_OK)
    assert main(["scene", run]) == 0
    assert (tmp_path / "scene.resolved.json").exists() and json.loads((tmp_path / "state.json").read_text())["scene"] == "done"
    for edit in (lambda d: d["sections"][0]["beats"][1].update(at=41),  # the script was re-voiced: a phrase is gone (place/phrase)
                 lambda d: d["sections"][0]["beats"].append({"at": 2, "do": "teleport", "ids": ["dc"]}),  # load
                 lambda d: d["sections"][0]["beats"][1].update(text="TĂNG 1000 LẦN")):  # check
        assert main(["scene", run]) == 0  # a good round again
        bad = copy.deepcopy(SCENE_OK)
        edit(bad)
        (tmp_path / "scene.json").write_text(json.dumps(bad))
        assert main(["scene", run]) == 2
        assert not (tmp_path / "scene.resolved.json").exists() and "scene" not in json.loads((tmp_path / "state.json").read_text())
        (tmp_path / "scene.json").write_text(json.dumps(SCENE_OK))
    assert main(["scene", run]) == 0
    (tmp_path / "scene.json").unlink()  # a missing scene.json too
    assert main(["scene", run]) == 2
    assert not (tmp_path / "scene.resolved.json").exists() and "scene" not in json.loads((tmp_path / "state.json").read_text())


def test_scene_never_leaves_an_old_video_marked_as_done(tmp_path):   # a hand-run `vshort scene`, passing or refused
    run = _scene_run(tmp_path, SCENE_OK)
    state = lambda: json.loads((tmp_path / "state.json").read_text())
    (tmp_path / "state.json").write_text(json.dumps({"render": "done"}))
    assert main(["scene", run]) == 0 and state()["scene"] == "done" and "render" not in state()
    (tmp_path / "state.json").write_text(json.dumps({"render": "done", "scene": "done"}))
    (tmp_path / "scene.json").write_text("{}")  # refused
    assert main(["scene", run]) == 2 and "render" not in state() and "scene" not in state()
    (tmp_path / "state.json").write_text(json.dumps({"render": "done"}))
    assert main(["scene", run, "--table"]) == 0 and state()["render"] == "done"  # the table changes nothing


def test_scene_unmarks_only_a_neon_run_and_only_what_is_marked(tmp_path, capsys):
    # an old-flow run run by mistake: nothing unmarked (its render is not remade), state.json untouched
    (tmp_path / "old").mkdir()
    old = _scene_run(tmp_path / "old", SCENE_OK, style=None)
    (tmp_path / "old" / "state.json").write_text(json.dumps({"render": "done", "scene": "done"}))
    before = (tmp_path / "old" / "state.json").stat().st_mtime_ns
    (tmp_path / "old" / "scene.json").write_text("{}")  # refused
    assert main(["scene", old]) == 2
    assert json.loads((tmp_path / "old" / "state.json").read_text()) == {"render": "done", "scene": "done"}
    assert (tmp_path / "old" / "state.json").stat().st_mtime_ns == before
    # a neon run with nothing marked: state.json is not written
    neon = _scene_run(tmp_path, SCENE_OK)
    (tmp_path / "scene.json").write_text("{}")
    assert main(["scene", neon]) == 2 and not (tmp_path / "state.json").exists()
    # a folder that is not there: "thiếu …", BAD_INPUT, and the folder is not made
    capsys.readouterr()
    gone = tmp_path / "missing"
    assert main(["scene", str(gone)]) == 2
    assert "thiếu" in capsys.readouterr().err and not gone.exists()


def test_scene_names_a_missing_scene_json(tmp_path, capsys):
    assert main(["scene", _run(tmp_path)]) == 2
    assert "scene.json" in capsys.readouterr().err and not (tmp_path / "scene.resolved.json").exists()


def test_scene_prints_every_load_problem_one_per_line(tmp_path, capsys):
    bad = copy.deepcopy(SCENE_OK)
    bad["sections"][0]["beats"] += [{"at": 2, "do": "teleport", "ids": ["dc"]}, {"at": 3, "do": "show", "ids": ["ghost"]}]
    assert main(["scene", _scene_run(tmp_path, bad)]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 2 and "'teleport'" in err[0] and "'ghost'" in err[1]
    assert not (tmp_path / "scene.resolved.json").exists() and not (tmp_path / "state.json").exists()  # nothing was marked, nothing is written


def test_scene_prints_place_and_phrase_problems(tmp_path, capsys):
    far = copy.deepcopy(SCENE_OK)
    far["sections"][0]["beats"][1]["at"] = 41
    assert main(["scene", _scene_run(tmp_path, far)]) == 2
    assert "cụm 41 không có" in capsys.readouterr().err


def test_scene_prints_what_the_check_refuses_with_the_time(tmp_path, capsys):
    liar = copy.deepcopy(SCENE_OK)
    liar["sections"][0]["beats"][1]["text"] = "TĂNG 1000 LẦN"
    assert main(["scene", _scene_run(tmp_path, liar)]) == 2
    err = capsys.readouterr().err
    assert "1000" in err and "4,0 s" in err and not (tmp_path / "scene.resolved.json").exists()


def test_scene_that_is_not_json_is_a_problem_not_a_crash(tmp_path, capsys):
    run = _run(tmp_path)
    (tmp_path / "scene.json").write_text("{not json")
    assert main(["scene", run]) == 2 and "scene.json" in capsys.readouterr().err


def test_check_a_badge_on_a_link_but_not_an_icon_or_a_tile():
    link = el("l1", "link", [100, 400, 400, 400], x1=100, y1=400, x2=400, y2=400, style="solid")
    badge = el("s1.2", "badge", [200, 385, 230, 415], of="dc")
    got = check(rt_of([link, badge], [act(2, "on", "l1"), act(3, "on", "s1.2")], 8), "")
    assert len(got) == 1 and got[0].startswith("3,0 s") and "badge 's1.2' đè lên nối 'l1'" in got[0]
    for kind in ("icon", "tile"):  # a tile hangs over its node, where a link straight up starts: as in the spike
        assert check(rt_of([link, el("x", kind, [200, 385, 230, 415])], [act(2, "on", "l1"), act(3, "on", "x")], 8), "") == []


@pytest.mark.parametrize("acts, said", [
    ([act(3, "on", "c"), act(3.6, "off", "c", d=0.35)], "0,6 s"),            # openmatter-neon-70s: MATTERCHAIN, 39.92 to 40.52 s
    ([act(3, "type", "c", d=1.0), act(4.5, "off", "c", d=0.35)], "0,5 s"),  # typed: read from the last letter on
    ([act(3, "on", "c"), act(4.0, "off", "c", d=0.35)], None),
    ([act(3, "on", "c"), act(5, "tone", "c", to="dim"), act(5.5, "off", "c", d=0.35)], None),  # a dim is not a new showing
    ([act(3, "on", "c")], None),                                           # stays to the end
])
def test_check_a_text_that_goes_before_it_can_be_read(acts, said):
    got = check(rt_of([chip("c", "VỪA", [60, 300, 200, 340])], acts, 7), "")
    assert (got == []) if said is None else (len(got) == 1 and got[0].startswith("3,0 s") and said in got[0] and "'c'" in got[0])


@pytest.mark.parametrize("label, name", [("openmatter", "OpenMatter"), ("azure", "Azure"), ("OpenMatter", None), ("Azure", None),
                                         ("dữ liệu", None), ("máy chủ", None)])
def test_check_a_label_without_the_capitals_the_brief_gives_the_name(label, name):
    brief = "Tiêu đề\nDữ liệu ở một nơi.\nTheo OpenMatter, tài nguyên do Azure cung cấp. Dữ liệu được chia."
    lab = el("n.label", "label", [60, 300, 220, 330], text=label, of="n")
    got = check(rt_of([lab], [act(2, "type", "n.label", d=0.5)], 6), brief)
    assert (got == []) if name is None else (len(got) == 1 and repr(name) in got[0] and repr(label) in got[0])
