"""Deterministic music beds — 5 mood loops, CC0-by-construction.

Each bed: 16s seamless loop, 48k stereo, chord pad + rhythm section, RMS
normalized to −28 dBFS (sits under −14 LUFS voice ≈ "felt, not heard";
the renderer ducks it further while words are spoken).

Run: .venv/bin/python sfx/music/build_music.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
OUT = Path(__file__).parent
RNG = np.random.default_rng(777)
RMS_DB = -28.0

# note name → semitone offset from A4=440
_NOTES = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


def hz(note: str, octave: int) -> float:
    return 440.0 * 2 ** ((_NOTES[note[0]] + (1 if "#" in note else 0) + (octave - 4) * 12) / 12)


def lp(x, cut, order=4):
    return signal.sosfilt(signal.butter(order, cut, btype="low", fs=SR, output="sos"), x)


def hp(x, cut, order=4):
    return signal.sosfilt(signal.butter(order, cut, btype="high", fs=SR, output="sos"), x)


def saw(freq, dur, detune=0.0):
    t = np.arange(int(dur * SR)) / SR
    return signal.sawtooth(2 * np.pi * freq * (1 + detune) * t)


def sine(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * freq * t)


def adsr(n, a, d, s_level, r):
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(n - a_n - d_n - r_n, 0)
    return np.concatenate([
        np.linspace(0, 1, max(a_n, 1)),
        np.linspace(1, s_level, max(d_n, 1)),
        np.full(s_n, s_level),
        np.linspace(s_level, 0, max(r_n, 1)),
    ])[:n]


def pad_chord(freqs, dur, bright=1400, soft=False):
    """Detuned saw (or sine) stack — the harmonic floor of every bed."""
    voices = []
    for f in freqs:
        if soft:
            v = sine(f, dur) + 0.5 * sine(f * 2, dur)
        else:
            v = saw(f, dur, -0.004) + saw(f, dur, 0.004) + 0.6 * sine(f / 2, dur)
        voices.append(v)
    x = np.sum(voices, axis=0) / len(voices)
    x = lp(x, bright)
    return x * adsr(len(x), 0.6, 0.5, 0.85, 0.8)


def kick(dur=0.28):
    t = np.arange(int(dur * SR)) / SR
    f = 120 * np.exp(-t * 22) + 42
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    return np.tanh(body * 2.2) * 0.9


def hat(dur=0.05, tone=8000):
    n = RNG.standard_normal(int(dur * SR))
    return hp(n, tone) * np.exp(-np.arange(int(dur * SR)) / SR * 60) * 0.35


def pluck(freq, dur=0.24):
    t = np.arange(int(dur * SR)) / SR
    x = signal.square(2 * np.pi * freq * t, duty=0.3) * 0.4 + sine(freq, dur) * 0.6
    return lp(x, 2600) * np.exp(-t * 8)


def bass(freq, dur):
    x = sine(freq, dur) + 0.3 * sine(freq * 2, dur)
    return lp(x, 300) * adsr(len(x), 0.01, 0.08, 0.7, 0.1)


def place(track, clip, at_s):
    i = int(at_s * SR)
    j = min(i + len(clip), len(track))
    if j > i:
        track[i:j] += clip[: j - i]


def make_loop(bpm, bars, build) -> np.ndarray:
    """build(track, beat_seconds, total_beats) fills the mono track; returns
    a seamless loop via 1s crossfade of tail onto head."""
    spb = 60.0 / bpm
    total = bars * 4 * spb
    n = int((total + 1.0) * SR)  # +1s tail for the crossfade
    track = np.zeros(n)
    build(track, spb, bars * 4)
    xfade = int(1.0 * SR)
    body = track[: int(total * SR)]
    tail = track[int(total * SR): int(total * SR) + xfade]
    ramp = np.linspace(0, 1, len(tail))
    body[: len(tail)] = body[: len(tail)] * ramp + tail * (1 - ramp)
    return body


def stereoize(x: np.ndarray) -> np.ndarray:
    """Cheap width: ±8ms haas + gentle HF tilt difference."""
    d = int(0.008 * SR)
    left = np.concatenate([x[d:], x[:d]])
    right = x
    return np.stack([left * 0.98, right], axis=1)


def normalize(x: np.ndarray) -> np.ndarray:
    rms = np.sqrt(np.mean(x ** 2))
    x = x * (10 ** (RMS_DB / 20) / max(rms, 1e-9))
    peak = np.abs(x).max()
    if peak > 0.891:  # −1 dBFS
        x *= 0.891 / peak
    return x


# ---------------------------------------------------------------- moods

def energetic(track, spb, beats):
    prog = [("A", 2, "min"), ("F", 2, "maj"), ("C", 3, "maj"), ("G", 2, "maj")]
    for bar in range(beats // 4):
        root, octv, qual = prog[bar % 4]
        third = 3 if qual == "min" else 4
        freqs = [hz(root, octv + 1), hz(root, octv + 1) * 2 ** (third / 12), hz(root, octv + 1) * 2 ** (7 / 12)]
        place(track, pad_chord(freqs, spb * 4, bright=1800) * 0.5, bar * 4 * spb)
        for b in range(4):
            place(track, kick(), (bar * 4 + b) * spb)
            place(track, hat(), (bar * 4 + b + 0.5) * spb)
            for e in (0, 0.5):
                place(track, bass(hz(root, octv), spb * 0.45) * 0.7, (bar * 4 + b + e) * spb)

def chill(track, spb, beats):
    prog = [("F", 2), ("E", 2), ("D", 2), ("C", 2)]
    for bar in range(beats // 4):
        root, octv = prog[bar % 4]
        freqs = [hz(root, octv + 1), hz(root, octv + 1) * 2 ** (4 / 12),
                 hz(root, octv + 1) * 2 ** (7 / 12), hz(root, octv + 1) * 2 ** (11 / 12)]
        place(track, pad_chord(freqs, spb * 4, soft=True) * 0.6, bar * 4 * spb)
        place(track, kick() * 0.6, bar * 4 * spb)
        place(track, kick() * 0.45, (bar * 4 + 2.5) * spb)
        for b in range(8):
            swing = 0.08 * spb if b % 2 else 0
            place(track, hat(tone=9000) * 0.5, (bar * 4 + b * 0.5) * spb + swing)
        place(track, bass(hz(root, octv), spb * 1.6) * 0.6, bar * 4 * spb)

def dramatic(track, spb, beats):
    prog = [("D", 2), ("A", 1), ("B", 1), ("A", 1)]
    for bar in range(beats // 4):
        root, octv = prog[bar % 4]
        freqs = [hz(root, octv + 1), hz(root, octv + 1) * 2 ** (3 / 12), hz(root, octv + 1) * 2 ** (7 / 12)]
        place(track, pad_chord(freqs, spb * 4, bright=900) * 0.65, bar * 4 * spb)
        place(track, kick() * 0.8, bar * 4 * spb)
        place(track, kick() * 0.5, (bar * 4 + 0.75) * spb)  # heartbeat pair
        place(track, bass(hz(root, octv - 1), spb * 3.5) * 0.8, bar * 4 * spb)

def uplifting(track, spb, beats):
    prog = [("C", 3), ("G", 2), ("A", 2), ("F", 2)]
    minor = {"A"}
    for bar in range(beats // 4):
        root, octv = prog[bar % 4]
        third = 3 if root in minor else 4
        base = hz(root, octv + 1)
        freqs = [base, base * 2 ** (third / 12), base * 2 ** (7 / 12)]
        place(track, pad_chord(freqs, spb * 4, bright=2200) * 0.45, bar * 4 * spb)
        arp = [base * 2, base * 2 ** (third / 12) * 2, base * 2 ** (7 / 12) * 2, base * 4]
        for e in range(8):
            place(track, pluck(arp[e % 4]) * 0.5, (bar * 4 + e * 0.5) * spb)
        place(track, kick() * 0.7, bar * 4 * spb)
        place(track, kick() * 0.7, (bar * 4 + 2) * spb)
        place(track, bass(hz(root, octv), spb * 0.9) * 0.6, bar * 4 * spb)

def tech(track, spb, beats):
    root_hz = hz("E", 2)
    seq = [1, 2 ** (3 / 12), 2 ** (7 / 12), 2 ** (10 / 12)]
    for bar in range(beats // 4):
        place(track, pad_chord([root_hz * 2, root_hz * 2 ** (7 / 12) * 2], spb * 4, bright=1200) * 0.35,
              bar * 4 * spb)
        for s in range(16):
            if s % 4 != 3:
                place(track, pluck(root_hz * 4 * seq[s % 4], 0.12) * 0.4, (bar * 4 + s * 0.25) * spb)
        for b in range(4):
            place(track, kick() * 0.65, (bar * 4 + b) * spb)
            place(track, hat(tone=10000) * 0.4, (bar * 4 + b + 0.5) * spb)


MOODS = {
    "energetic": (104, energetic),
    "chill": (82, chill),
    "dramatic": (72, dramatic),
    "uplifting": (112, uplifting),
    "tech": (96, tech),
}


if __name__ == "__main__":
    index = {}
    for mood, (bpm, build) in MOODS.items():
        bars = max(4, round(16 / (60.0 / bpm * 4)))
        mono = make_loop(bpm, bars, build)
        stereo = normalize(stereoize(mono))
        fname = f"bed_{mood}.wav"
        sf.write(OUT / fname, stereo.astype(np.float32), SR, subtype="PCM_16")
        index[mood] = {"file": f"music/{fname}", "bpm": bpm,
                       "loop_s": round(len(mono) / SR, 3)}
        print(f"{mood}: {bpm}bpm {len(mono)/SR:.1f}s loop")
    (OUT / "index.json").write_text(json.dumps({"beds": index}, indent=1))
    print("music index written")
