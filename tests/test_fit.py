import wave
from pathlib import Path

import numpy as np
import pytest

from vshort.fit import Placement, build_narration, phrase_fracs, phrase_times, sequence, total
from vshort.tts import Clip


def test_sequence_lays_clips_back_to_back():
    clips = [Clip(1, Path("a"), 2.0), Clip(3, Path("b"), 1.0), Clip(4, Path("c"), 1.5)]
    p = sequence(clips)
    assert [(x.id, round(x.start, 2), x.dur) for x in p] == [(1, 0.2, 2.0), (3, 2.7, 1.0), (4, 4.2, 1.5)]
    assert round(total(p), 2) == 6.2


def test_phrase_times_contiguous():
    p = [Placement(1, 0.5, 2.0), Placement(2, 3.0, 1.0)]
    out = phrase_times(p, [{"id": 1, "phrases": "Câu đầu trọn vẹn"}, {"id": 2, "phrases": "một hai | ba bốn"}])
    assert out[0][0] == 0.0 and out[0][2] == "Câu đầu trọn vẹn"
    assert [round(x[0], 2) for x in out[1:]] == [3.0, 3.5] and out[0][1] == out[1][0]


def test_phrase_fracs_split_by_syllables():
    assert phrase_fracs("một hai | ba") == [(0.0, 2 / 3), (2 / 3, 1.0)]
    assert phrase_fracs("một") == [(0.0, 1.0)]


def _tone(path: Path, seconds: float) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(np.full(round(seconds * 24000), 3000, np.int16).tobytes())
    return path


def test_build_narration_places_clips(tmp_path):
    clips = [Clip(1, _tone(tmp_path / "a.wav", 1.0), 1.0), Clip(2, _tone(tmp_path / "b.wav", 1.1), 1.1)]
    p = [Placement(1, 0.5, 1.0), Placement(2, 2.0, 1.1)]
    out = tmp_path / "n.wav"
    build_narration(p, clips, total=4.0, out_wav=out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 96000
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    loud = np.abs(a) > 1000
    assert not loud[: int(0.45 * 24000)].any() and loud[int(0.6 * 24000)] and loud[int(2.5 * 24000)]
    assert not loud[int(3.2 * 24000):].any()  # no tempo change: the 1.1 s clip lasts 1.1 s, ends at 3.1


def test_build_narration_plays_the_clips_at_the_tempo(tmp_path):
    clips = [Clip(1, _tone(tmp_path / "a.wav", 1.0), 1.0)]
    out = tmp_path / "n.wav"
    build_narration(sequence(clips, 1.25), clips, total=2.0, out_wav=out, tempo=1.25)
    with wave.open(str(out)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    loud = np.abs(a) > 1000
    assert loud[int(0.6 * 24000)] and not loud[int(1.1 * 24000):].any()  # 0.2 + 1.0 / 1.25 = 1.0: over by 1.1 s, not 1.2
