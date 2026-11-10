import itertools
import math

import pytest

from vshort.layout import (C, Box, HUB, ICON, LABEL_FONT, LABEL_MAX, LABEL_SIZE, MIN_LINK, SLOTS, STATEMENT_BAND, _wrap, boxes_overlap,
                           place, segment_hits_box, text_box)
from vshort.scene import Beat, Link, Node, SceneError, Section


def ring_section(labels=None, links_to_hub=False, chip=None, beats=()):
    """Layout "ring": hub "dc" and u1..u6 on r0..r5; optional labels (one per u), links u -> dc, a chip (text, near, tone)."""
    nodes = [Node("dc", "server", "", "hub")] + [Node(f"u{i + 1}", "user", labels[i] if labels else "", f"r{i}") for i in range(6)]
    links = [Link(f"l{i + 1}", f"u{i + 1}", "dc", "solid") for i in range(6)] * links_to_hub
    chips = [Beat(1, "chip", {"text": chip[0], "near": chip[1], "tone": chip[2]})] if chip else []
    return Section("s1", "", "normal", "ring", tuple(nodes), tuple(links), tuple(beats) + tuple(chips), ())


def widest_label() -> str:
    """A label as wide as the rule allows, to within a pixel or two."""
    s = ""
    for ch in "ĐMmnoiltI.":
        while text_box(s + ch, LABEL_FONT, LABEL_SIZE, 0, 0).x1 <= LABEL_MAX:
            s += ch
    return s


def full_section(layout):
    """Every slot holds a node with a label as wide as allowed, a badge and a tile; links: all to the hub, along the chain, along
    each row of the grid, as the layout has a hub, a line or a table."""
    slots = list(SLOTS[layout])
    nodes = tuple(Node(f"n{i}", "user", widest_label(), s) for i, s in enumerate(slots))
    ids = [n.id for n in nodes]
    if "hub" in slots:
        pairs = [(n.id, next(m.id for m in nodes if m.slot == "hub")) for n in nodes if n.slot != "hub"]
    elif layout == "chain":
        pairs = list(zip(ids, ids[1:]))
    else:  # grid: along the rows
        pairs = [(ids[i], ids[i + 1]) for i in range(len(ids) - 1) if i % 3 != 2]
    links = tuple(Link(f"l{i}", a, b, "solid") for i, (a, b) in enumerate(pairs))
    # the hub of a full ring has a link through each corner, so no badge can stand by it (place refuses that one)
    badged = [n.id for n in nodes if not (layout == "ring" and n.slot == "hub")]
    beats = tuple(Beat(1, "badge", {"node": i, "icon": "lock"}) for i in badged) + (Beat(2, "split", {"node": ids[0], "to": ids}),)
    return Section("s1", "", "normal", layout, nodes, links, beats, ())


def by_id(els, i):
    return next(e for e in els if e["id"] == i)


def test_overlap_and_segment_tests_keep_their_margins():
    assert boxes_overlap([0, 0, 10, 10], [13.9, 0, 20, 10]) and not boxes_overlap([0, 0, 10, 10], [14, 0, 20, 10])
    assert not boxes_overlap([0, 0, 10, 10], [10, 0, 20, 10], margin=-1) and boxes_overlap(Box(0, 0, 10, 10), Box(5, 5, 9, 9))
    link = {"x1": 0, "y1": 100, "x2": 200, "y2": 100}
    near = [50, 108, 100, 150]  # 8 px under the line
    assert not segment_hits_box(link, near) and segment_hits_box(link, near, margin=9) and segment_hits_box(link | {"style": "tunnel"}, near)
    assert segment_hits_box({"x1": 0, "y1": 0, "x2": 100, "y2": 100}, [40, 60, 60, 80])  # a diagonal through the corner region
    assert not segment_hits_box({"x1": 0, "y1": 0, "x2": 100, "y2": 100}, [70, 20, 90, 40])  # and one beside the box
    assert segment_hits_box(link, [-50, 90, 10, 110]) and not segment_hits_box(link, [210, 90, 260, 110])  # an end inside; past the end


