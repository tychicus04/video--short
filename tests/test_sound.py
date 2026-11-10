from pathlib import Path

import numpy as np

from vshort import sound
from vshort.retime import Piece

# three lines: 0–4 s plays source 0–4; 4–10 plays source 4–10; 10–14 plays source 10–16 at 1.5x
PIECES = [Piece(1, 0, 4, 0, 4, 1, 0, 0), Piece(2, 4, 10, 4, 10, 1, 0, 0), Piece(3, 10, 16, 10, 14, 1.5, 0, 0)]


def test_three_strongest_changes_get_effects_in_time_order():
    changes = [(5.0, 20.0), (6.0, 40.0), (8.0, 15.0), (11.5, 35.0), (13.0, 25.0)]
    assert sound.cues(changes, PIECES) == [sound.Cue("whoosh", 6.0), sound.Cue("pop", 8.0), sound.Cue("whoosh", 11.0)]


def test_no_effect_in_the_title_line_nor_in_a_dropped_tail():
    ps = [*PIECES[:2], Piece(3, 10, 13, 10, 12, 1.5, 0, 3)]  # source 13–16 dropped
    assert sound.cues([(2.0, 50.0), (14.0, 50.0), (7.0, 10.0)], ps) == [sound.Cue("whoosh", 7.0)]


def test_changes_closer_than_space_keep_the_stronger():
    assert sound.cues([(6.0, 20.0), (6.8, 30.0)], PIECES) == [sound.Cue("whoosh", 6.8)]


def _wav(tmp_path, a: np.ndarray) -> Path:
    path = tmp_path / "v.wav"
    sound._ff(a, "anull", "-c:a", "pcm_s16le", "-y", str(path))
    return path


def test_master_lands_on_the_loudness_with_room_under_full_scale(tmp_path):
    t = np.arange(3 * sound.RATE) / sound.RATE
    hot = 0.98 * np.sin(2 * np.pi * 220 * t) * (0.25 + 0.75 * (np.sin(2 * np.pi * 3 * t) > 0))  # quiet voice, hot peaks
    out = tmp_path / "m.wav"
    sound.master(_wav(tmp_path, 0.05 * hot), [], 4.0, out)
    a = sound._decode(out)
    assert abs(len(a) / sound.RATE - 4.0) < 0.01 and abs(sound.loudness(a) - sound.LUFS) < 0.5
    up = sound._decode(_wav(tmp_path, a))  # what the true-peak meter sees, roughly: the peaks between samples
    assert 20 * np.log10(np.abs(np.interp(np.arange(0, len(up) - 1, 0.25), np.arange(len(up)), up)).max()) < -1.5


def test_an_effect_lands_its_loudest_moment_on_the_cue(tmp_path):
    t = np.arange(4 * sound.RATE) / sound.RATE
    voice = 0.1 * np.sin(2 * np.pi * 220 * t) * (t < 1)
    out = tmp_path / "m.wav"
    sound.master(_wav(tmp_path, voice), [sound.Cue("pop", 2.5)], 4.0, out)
    a = sound._decode(out)
    tail = np.abs(a[2 * sound.RATE:])
    assert abs(2 + np.argmax(tail) / sound.RATE - 2.5) < 0.05  # the pop, where the voice is silent
    sound.master(_wav(tmp_path, np.zeros(sound.RATE, np.float32)), [sound.Cue("pop", 0.5)], 1.0, out)
    assert np.abs(sound._decode(out)).max() == 0  # silence stays silence: nothing to set the effect against


# ---- the neon style: three accents named by the scene, not found in the picture ----

def _rt(*actions, title=None, elements=()):
    return {"title": title, "elements": [{"id": "h", "kind": "hero"}, {"id": "n", "kind": "icon"}, *elements],
            "actions": [{"t": t, "do": do, "ids": ids, **more} for t, do, ids, more in actions]}


TITLE = {"lines": ["x"], "size": 46, "t0": 0.5, "t1": 3.4, "out": 3.86}


