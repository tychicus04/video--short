import io
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from google.genai import errors

from vshort.tts import QuotaExceeded, _speaker_from_client, load_api_key, measured_rate, synth_script


def _speech_wav(parts: list[tuple[str, float]]) -> bytes:
    """parts: ("tone" | "gap", seconds) at 24 kHz mono 16-bit."""
    a = np.concatenate([np.full(round(s * 24000), 3000 if kind == "tone" else 0, np.int16) for kind, s in parts])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(a.tobytes())
    return buf.getvalue()


LINES = [(1, "một hai ba bốn"), (2, "năm sáu, bảy tám chín mười"), (3, "mười một mười hai")]
AUDIO = [("gap", 0.3), ("tone", 1.2), ("gap", 0.6), ("tone", 0.8), ("gap", 0.25), ("tone", 1.0), ("gap", 0.6),
         ("tone", 1.2), ("gap", 0.4)]


def test_one_call_split_at_sentence_gaps_not_commas(tmp_path):
    calls = []
    clips = synth_script(LINES, tmp_path, lambda text: calls.append(text) or _speech_wav(AUDIO), tag="t")
    assert len(calls) == 1 and calls[0] == "một hai ba bốn.\n\nnăm sáu, bảy tám chín mười.\n\nmười một mười hai."
    assert [c.id for c in clips] == [1, 2, 3]
    for c, speech in zip(clips, [1.2, 2.05, 1.2]):
        assert abs(c.duration - (speech + 0.1)) < 0.06  # speech + 0.05 s pad each side


def test_script_audio_is_cached(tmp_path):
    calls = []
    speak = lambda text: calls.append(text) or _speech_wav(AUDIO)  # noqa: E731
    synth_script(LINES, tmp_path, speak, tag="t")
    synth_script(LINES, tmp_path, speak, tag="t")
    assert len(calls) == 1


def test_quota_leaves_nothing_half_written(tmp_path):
    def speak(text):
        raise QuotaExceeded()

    with pytest.raises(QuotaExceeded):
        synth_script(LINES, tmp_path, speak, tag="t")
    assert not list(tmp_path.glob("*.wav"))


def test_unsplittable_audio_is_reported(tmp_path):
    with pytest.raises(ValueError, match="tách"):
        synth_script(LINES, tmp_path, lambda text: _speech_wav([("tone", 4.0)]), tag="t")


def test_load_api_key_never_leaks(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OTHER=1\nGEMINI_API_KEY=secret123\n")
    assert load_api_key(tmp_path / ".env") == "secret123"
    with pytest.raises(RuntimeError) as e:
        load_api_key(tmp_path / "missing.env")
    assert "secret" not in str(e.value)


def test_measured_rate():
    clips = [SimpleNamespace(id=1, duration=2.0), SimpleNamespace(id=2, duration=2.0)]
    assert measured_rate(clips, [(1, "một hai ba bốn"), (2, "năm sáu bảy tám chín mười")]) == 2.5


class FakeModels:
    def __init__(self, result):
        self.result, self.seen = result, []

    def generate_content(self, **kw):
        self.seen.append(kw)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _response(data: bytes, mime: str):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime))
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


def test_raw_pcm_is_wrapped_as_wav():
    models = FakeModels(_response(b"\0\0" * 24000, "audio/L16;codec=pcm;rate=24000"))
    out = _speaker_from_client(SimpleNamespace(models=models), "m", "Charon")("Xin chào")
    with wave.open(io.BytesIO(out)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 24000)
    cfg = models.seen[0]["config"]
    assert models.seen[0]["contents"] == "Xin chào"
    assert cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Charon"


def test_429_becomes_quota_exceeded():
    err = errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}})
    with pytest.raises(QuotaExceeded):
        _speaker_from_client(SimpleNamespace(models=FakeModels(err)), "m", "v")("x")


def _quota_error(quota_id: str, delay: str = "2s") -> errors.ClientError:
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}})


class FlakyModels(FakeModels):
    def __init__(self, errors_first, result):
        super().__init__(result)
        self.errors_first = list(errors_first)

    def generate_content(self, **kw):
        if self.errors_first:
            raise self.errors_first.pop(0)
        return super().generate_content(**kw)


def test_per_minute_limit_waits_and_retries():
    waits = []
    models = FlakyModels([_quota_error("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "7s")],
                         _response(b"\0\0" * 240, "audio/L16;rate=24000"))
    speak = _speaker_from_client(SimpleNamespace(models=models), "m", "v", sleep=waits.append)
    assert speak("x")[:4] == b"RIFF" and waits == [8.0]  # suggested delay + 1 s margin


def test_per_day_limit_stops_at_once():
    waits = []
    models = FlakyModels([_quota_error("GenerateRequestsPerDayPerProjectPerModel-FreeTier")], _response(b"", "audio/L16"))
    with pytest.raises(QuotaExceeded):
        _speaker_from_client(SimpleNamespace(models=models), "m", "v", sleep=waits.append)("x")
    assert waits == []


def test_silent_audio_is_reported(tmp_path):
    with pytest.raises(ValueError, match="khoảng lặng"):
        synth_script(LINES, tmp_path, lambda text: _speech_wav([("gap", 2.0)]), tag="t")


def test_uneven_speed_does_not_pull_cuts_onto_commas(tmp_path):
    # sentences 1–2 spoken slowly, 3–4 fast; sentence 2 has a comma pause where a whole-script
    # proportional estimate would expect the 2|3 boundary
    lines = [(1, "a b c d e f"), (2, "g h, i j k l"), (3, "m n o p q r"), (4, "s t u v w x")]
    audio = [("gap", 0.3), ("tone", 2.4), ("gap", 0.6), ("tone", 0.8), ("gap", 0.45), ("tone", 1.15), ("gap", 0.6),
             ("tone", 1.2), ("gap", 0.6), ("tone", 1.2), ("gap", 0.4)]
    clips = synth_script(lines, tmp_path, lambda text: _speech_wav(audio), tag="t")
    for c, speech in zip(clips, [2.4, 2.4, 1.2, 1.2]):
        assert abs(c.duration - (speech + 0.1)) < 0.06