def test_ring_slots_match_the_spike():
    r = SLOTS["ring"]
    assert r["r0"] == pytest.approx((558, 560), abs=0.5) and r["r4"] == pytest.approx((183.4, 385.3), abs=0.5)


def test_ring_with_labels_stays_left_of_the_buttons():
    els = place(ring_section(labels=["Máy chủ"] * 6))
    assert all(e["box"][2] <= 618 for e in els if e["box"][3] > 535)
    assert {e["id"] for e in els if e["kind"] == "label"} == {f"u{i}.label" for i in range(1, 7)}


def test_trust_chip_above_hub_misses_every_link():  # the spike got this wrong four times
    els = place(ring_section(links_to_hub=True, chip=("PHẢI TIN?", "dc", "risk")))
    chip = next(e for e in els if e["kind"] == "chip")
    assert not any(segment_hits_box(e, chip["box"]) for e in els if e["kind"] == "link")
    assert chip["box"][3] < by_id(els, "dc")["box"][1]  # still above the hub
    assert (chip["id"], chip["tone"], chip["beat"]) == ("s1.0", "risk", 0)


def test_label_too_long_names_the_node():
    with pytest.raises(SceneError, match="nhãn của u1"):
        place(ring_section(labels=["Máy chủ SharePoint nội bộ của công ty lớn"] * 6))


def test_a_label_with_nowhere_to_stand_names_the_node():
    sec = Section("s2", "", "normal", "ring", (Node("u1", "user", "Máy chủ", "r0"),), (), (), ())
    assert place(sec)  # there is room as it is
    wall = [{"id": "wall", "kind": "chip", "box": [0, 250, 720, 900]}]  # kept, covering every spot the label could take
    with pytest.raises(SceneError, match="nhãn của u1: không còn chỗ trống"):
        place(sec, kept=wall)


@pytest.mark.parametrize("layout", ["center", "pair", "chain", "ring", "grid"])
def test_full_layouts_have_no_overlap(layout):  # a full layout must not make mistakes the agent cannot repair
    els = place(full_section(layout))
    texts = [e for e in els if e["kind"] in ("label", "chip")]
    solid = [e for e in els if e["kind"] in ("icon", "badge", "tile")]
    assert len(texts) == len(SLOTS[layout]) and len(solid) == 3 * len(SLOTS[layout]) - (layout == "ring")  # no badge by a full ring's hub
    assert not any(boxes_overlap(a["box"], b["box"]) for a, b in itertools.combinations(texts + solid, 2))
    assert not any(segment_hits_box(link, t["box"]) for link in els if link["kind"] == "link" for t in texts)
    assert all(e["box"][2] <= 618 for e in els if e["box"][3] > 535)
    assert all(math.dist((e["x1"], e["y1"]), (e["x2"], e["y2"])) >= MIN_LINK for e in els if e["kind"] == "link")


def test_a_link_too_short_to_see_is_refused_in_vietnamese(monkeypatch):  # the old pair slots left a 22 px stub
    nodes = (Node("a", "user", "", "left"), Node("b", "server", "", "hub"))
    sec = Section("s1", "", "normal", "pair", nodes, (Link("l1", "a", "b", "solid"),), (), ())
    assert place(sec)  # 72 px of line
    monkeypatch.setitem(SLOTS["pair"], "left", (170, 560))  # 160 px from the hub: 2 px of line
    with pytest.raises(SceneError, match=r"nối l1: a và b quá gần nhau để nối \(chỉ thấy 2 px đường, cần ít nhất 48\)"):
        place(sec)