def test_scene_cues_three_at_most_and_spaced():
    rt = _rt((0.4, "type", ["a"], {}), (4.2, "on", ["n"], {}), (4.9, "tone", ["n"], {"to": "risk"}), (30.0, "draw", ["h"], {"d": 0.7}),
             title=TITLE)  # the first action after the title is at 4.2; the red one 0.7 s later is under SPACE and goes
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 4.2), sound.Cue("pop", 30.0)]


def test_scene_cues_each_at_its_own_moment_in_time_order():
    rt = _rt((0.4, "type", ["a"], {}), (5.0, "on", ["n"], {}), (20.0, "tone", ["n"], {"to": "safe"}), (22.0, "tone", ["n"], {"to": "risk"}),
             (23.0, "tone", ["n"], {"to": "risk"}), (40.0, "on", ["n"], {}), (41.0, "on", ["h"], {}), (50.0, "draw", ["h"], {"d": 0.7}),
             title=TITLE)
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 5.0), sound.Cue("glitch", 22.0), sound.Cue("pop", 41.0)]


def test_scene_cues_whoosh_waits_for_the_title_bar_to_leave_and_without_a_bar_takes_the_first_action():
    acts = [(0.4, "type", ["a"], {}), (3.0, "on", ["n"], {}), (6.0, "on", ["n"], {})]
    assert sound.scene_cues(_rt(*acts, title=TITLE)) == [sound.Cue("whoosh", 6.0)]
    assert sound.scene_cues(_rt(*acts)) == [sound.Cue("whoosh", 0.4)]


def test_scene_cues_nothing_to_accent_is_no_cue():
    assert sound.scene_cues(_rt(title=TITLE)) == []
    assert sound.scene_cues(_rt((5.0, "tone", ["n"], {"to": "dim"}), (6.0, "tone", ["n"], {"to": "claim"}), (8.0, "type", ["h"], {"d": 1}),
                                title=TITLE)) == [sound.Cue("whoosh", 5.0)]  # no red, and a hero that is only typed does not pop


def test_scene_cues_every_name_is_a_sound_in_the_library():
    assert all((sound.SFX / f"{n}.mp3").exists() for n in ("whoosh", "glitch", "pop"))


RED = {"id": "r", "kind": "icon", "tone": "risk"}  # a `state` that came before it was shown has made it red from the start


def test_scene_cues_glitch_also_where_an_element_that_starts_red_is_first_shown():
    rt = _rt((5.0, "on", ["n"], {}), (20.0, "draw", ["r"], {"d": 0.6}), (40.0, "tone", ["n"], {"to": "risk"}), title=TITLE, elements=[RED])
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 5.0), sound.Cue("glitch", 20.0)]  # the earlier of the two kinds of red
    rt = _rt((5.0, "on", ["n"], {}), (20.0, "tone", ["n"], {"to": "risk"}), (40.0, "type", ["r"], {"d": 0.6}), title=TITLE, elements=[RED])
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 5.0), sound.Cue("glitch", 20.0)]
    rt = _rt((5.0, "on", ["n"], {}), (20.0, "off", ["r"], {}), (22.0, "tone", ["r"], {"to": "dim"}), title=TITLE, elements=[RED])
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 5.0)]  # shown only by on/draw/type: an off or a dim is not the red arriving


def test_scene_cues_the_opening_hero_under_the_title_bar_takes_neither_the_pop_nor_the_glitch():
    rt = _rt((0.0, "draw", ["h"], {"d": 0.7}), (5.0, "on", ["n"], {}), (30.0, "draw", ["h"], {"d": 0.7}), title=TITLE)
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 5.0), sound.Cue("pop", 30.0)]
    # a red opening icon is not the moment the attack lands: the glitch waits for the first red of the diagram
    rt = _rt((0.0, "draw", ["r"], {"d": 0.7}), (5.0, "on", ["n"], {}), (20.0, "tone", ["n"], {"to": "risk"}), title=TITLE, elements=[RED])
    assert sound.scene_cues(rt) == [sound.Cue("whoosh", 5.0), sound.Cue("glitch", 20.0)]
