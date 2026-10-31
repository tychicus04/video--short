import wave
from pathlib import Path

import numpy as np

from vshort.fit import Placement, build_narration, phrase_times, place, too_long
from vshort.script import Sentence
from vshort.tts import Clip

S = [Sentence(1, 0.0, 3.0, "a"), Sentence(2, 3.0, 5.0, "b")]


def test_place_tempo_capped_and_overflow():
    clips = [Clip(1, Path("x"), 2.0), Clip(2, Path("y"), 2.6)]
    p = place(S, clips, cut=5.0)
    assert p[0].tempo == 1.0 and abs(p[1].tempo - 1.10) < 1e-9
    assert abs(p[1].overflow - (2.6 / 1.10 - 2.0)) < 1e-6 and too_long(p) == [2]


def test_next_sentence_waits_for_spill():
    clips = [Clip(1, Path("x"), 3.6), Clip(2, Path("y"), 1.0)]
    p = place(S, clips, cut=6.0)
    assert p[1].start >= p[0].start + p[0].dur + 0.1 - 1e-9


def test_phrase_times_contiguous():
    p = [Placement(1, 0.5, 2.0, 1.0, 0.0), Placement(2, 3.0, 1.0, 1.0, 0.0)]
    out = phrase_times(p, [{"id": 1, "phrases": "Câu đầu trọn vẹn"}, {"id": 2, "phrases": "một hai | ba bốn"}])
    assert out[0][0] == 0.0 and out[0][2] == "Câu đầu trọn vẹn"
    assert [round(x[0], 2) for x in out[1:]] == [3.0, 3.5] and out[0][1] == out[1][0]


def _tone(path: Path, seconds: float) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(np.full(round(seconds * 24000), 3000, np.int16).tobytes())
    return path


def test_build_narration_places_and_speeds_up(tmp_path):
    clips = [Clip(1, _tone(tmp_path / "a.wav", 1.0), 1.0), Clip(2, _tone(tmp_path / "b.wav", 1.1), 1.1)]
    p = [Placement(1, 0.5, 1.0, 1.0, 0.0), Placement(2, 2.0, 1.0, 1.1, 0.0)]
    out = tmp_path / "n.wav"
    build_narration(p, clips, total=4.0, out_wav=out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 96000
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    loud = np.abs(a) > 1000
    assert not loud[: int(0.45 * 24000)].any() and loud[int(0.6 * 24000)] and loud[int(2.5 * 24000)]
    assert not loud[int(3.1 * 24000):].any()  # 1.1 s at tempo 1.1 lasts 1.0 s: ends by 3.0