def test_nodes_links_badges_and_tiles_stand_as_in_the_spike():
    sec = ring_section(links_to_hub=True, beats=[Beat(1, "badge", {"node": "u1", "icon": "eyeoff"}),
                                                 Beat(2, "split", {"node": "dc", "to": ["u1", "dc"]}),
                                                 Beat(3, "merge", {"from": ["u2", "u3"], "into": "dc"})])
    els = place(sec)
    dc, u1 = by_id(els, "dc"), by_id(els, "u1")
    assert (dc["size"], u1["size"], dc["kind"], dc["icon"], dc["tone"]) == (HUB, ICON, "icon", "server", "normal")
    assert (dc["x"], dc["y"]) == C
    link = by_id(els, "l1")  # u1 at r0 is to the right of the hub: 46 px in from the user, 112 from the hub
    assert math.dist((link["x1"], link["y1"]), (u1["x"], u1["y"])) == pytest.approx(46)
    assert math.dist((link["x2"], link["y2"]), C) == pytest.approx(112)
    badge = by_id(els, "s1.0")  # size 34 at (x - 0.6 s, y - 0.74 s): (x - 50, y - 62) at s = 84 in the spike
    assert (badge["kind"], badge["of"], badge["beat"], badge["size"]) == ("badge", "u1", 0, 34)
    assert (badge["x"], badge["y"]) == pytest.approx((u1["x"] - 50.4, u1["y"] - 62.16))
    t0, t1 = by_id(els, "s1.1.0"), by_id(els, "s1.1.1")  # 30 × 30 at (x, y - s / 2 - 41): (x, y - 83) at s = 84
    assert (t0["kind"], t0["size"], t0["beat"]) == ("tile", 30, 1) and "of" not in t0  # a tile is not its node's
    assert (t0["x"], t0["y"]) == pytest.approx((u1["x"], u1["y"] - 83))
    assert (t1["x"], t1["y"]) == pytest.approx((C[0], C[1] - 116))
    m0, m1 = by_id(els, "s1.2.0"), by_id(els, "s1.2.1")  # a merge's tiles, one a piece, all rest over `into`, on one spot
    assert (m0["kind"], m0["beat"]) == ("tile", 2) and "s1.2.2" not in {e["id"] for e in els}
    assert (m0["x"], m0["y"]) == pytest.approx((C[0], C[1] - 116)) and (m1["x"], m1["y"]) == (m0["x"], m0["y"])
    assert m0["box"] == m1["box"] == t1["box"]
    assert t0["box"] == pytest.approx([u1["x"] - 16.25, u1["y"] - 99.25, u1["x"] + 16.25, u1["y"] - 66.75], abs=0.01)  # 30 + stroke 2.5


def test_split_and_merge_name_a_node_that_is_not_there():
    for beat, ghost in [(Beat(1, "merge", {"from": ["u1"], "into": "ghost"}), "ghost"),
                        (Beat(1, "merge", {"from": ["ghost"], "into": "dc"}), "ghost"),
                        (Beat(1, "split", {"node": "ghost", "to": ["u1"]}), "ghost"),
                        (Beat(1, "split", {"node": "dc", "to": ["ghost"]}), "ghost")]:
        with pytest.raises(SceneError, match=f"nhịp 0 .*nút '{ghost}'"):
            place(ring_section(beats=[beat]))


def test_a_link_too_short_to_draw_is_refused():
    sec = Section("s1", "", "normal", "chain", (Node("a", "user", "", "c0"), Node("b", "user", "", "c1")),
                  (Link("l", "a", "a", "solid"), Link("m", "a", "b", "solid")), (), ())
    with pytest.raises(SceneError, match="nối l: a và a quá gần"):
        place(sec)


