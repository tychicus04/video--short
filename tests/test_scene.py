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
        section("s2", [("b", "hub")], keep=["a", "nope"], beats=[{"at": 3, "do": "show", "ids": ["a", "b"]}])]}
    ps = problems(d)
    assert len(ps) == 4
    assert any("s1" in p and "nhịp 0" in p and "'ghost'" in p for p in ps)
    assert any("s1" in p and "nhịp 1" in p and "'x'" in p for p in ps)
    assert any("s1" in p and "nhịp 1" in p and "'y'" in p for p in ps)
    assert any("s2" in p and "keep" in p and "'nope'" in p for p in ps)


def test_keep_needs_the_id_alive_at_the_end_of_the_section_before():
    ok = [("a", "hub"), ("b", "r0")]
    d = {"sections": [section("s1", ok), section("s2", [("c", "hub")], keep=["a"]),
                      section("s3", [("d", "hub")], keep=["a", "b"])]}
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
    d = {"sections": [section("s1", [("a", "hub")]), section("s2", [("b", "hub")], keep=["a"])]}
    d["sections"][1]["nodes"].append({"id": "a", "icon": "user", "label": "", "slot": "r0"})
    assert any("'a'" in p and "s2" in p for p in problems(d))


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
