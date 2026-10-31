"""Gemini text-to-speech: one call for the whole script, cut into per-sentence clips; cached by text."""
import hashlib
import json
import io
import os
import re
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

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


def _per_minute_wait(e) -> float | None:
    """Seconds to wait when a 429 is a per-minute limit (free tier); None when the daily quota is gone."""
    body = json.dumps(e.details) if isinstance(getattr(e, "details", None), dict) else str(e)
    if "PerMinute" not in body:
        return None
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
    return (float(m.group(1)) if m else 59.0) + 1.0


def _speaker_from_client(client, model: str, voice: str, sleep: Callable[[float], None] = time.sleep,
                         retries: int = 10) -> Callable[[str], bytes]:
    from google.genai import errors, types

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)),
            language_code="vi",
        ),
    )

    def speak(text: str) -> bytes:
        for _ in range(retries + 1):
            try:
                resp = client.models.generate_content(model=model, contents=text, config=config)
                break
            except errors.APIError as e:
                if not (e.code == 429 or "RESOURCE_EXHAUSTED" in str(e)):
                    raise
                wait = _per_minute_wait(e)
                if wait is None:
                    raise QuotaExceeded() from None
                sleep(wait)
        else:
            raise QuotaExceeded()
        part = next(p for p in resp.candidates[0].content.parts if p.inline_data)
        return _pcm_to_wav(part.inline_data.data, part.inline_data.mime_type or "")

    return speak


def gemini_speaker(api_key: str, model: str, voice: str) -> Speaker:
    from google import genai

    return _speaker_from_client(genai.Client(api_key=api_key), model, voice)


def _duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def _script_text(lines: list[tuple[int, str]]) -> str:
    """One paragraph per sentence, each closed by punctuation, so the voice pauses clearly between them."""
    return "\n\n".join(t if t.rstrip()[-1:] in ".?!…" else t.rstrip() + "." for _, t in lines)


def _sentence_spans(a: np.ndarray, rate: int, weights: list[int]) -> list[tuple[int, int]]:
    """Cut one narration into len(weights) sentences at silences.

    Each sentence's piece should last about its syllables / the average speaking rate (judged per
    sentence, so speed changes don't accumulate), and longer pauses are preferred, so a comma's short
    pause loses to the pause between paragraphs.
    """
    hop = rate // 50  # 20 ms frames
    rms = np.sqrt(np.mean(a[: len(a) // hop * hop].astype(np.float64).reshape(-1, hop) ** 2, axis=1))
    silent = rms < 0.08 * np.percentile(rms, 95)
    voiced = np.where(~silent)[0]
    s0, s1 = int(voiced[0]), int(voiced[-1]) + 1
    gaps, run = [], None
    for f in range(s0, s1):
        if silent[f] and run is None:
            run = f
        elif not silent[f] and run is not None:
            if f - run >= 6:  # ≥ 0.12 s
                gaps.append((run, f))
            run = None
    n, m = len(weights), len(gaps)
    if m < n - 1:
        raise ValueError(f"Không tách được giọng đọc thành {n} câu: chỉ có {m} khoảng lặng giữa câu")
    speech = max((s1 - s0) - 25 * (n - 1), 1)  # minus ~0.5 s of pause per sentence break
    expected = [w * speech / sum(weights) for w in weights]

    def piece(k: int, b: int, e: int) -> float:
        return abs((e - b) - expected[k]) / expected[k]

    def bonus(j: int) -> float:
        return 2 * (gaps[j][1] - gaps[j][0]) / 50

    chosen: list[tuple[int, int]] = []
    if n > 1:
        best = [[float("inf")] * m for _ in range(n - 1)]
        back = [[-1] * m for _ in range(n - 1)]
        for j in range(m):
            best[0][j] = piece(0, s0, gaps[j][0]) - bonus(j)
        for k in range(1, n - 1):
            for j in range(k, m):
                for jj in range(k - 1, j):
                    c = best[k - 1][jj] + piece(k, gaps[jj][1], gaps[j][0]) - bonus(j)
                    if c < best[k][j]:
                        best[k][j], back[k][j] = c, jj
        j = min(range(n - 2, m), key=lambda jj: best[n - 2][jj] + piece(n - 1, gaps[jj][1], s1))
        for k in range(n - 2, -1, -1):
            chosen.append(gaps[j])
            j = back[k][j]
        chosen.reverse()
    pad = hop * 5 // 2  # 0.05 s
    edges = [s0] + [x for g in chosen for x in g] + [s1]
    return [(max(edges[2 * k] * hop - pad, 0), min(edges[2 * k + 1] * hop + pad, len(a))) for k in range(n)]


def _write_wav(path: Path, a: np.ndarray, rate: int) -> None:
    tmp = path.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(a.astype(np.int16).tobytes())
    tmp.rename(path)


def synth_script(lines: list[tuple[int, str]], out_dir: Path, speak: Speaker, tag: str) -> list[Clip]:
    """One TTS call for the whole script (free tier: 10 calls/day), cut into one clip per sentence.

    The narration is cached by its text, so a rerun or a crash after the call costs no new request.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    text = _script_text(lines)
    key = hashlib.sha1((tag + text).encode()).hexdigest()[:10]
    full = out_dir / f"script-{key}.wav"
    if not full.exists():
        data = speak(text)  # QuotaExceeded propagates before anything is written
        tmp = full.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.rename(full)
    paths = [out_dir / f"{i}-{key}.wav" for i, _ in lines]
    if not all(p.exists() for p in paths):
        with wave.open(str(full)) as w:
            rate, a = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), np.int16)
        for p, (b, e) in zip(paths, _sentence_spans(a, rate, [max(syllables(t), 1) for _, t in lines])):
            _write_wav(p, a[b:e], rate)
    return [Clip(i, p, _duration(p)) for (i, _), p in zip(lines, paths)]


def measured_rate(clips: list[Clip], lines: list[tuple[int, str]]) -> float:
    text = dict(lines)
    return sum(syllables(text[c.id]) for c in clips) / sum(c.duration for c in clips)