def test_ids_and_tones_of_everything_a_beat_makes():
    nodes = (Node("dc", "server", "", "hub"), Node("f", "file", "tệp", "left"))
    beats = (Beat(1, "badge", {"node": "f", "icon": "lock"}), Beat(2, "swap", {"node": "f", "icon": "filelock"}),
             Beat(3, "chip", {"text": "05.11.2026"}), Beat(4, "statement", {"text": "Một câu ngắn"}),
             Beat(5, "quote", {"text": "AI không cần data center khổng lồ", "who": "OPENMATTER TUYÊN BỐ"}),
             Beat(6, "hero", {"icon": "shield", "label": "BẰNG CHỨNG MẬT MÃ"}), Beat(7, "hero", {"icon": "check", "tone": "claim"}))
    els = place(Section("s9", "KIỂM CHỨNG", "risk", "pair", nodes, (), beats, ()))
    assert {e["id"] for e in els} == {"dc", "f", "f.label", "s9.label", "s9.0", "s9.1", "s9.2", "s9.3", "s9.4", "s9.5", "s9.6"}
    f, swap = by_id(els, "f"), by_id(els, "s9.1")
    assert (swap["kind"], swap["icon"], swap["of"], swap["beat"]) == ("icon", "filelock", "f", 1)
    assert (swap["x"], swap["y"], swap["size"], swap["tone"], swap["box"]) == (f["x"], f["y"], f["size"], "risk", f["box"])
    tones = {e["id"]: e["tone"] for e in els}
    assert tones == {"dc": "risk", "f": "risk", "f.label": "risk", "s9.label": "risk", "s9.0": "risk", "s9.1": "risk",
                     "s9.2": "claim", "s9.3": None, "s9.4": "claim", "s9.5": "safe", "s9.6": "claim"}
    hero, plain = by_id(els, "s9.5"), by_id(els, "s9.6")
    assert (hero["kind"], hero["size"], hero["x"], hero["y"]) == ("hero", 170, C[0], C[1] - 6)
    assert (hero["label"], plain["label"], plain["label_box"][2] - plain["label_box"][0]) == ("BẰNG CHỨNG MẬT MÃ", "", 0)
    lb = hero["label_box"]  # IBM Plex Mono 30, centred on the picture's middle, from y 756
    assert lb[1] == 756 and lb[0] + lb[2] == pytest.approx(2 * C[0], abs=0.1)
    assert hero["box"][1] < hero["box"][3] and hero["box"][3] == lb[3] and hero["box"][0] <= lb[0] and hero["box"][2] >= lb[2]
    sec = by_id(els, "s9.label")
    assert (sec["box"][:2], sec["text"], sec["kind"], sec["align"], sec["font"], sec["size"]) == (
        [60, 190], "KIỂM CHỨNG", "section", "left", "IBMPlexMono-SemiBold.ttf", 22)
    assert (by_id(els, "f.label")["align"], by_id(els, "s9.2")["align"], by_id(els, "s9.2")["font"]) == (
        "center", "center", "IBMPlexMono-SemiBold.ttf")
    assert not [e for e in els if e["kind"] == "tile"]


def test_plex_mono_is_measured_with_its_two_pixel_letter_spacing():
    from vshort.layout import MONO
    from vshort.textfit import _font
    raw = _font(22, MONO).getbbox("PHẢI TIN?")[2]
    assert text_box("PHẢI TIN?", MONO, 22, 0, 0).x1 == pytest.approx((raw + 2 * 8) * 1.06)
    raw = _font(22, LABEL_FONT).getbbox("Máy chủ")[2]  # Be Vietnam Pro has none
    assert text_box("Máy chủ", LABEL_FONT, 22, 0, 0).x1 == pytest.approx(raw * 1.06)


def test_statement_and_quote_wrap_and_refuse_what_will_not_fit():
    els = place(Section("s1", "", "normal", "none", (), (), (
        Beat(1, "statement", {"text": "Mỗi máy chỉ thấy một phần nhỏ của việc"}),
        Beat(2, "quote", {"text": "AI không cần data center khổng lồ", "who": "A"}),), ()))
    st, q = by_id(els, "s1.0"), by_id(els, "s1.1")
    assert len(st["lines"]) == 2 and 60 <= st["box"][0] and 870 <= st["box"][1] and st["box"][3] <= 990 and st["box"][2] <= 612
    assert st["box"][0] + st["box"][2] == pytest.approx(60 + 612, abs=0.1) and st["tone"] is None  # the box centred in the band
    assert 1 <= len(q["lines"]) <= 4 and q["box"] == [60, 380, 600, 750]
    for text, kind, who in [("từ " * 30, "statement", None), ("từ " * 30, "quote", "A"), ("từ", "quote", "x" * 80)]:
        args = {"text": text} | ({"who": who} if who else {})
        with pytest.raises(SceneError, match="nhịp 0"):
            place(Section("s1", "", "normal", "none", (), (), (Beat(1, kind, args),), ()))


