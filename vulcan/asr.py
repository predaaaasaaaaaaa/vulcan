"""Stage 2 — ASR: mastered.wav → words.json (word-level ms timestamps).

Engine decided by Phase-2 benchmark (see BUILDLOG). The output contract is the
single source of truth for ALL downstream timing — the Director never invents
timestamps, it only groups these words into beats.

words.json:
{
  "engine": "faster-whisper/small/int8",
  "language": "en",
  "duration_ms": 61234,
  "text": "full transcript…",
  "words": [{"w": "nobody", "s": 120, "e": 410, "p": 0.94}, …]
}
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def transcribe_faster_whisper(
    wav_path: str | Path,
    model_size: str = "small",
    compute_type: str = "int8",
    language: str | None = None,
    device: str = "cpu",
) -> dict:
    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(wav_path),
        word_timestamps=True,
        language=language,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        beam_size=5,
    )
    words = []
    texts = []
    for seg in segments:
        texts.append(seg.text)
        for w in seg.words or []:
            token = w.word.strip()
            if not token:
                continue
            words.append({
                "w": token,
                "s": round(w.start * 1000),
                "e": round(w.end * 1000),
                "p": round(float(w.probability), 3),
            })
    _normalize_words(words)
    return {
        "engine": f"faster-whisper/{model_size}/{compute_type}",
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "elapsed_s": round(time.time() - t0, 1),
        "text": "".join(texts).strip(),
        "words": words,
    }


def _normalize_words(words: list[dict]) -> None:
    """Deterministic cleanup of known whisper quirks (in place).

    Zero-duration words get a 20ms floor; timestamps are clamped monotonic.
    This is mechanical normalization of ASR output, not timing invention.
    """
    prev_s = 0
    for w in words:
        if w["s"] < prev_s:
            w["s"] = prev_s
        if w["e"] <= w["s"]:
            w["e"] = w["s"] + 20
        prev_s = w["s"]


def sanity_check_words(words: list[dict], duration_ms: int) -> list[str]:
    """Deterministic alignment sanity — failures here abort the run loudly."""
    problems = []
    if not words:
        return ["no words recognized"]
    prev_s = -1
    low_conf = 0
    for w in words:
        if w["s"] >= w["e"]:
            problems.append(f"word '{w['w']}' zero/negative duration ({w['s']}→{w['e']})")
        if w["e"] > duration_ms + 500:
            problems.append(f"word '{w['w']}' ends past audio ({w['e']} > {duration_ms})")
        if w["s"] < prev_s:
            problems.append(f"word '{w['w']}' timestamps regress")
        if w["e"] - w["s"] > 3000:
            problems.append(f"word '{w['w']}' suspiciously long ({w['e'] - w['s']}ms)")
        if w.get("p", 1.0) < 0.30:
            low_conf += 1
        prev_s = w["s"]
    if low_conf / len(words) > 0.25:
        problems.append(f"{low_conf}/{len(words)} words below 0.30 confidence — audio likely unusable")
    return problems


def run_asr(wav_path: str | Path, out_path: str | Path, duration_ms: int,
            model_size: str = "small", compute_type: str = "int8",
            language: str | None = None) -> dict:
    result = transcribe_faster_whisper(
        wav_path, model_size=model_size, compute_type=compute_type, language=language
    )
    result["duration_ms"] = duration_ms
    problems = sanity_check_words(result["words"], duration_ms)
    if problems:
        raise RuntimeError("ASR sanity check failed: " + "; ".join(problems[:5]))
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return result
