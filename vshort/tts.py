"""Gemini text-to-speech: one WAV per sentence, cached by text, stopping cleanly when quota runs out."""
import hashlib
import io
import os
import re
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vshort.script import syllables


class QuotaExceeded(Exception):
    pass


class Speaker(Protocol):
    def __call__(self, text: str) -> bytes: ...


@dataclass
class Clip:
    id: int
    path: Path
    duration: float


def load_api_key(env_file: Path) -> str:
    if key := os.environ.get("GEMINI_API_KEY"):
        return key
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "GEMINI_API_KEY" and value.strip():
                return value.strip().strip("\"'")
    raise RuntimeError("Không tìm thấy GEMINI_API_KEY")


def _pcm_to_wav(data: bytes, mime: str) -> bytes:
    if not re.match(r"audio/(l16|pcm)", mime.lower()):
        return data
    m = re.search(r"rate=(\d+)", mime)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(m.group(1)) if m else 24000)
        w.writeframes(data)
    return buf.getvalue()


def _speaker_from_client(client, model: str, voice: str) -> Callable[[str], bytes]:
    from google.genai import errors, types

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)),
            language_code="vi",
        ),
    )

    def speak(text: str) -> bytes:
        try:
            resp = client.models.generate_content(model=model, contents=text, config=config)
        except errors.APIError as e:
            if e.code == 429 or "RESOURCE_EXHAUSTED" in str(e):
                raise QuotaExceeded() from None
            raise
        part = next(p for p in resp.candidates[0].content.parts if p.inline_data)
        return _pcm_to_wav(part.inline_data.data, part.inline_data.mime_type or "")

    return speak


def gemini_speaker(api_key: str, model: str, voice: str) -> Speaker:
    from google import genai

    return _speaker_from_client(genai.Client(api_key=api_key), model, voice)


def _duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def synth_all(lines: list[tuple[int, str]], out_dir: Path, speak: Speaker, tag: str) -> list[Clip]:
    """Synthesize each (id, text); files already on disk for the same text are reused, not re-requested."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, text in lines:
        path = out_dir / f"{i}-{hashlib.sha1((tag + text).encode()).hexdigest()[:10]}.wav"
        if not path.exists():
            data = speak(text)  # QuotaExceeded propagates; finished files stay
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.rename(path)
        clips.append(Clip(i, path, _duration(path)))
    return clips


def measured_rate(clips: list[Clip], lines: list[tuple[int, str]]) -> float:
    text = dict(lines)
    return sum(syllables(text[c.id]) for c in clips) / sum(c.duration for c in clips)