STATEMENTS = [  # (text, the two lines, or None: the greedy wrap's own, which leaves no orphan and so is kept)
    ("Tin ai khi máy chủ lộ chìa?", ["Tin ai khi máy chủ", "lộ chìa?"]),  # greedy: "… lộ | chìa?"
    ("Cập nhật ngay hôm nay", ["Cập nhật ngay", "hôm nay"]),  # greedy: "… hôm | nay"
    ("Mỗi máy chỉ thấy một phần", ["Mỗi máy chỉ thấy", "một phần"]),  # greedy: "… một | phần"
    ("Một lỗ hổng mở cả hệ thống", ["Một lỗ hổng mở cả", "hệ thống"]),  # greedy: "… cả hệ | thống"
    ("Dữ liệu khách hàng đã bị lộ", None),  # a rebalance would cut "khách | hàng"
    ("Hãy cập nhật bản vá ngay hôm nay", None),  # … "bản | vá"
    ("Không ai kiểm tra lại chữ ký", None),  # … "kiểm | tra"
]


@pytest.mark.parametrize("text, expected", STATEMENTS, ids=[t for t, _ in STATEMENTS])
def test_a_statement_loses_its_orphan_last_word_and_no_other_cut_moves(text, expected):
    # Ruling 36: greedy's cut stays, except when its second line is one word: then the cut moves back to the latest point that leaves
    # two words below (a rebalance of every statement cut mid-sentence, where Vietnamese compounds are dense)
    st = by_id(place(Section("s1", "", "normal", "none", (), (), (Beat(1, "statement", {"text": text}),), ())), "s1.0")
    band = STATEMENT_BAND.x1 - STATEMENT_BAND.x0
    greedy = _wrap(text, "BeVietnamPro-ExtraBold.ttf", 44, band, 2)
    assert len(greedy) == 2  # the sentence does not fit on one line at size 44: a row for a one-liner would test nothing
    lines = st["lines"]
    assert lines == (expected or greedy) and " ".join(lines) == text and len(lines) == 2
    assert all(text_box(ln, "BeVietnamPro-ExtraBold.ttf", 44, 0, 0).x1 <= band for ln in lines)
    assert st["box"][2] - st["box"][0] == pytest.approx(max(text_box(ln, "BeVietnamPro-ExtraBold.ttf", 44, 0, 0).x1 for ln in lines))


def test_chips_without_near_stack_in_the_left_column():
    chips = tuple(Beat(i, "chip", {"text": t}) for i, t in enumerate(["05.11.2026", "chưa xác nhận", "1000 lần"], start=1))
    for label, y0 in (("", 190), ("THÔNG THƯỜNG", 250)):
        els = place(Section("s1", label, "normal", "none", (), (), chips, ()))
        cs = [e for e in els if e["kind"] == "chip"]
        assert [c["box"][0] for c in cs] == [60, 60, 60] and cs[0]["box"][1] == y0
        assert cs[1]["box"][1] == pytest.approx(cs[0]["box"][3] + 12, abs=0.1)
        assert cs[2]["box"][1] == pytest.approx(cs[1]["box"][3] + 12, abs=0.1)
        assert all(c["tone"] == "claim" for c in cs)


