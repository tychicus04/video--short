from pathlib import Path

import numpy as np

from vshort import kit, sound
from vshort.motion import Scene
from vshort.render import Segment


def _seg(i, a, b, group, scene=None):
    return Segment(i, a, b, Path(f"f{i}.png"), group, scene)


def test_three_accents_on_moments_the_picture_makes():
    segs = [_seg(1, 0, 3, "s0"), _seg(2, 3, 9, "m0", 0), _seg(3, 9, 12, "m0", 0), _seg(4, 12, 15, "v4"),
            _seg(5, 15, 18, "v5")]
    canvas = Scene([2, 3], [], [kit.Act("draw", "a", 3, 3.8), kit.Act("red", "srv", 7.5, 8.1),
                                kit.Act("red", "db", 10, 10.6)])
    assert sound.cues(segs, [canvas]) == [sound.Cue("whoosh", 3), sound.Cue("glitch", 7.5), sound.Cue("pop", 12)]
    # a video that opens on the canvas has no cut into it; an effect right after another is dropped
    segs[0], canvas.acts[1:] = _seg(1, 0, 3, "m0", 0), [kit.Act("red", "srv", 11, 11.6)]
    assert sound.cues(segs, [canvas]) == [sound.Cue("glitch", 11)]
    assert sound.cues([_seg(1, 0, 3, "s0"), _seg(2, 3, 5, "s1")], []) == []


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
