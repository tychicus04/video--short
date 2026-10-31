import io
import wave
from types import SimpleNamespace

import pytest
from conftest import wav_bytes
from google.genai import errors

from vshort.tts import QuotaExceeded, _speaker_from_client, load_api_key, measured_rate, synth_all


def test_cache_skips_existing(tmp_path):
    calls = []
    speak = lambda text: calls.append(text) or wav_bytes(1.0)  # noqa: E731
    synth_all([(1, "Xin chào bạn")], tmp_path, speak, tag="v1")
    clips = synth_all([(1, "Xin chào bạn")], tmp_path, speak, tag="v1")
    assert len(calls) == 1 and abs(clips[0].duration - 1.0) < 0.01


def test_quota_stops_and_keeps_finished(tmp_path):
    def speak(text):
        if text == "hai":
            raise QuotaExceeded()
        return wav_bytes(0.5)

    with pytest.raises(QuotaExceeded):
        synth_all([(1, "một"), (2, "hai"), (3, "ba")], tmp_path, speak, tag="t")
    assert len(list(tmp_path.glob("1-*.wav"))) == 1 and not list(tmp_path.glob("2-*.wav"))


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