def test_a_chip_goes_round_icons_and_names_itself_when_nothing_is_left():
    els = place(ring_section(beats=[Beat(i, "chip", {"text": "bốn mươi hai"}) for i in range(1, 4)]))
    cs = [e for e in els if e["kind"] == "chip"]
    icons = [e for e in els if e["kind"] == "icon"]
    assert not any(boxes_overlap(c["box"], i["box"]) for c in cs for i in icons)
    with pytest.raises(SceneError, match="chip 'bốn mươi hai': không còn chỗ trống"):
        place(Section("s1", "", "normal", "none", (), (), tuple(Beat(i, "chip", {"text": "bốn mươi hai"}) for i in range(1, 30)), ()))
    with pytest.raises(SceneError, match="chip 'PHẢI TIN\\?' cạnh dc: không còn chỗ trống"):
        place(ring_section(links_to_hub=True, chip=("PHẢI TIN?", "dc", "risk")), kept=[
            {"id": "wall", "kind": "chip", "box": [0, 250, 720, 900]}])


def test_a_kept_hub_is_an_obstacle_and_a_link_to_it_is_cut_at_its_size():
    first = place(Section("a", "", "normal", "center", (Node("dc", "server", "dịch vụ", "hub"),), (), (), ()))
    kept = [e for e in first if e["id"] == "dc" or e.get("of") == "dc"]
    assert [e["id"] for e in kept] == ["dc", "dc.label"]
    # what an earlier section left to the left of the hub, where a new node's label would first go
    kept.append({"id": "old.label", "kind": "label", "of": "dc", "box": [80, 606, 220, 634]})
    nodes = (Node("u1", "user", "Máy chủ", "left"), Node("u2", "user", "Máy chủ", "above"))
    sec = Section("b", "", "normal", "pair", nodes, (Link("l1", "u2", "dc", "solid"),), (), ("dc",))
    els = place(sec, kept)
    assert {e["id"] for e in els} == {"u1", "u2", "u1.label", "u2.label", "l1"}  # only this section's own
    link = by_id(els, "l1")
    assert math.dist((link["x2"], link["y2"]), C) == pytest.approx(112)
    assert math.dist((link["x1"], link["y1"]), (330, 340)) == pytest.approx(46)
    labels = [e for e in els if e["kind"] == "label"]
    solid = kept + [e for e in els if e["kind"] == "icon"]
    assert not any(boxes_overlap(lb["box"], k["box"]) for lb in labels for k in solid)
    assert not any(segment_hits_box(link, lb["box"]) for lb in labels)
    # without that old label, u1's own would stand right under its icon: the kept one is what moved it
    assert by_id(place(sec, kept[:2]), "u1.label")["box"][1] == pytest.approx(604.75, abs=0.1)


def test_a_badge_takes_the_first_corner_no_link_runs_through():
    """u1 (r0) is right of the hub, its link leaves it sideways: the spike's corner (above, left) is free. u2 (r1) is below and to
    the right, its link leaves up and to the left, through that corner: the badge goes above, right."""
    sec = ring_section(links_to_hub=True, beats=[Beat(1, "badge", {"node": "u1", "icon": "lock"}),
                                                 Beat(1, "badge", {"node": "u2", "icon": "lock"})])
    els = place(sec)
    u1, u2, b1, b2 = (by_id(els, i) for i in ("u1", "u2", "s1.0", "s1.1"))
    assert (b1["x"], b1["y"]) == pytest.approx((u1["x"] - 50.4, u1["y"] - 62.16))
    assert (b2["x"], b2["y"]) == pytest.approx((u2["x"] + 50.4, u2["y"] - 62.16))
    assert not any(segment_hits_box(l, b["box"]) for l in els if l["kind"] == "link" for b in (b1, b2))


def test_a_badge_with_a_link_through_every_corner_is_a_problem_that_names_the_node():
    with pytest.raises(SceneError) as e:  # the hub of a full ring: r1, r2, r4 and r5 leave through its four corners
        place(ring_section(links_to_hub=True, beats=[Beat(1, "badge", {"node": "dc", "icon": "lock"})]))
    assert len(e.value.problems) == 1 and "badge" in e.value.problems[0] and "'dc'" in e.value.problems[0]
    assert "chip" in e.value.problems[0]  # what to do instead
