import json
from pathlib import Path

import pytest

from vshort.fit import Placement, phrase_fracs
from vshort.motion import LEAD_IN, clashes, load, sheet, timed, validate

EX = Path(__file__).resolve().parent.parent / "examples" / "motion"


def _ex(name):
    return json.loads((EX / f"{name}.json").read_text()), json.loads((EX / f"{name}.script.json").read_text())


def _line_end(pl, a, sc):
    """End of the voice of the scene line whose span holds the act's start."""
    p = next(p for p in pl if p.id in sc.lines and a.t0 <= p.start + p.dur + 1e-9)  # a scene's opening starts early
    return p.start + p.dur


@pytest.mark.parametrize("name", ["coruna", "goi-tin"])
def test_examples_are_valid(name):
    doc, script = _ex(name)
    assert validate(doc, script) == []


def test_timed_follows_the_voice():
    doc, script = _ex("goi-tin")
    slow = [Placement(i, s, d) for i, s, d in [(1, 0.2, 3), (2, 3.5, 4), (3, 7.8, 4), (4, 12.1, 5), (5, 17.4, 3)]]
    fast = [Placement(p.id, p.start / 2, p.dur / 2) for p in slow]
    t_slow = [a.t0 for sc in timed(doc, slow, script) for a in sc.acts if a.do != "draw"]
    t_fast = [a.t0 for sc in timed(doc, fast, script) for a in sc.acts if a.do != "draw"]
    assert t_fast == pytest.approx([t / 2 for t in t_slow])
    pkt = next(a for a in timed(doc, slow, script)[0].acts if a.do == "move")  # {2, phrase 3, at 0.2}
    f0, f1 = phrase_fracs(script[1]["phrases"])[2]
    assert pkt.t0 == pytest.approx(3.5 + 4 * (f0 + (f1 - f0) * 0.2))


def test_acts_end_inside_their_line():
    doc, script = _ex("coruna")
    pl = [Placement(r["id"], 10 + r["id"], 0.8) for r in script if r["phrases"].strip()]
    for sc in timed(doc, pl, script):
        for a in sc.acts:
            if a.do != "pulse":
                assert a.t1 - a.t0 >= 0.3 - 1e-9
                assert a.t1 <= max(_line_end(pl, a, sc), a.t0 + 0.3) + 1e-9


@pytest.mark.parametrize("case, edit, needle", [
    ("label-word", lambda d: d["scenes"][0]["things"][1].update(label="CVE-2025-24201"), "cve-2025-24201"),
    ("url", lambda d: d["scenes"][0]["things"][0].update(url="apple.com"), "apple.com"),
    ("crowded", lambda d: d["scenes"][1]["things"].append(
        {"id": "x", "kind": "box", "box": [200, 920, 520, 1000], "label": "dữ liệu", "when": {"line": 10}}), "4"),
    ("subtitle-band", lambda d: d["scenes"][0]["things"][0].update(box=[180, 170, 540, 1150]), "1050"),
    ("mover", lambda d: d["scenes"][1]["acts"].append({"do": "move", "thing": "safari", "to": [300, 300],
                                                       "when": {"line": 11}}), "safari"),
    ("title", lambda d: d.update(lines=[1, *d["lines"]]), "tiêu đề"),
    ("cue", lambda d: d["scenes"][0]["acts"][0]["when"].update(phrase=9), "phrase"),
    ("split", lambda d: d["scenes"][0].update(lines=[7, 9]), "lines"),
    ("say-not-box", lambda d: d["scenes"][2]["acts"][0].update(say="đã bị chiếm"), "say"),
    ("say-low-box", lambda d: d["scenes"][1]["things"][2].update(box=[120, 700, 600, 760]), "say"),
    ("short-dur", lambda d: d["scenes"][1]["acts"][1].update(dur=0.05), "dur"),
])
def test_validate_reports(case, edit, needle):
    doc, script = _ex("coruna")
    edit(doc)
    assert any(needle in p.lower() for p in validate(doc, script)), case


def test_validate_rejects_a_reference_on_an_animated_line():
    doc, script = _ex("coruna")
    refs = [{"kind": "svg", "id": 9, "file": "visuals/a.svg"}, {"kind": "svg", "id": 4, "file": "visuals/b.svg"},
            {"kind": "patch", "ids": [8, 9]}]
    assert [p for p in validate(doc, script, refs) if "9" in p]
    assert not [p for p in clashes(refs, {7, 8, 9}) if "4" in p]


def test_load_treats_null_and_missing_as_no_animation(tmp_path):
    assert load(tmp_path / "motion.json") is None
    (tmp_path / "motion.json").write_text("null")
    assert load(tmp_path / "motion.json") is None
    (tmp_path / "motion.json").write_text("{oops")
    with pytest.raises(ValueError):
        load(tmp_path / "motion.json")


def test_sheet_has_a_row_per_scene():
    doc, script = _ex("coruna")
    img = sheet(doc, script)
    assert img.width >= 4 * 240 and img.height >= 3 * 420


def test_a_scene_starts_drawing_in_the_crossfade_into_it():
    doc, script = _ex("goi-tin")
    pl = [Placement(i, s, d) for i, s, d in [(1, 0.2, 3), (2, 3.5, 4), (3, 7.8, 4), (4, 12.1, 5), (5, 17.4, 3)]]
    first, second = timed(doc, pl, script)
    draws = {a.thing: a.t0 for a in first.acts if a.do == "draw"}
    assert draws["a"] == pytest.approx(3.5 - LEAD_IN)  # {line 2}: the very start of the scene
    assert draws["b"] > 3.5  # {line 2, phrase 2}: on its word
    opening = [a.t0 for a in second.acts if a.do == "draw" and a.thing in ("a", "b")]
    assert len(opening) == 2 and all(t == pytest.approx(7.8 - LEAD_IN) for t in opening)
