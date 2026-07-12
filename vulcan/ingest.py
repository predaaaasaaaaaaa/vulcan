"""Stage 1 — ingest: voice note → mastered.wav.

Chain: decode → light denoise (afftdn) → two-pass loudnorm to target LUFS.
The mastered track IS the final video audio, so this runs once and everything
downstream (ASR, beats, render, QC) shares the exact same timeline.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

TARGET_SR = 48000


class IngestError(RuntimeError):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise IngestError(f"ffmpeg failed ({' '.join(cmd[:6])}…): {proc.stderr[-800:]}")
    return proc


def probe_duration_ms(path: Path) -> int:
    proc = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ])
    dur = float(json.loads(proc.stdout)["format"]["duration"])
    return round(dur * 1000)


def measure_loudness(path: Path, target_lufs: float) -> dict:
    """First loudnorm pass: measure integrated loudness stats."""
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    # loudnorm prints its JSON block to stderr after the progress noise
    tail = proc.stderr[proc.stderr.rfind("{"):]
    start = proc.stderr.rfind("{")
    if start == -1:
        raise IngestError(f"loudnorm measure pass produced no JSON: {proc.stderr[-400:]}")
    return json.loads(tail[: tail.rfind("}") + 1])


def master(voice_path: str | Path, out_dir: str | Path, target_lufs: float = -14.0) -> Path:
    """voice.(ogg|mp3|m4a|wav) → out_dir/mastered.wav (mono, 48k, denoised, −14 LUFS)."""
    voice_path = Path(voice_path)
    if not voice_path.exists():
        raise IngestError(f"input not found: {voice_path}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    denoised = out_dir / "denoised.wav"
    mastered = out_dir / "mastered.wav"

    # Pass 0: decode + light broadband denoise + SILENCE CAP + gentle 3:1
    # compression. nr=12 is gentle — voice notes are phone-mic recordings;
    # heavier NR smears consonants and hurts ASR. The silence cap trims any
    # internal pause beyond ~0.9s: long dead air is unwatchable in short-form
    # AND breaks beat math (a real 9.15s pause made a single-word beat span
    # >5s — unrepairable by cutting; see post-mortem 2026-07-12). ASR runs on
    # this same mastered track, so the timeline stays consistent everywhere.
    # The compressor tames peaks so the linear loudnorm below can actually
    # reach the target without hitting the TP cap.
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(voice_path),
        "-ac", "1", "-ar", str(TARGET_SR),
        "-af", (
            "afftdn=nr=12:nf=-28,"
            "silenceremove=stop_periods=-1:stop_duration=0.9:stop_threshold=-38dB,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=120:makeup=4dB"
        ),
        str(denoised),
    ])

    # Pass 1+2: measured (linear) loudnorm — true two-pass for accurate LUFS.
    m = measure_loudness(denoised, target_lufs)
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(denoised),
        "-af", (
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:"
            f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
            f"offset={m['target_offset']}:linear=true"
        ),
        "-ar", str(TARGET_SR), "-ac", "1",
        str(mastered),
    ])
    denoised.unlink(missing_ok=True)

    # Residual correction: if the TP ceiling still forced an undershoot, apply
    # the remaining gain through a limiter. Keeps the result deterministic and
    # inside qc tolerance for any input dynamics.
    got = float(measure_loudness(mastered, target_lufs)["input_i"])
    delta = target_lufs - got
    if abs(delta) > 0.5:
        corrected = out_dir / "mastered_corr.wav"
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(mastered),
            "-af", f"volume={delta:.2f}dB,alimiter=limit=0.84:attack=3:release=60:level=false",
            "-ar", str(TARGET_SR), "-ac", "1",
            str(corrected),
        ])
        corrected.replace(mastered)
    return mastered


def verify_lufs(path: Path, target_lufs: float, tolerance: float = 1.0) -> float:
    """Return measured integrated LUFS; raise if outside tolerance."""
    m = measure_loudness(path, target_lufs)
    got = float(m["input_i"])
    if abs(got - target_lufs) > tolerance:
        raise IngestError(f"mastered LUFS {got} outside {target_lufs}±{tolerance}")
    return got
