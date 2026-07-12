"""Deterministic SFX synthesis — 43 motion-graphics cues, CC0-by-construction.

Every cue is layered DSP (numpy/scipy): filtered noise, pitch-enveloped tones,
FM bells, gated squares. Seeded RNG → identical files on every build.
Output: 48k mono 16-bit wav, RMS-normalized to a shared bus level so the
renderer mixes them at volume=1 and the final program hits the config target.

Run: .venv/bin/python sfx/build_sfx.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
OUT = Path(__file__).parent
RNG = np.random.default_rng(4242)
BUS_RMS_DB = -20.0
PEAK_DB = -3.0


# ---------------------------------------------------------------- primitives

def t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def env_exp(dur: float, tau: float, attack: float = 0.002) -> np.ndarray:
    x = t(dur)
    e = np.exp(-x / tau)
    a = np.clip(x / max(attack, 1e-4), 0, 1)
    return e * a


def env_arc(dur: float, peak_at: float = 0.4) -> np.ndarray:
    """Smooth rise-fall arc (whoosh/swish body)."""
    x = np.linspace(0, 1, int(dur * SR))
    up = np.clip(x / peak_at, 0, 1)
    down = np.clip((1 - x) / (1 - peak_at), 0, 1)
    return (np.sin(np.minimum(up, 1) * np.pi / 2) * np.sin(np.minimum(down, 1) * np.pi / 2)) ** 1.4


def noise(dur: float) -> np.ndarray:
    return RNG.standard_normal(int(dur * SR))


def bp(x: np.ndarray, lo: float, hi: float, order: int = 4) -> np.ndarray:
    sos = signal.butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def lp(x: np.ndarray, cut: float, order: int = 4) -> np.ndarray:
    sos = signal.butter(order, cut, btype="low", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def hp(x: np.ndarray, cut: float, order: int = 4) -> np.ndarray:
    sos = signal.butter(order, cut, btype="high", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def sweep_bp(x: np.ndarray, f0: float, f1: float, width_oct: float = 1.0, blocks: int = 48) -> np.ndarray:
    """Time-varying bandpass — overlap-added blocks with raised-cosine
    crossfades so filter switching never buzzes."""
    n = len(x)
    out = np.zeros(n)
    win_acc = np.zeros(n) + 1e-9
    hop = n // blocks
    win_len = hop * 2
    window = np.hanning(win_len)
    for i in range(blocks):
        a = i * hop
        b = min(a + win_len, n)
        if b <= a:
            continue
        f = f0 * (f1 / f0) ** (i / max(blocks - 1, 1))
        lo = max(f / (2 ** (width_oct / 2)), 30)
        hi = min(f * (2 ** (width_oct / 2)), SR / 2 - 200)
        seg = bp(x[a:b], lo, hi) * window[: b - a]
        out[a:b] += seg
        win_acc[a:b] += window[: b - a]
    return out / win_acc


def tone(dur: float, f0: float, f1: float | None = None, kind: str = "sine") -> np.ndarray:
    """Tone with exponential pitch glide f0→f1."""
    x = t(dur)
    f1 = f1 or f0
    freq = f0 * (f1 / f0) ** (x / max(dur, 1e-6))
    phase = 2 * np.pi * np.cumsum(freq) / SR
    if kind == "saw":
        return signal.sawtooth(phase)
    if kind == "square":
        return signal.square(phase)
    return np.sin(phase)


def fm_bell(dur: float, f: float, partials: list[tuple[float, float]], tau: float) -> np.ndarray:
    x = t(dur)
    out = np.zeros_like(x)
    for ratio, amp in partials:
        out += amp * np.sin(2 * np.pi * f * ratio * x) * np.exp(-x / (tau / ratio ** 0.6))
    return out


def click(freq: float = 3200, dur: float = 0.008, body: float = 0.5) -> np.ndarray:
    n = noise(dur)
    c = bp(n, freq * 0.6, min(freq * 1.8, SR / 2 - 200)) * env_exp(dur, dur / 3, attack=0.0005)
    return c * body


def mix(*layers: np.ndarray) -> np.ndarray:
    n = max(len(l) for l in layers)
    out = np.zeros(n)
    for l in layers:
        out[: len(l)] += l
    return out


def delay(x: np.ndarray, seconds: float) -> np.ndarray:
    pad = np.zeros(int(seconds * SR))
    return np.concatenate([pad, x])


def soft(x: np.ndarray, drive: float = 1.0) -> np.ndarray:
    return np.tanh(x * drive)


def normalize(x: np.ndarray) -> np.ndarray:
    active = x[np.abs(x) > np.abs(x).max() * 0.01]
    rms = np.sqrt(np.mean(active ** 2)) if len(active) else 1e-9
    x = x * (10 ** (BUS_RMS_DB / 20) / max(rms, 1e-9))
    peak_lim = 10 ** (PEAK_DB / 20)
    peak = np.abs(x).max()
    if peak > peak_lim:
        x = x * (peak_lim / peak)
    return x


# ---------------------------------------------------------------- cue recipes

def whoosh(dur: float, f0: float, f1: float, peak_at: float = 0.45, width: float = 1.2) -> np.ndarray:
    return sweep_bp(noise(dur), f0, f1, width) * env_arc(dur, peak_at)

def pop(f0: float, f1: float, dur: float = 0.14, snap: float = 0.0) -> np.ndarray:
    body = tone(dur, f0, f1) * env_exp(dur, dur / 4)
    layers = [body]
    if snap > 0:
        layers.append(click(4200, 0.006, snap))
    return mix(*layers)

def boom(f0: float, f1: float, dur: float, punch: float = 0.0, drive: float = 1.6) -> np.ndarray:
    body = soft(tone(dur, f0, f1) * env_exp(dur, dur / 3.2), drive)
    layers = [body, lp(noise(dur), 140) * env_exp(dur, dur / 4) * 0.5]
    if punch:
        layers.append(bp(noise(0.05), 200, 900) * env_exp(0.05, 0.012) * punch)
    return mix(*layers)

def jingle(n_coins: int, dur: float) -> np.ndarray:
    out = np.zeros(int(dur * SR))
    for i in range(n_coins):
        f = float(RNG.uniform(3800, 7600))
        start = RNG.uniform(0, dur * 0.5)
        c = fm_bell(0.3, f, [(1, 1), (1.51, 0.5)], 0.06) * 0.6
        s = int(start * SR)
        out[s:s + len(c)] += c[: len(out) - s]
    return out


CUES: dict[str, np.ndarray] = {}

def build_all() -> dict[str, np.ndarray]:
    C = CUES
    C["whoosh_01"] = whoosh(0.45, 500, 4200)
    C["whoosh_02"] = mix(whoosh(0.6, 220, 1400, 0.5, 1.5), lp(noise(0.6), 500) * env_arc(0.6, 0.5) * 0.6)
    C["whoosh_03"] = whoosh(0.24, 1200, 6500, 0.35)
    C["whoosh_04"] = mix(whoosh(0.3, 800, 5000, 0.4), delay(whoosh(0.3, 1000, 5600, 0.4), 0.13))
    C["whoosh_05"] = whoosh(0.5, 4000, 400, 0.62)  # reverse-feel: high→low swell
    C["pop_01"] = pop(380, 170)
    C["pop_02"] = pop(950, 340, 0.1)
    C["pop_03"] = pop(520, 210, 0.12, snap=0.8)
    C["pop_04"] = mix(pop(500, 220, 0.11, 0.4), delay(pop(650, 280, 0.11, 0.4), 0.09))
    C["click_01"] = click(3400, 0.007, 1.0)
    C["click_02"] = mix(click(2400, 0.005), delay(click(1500, 0.009, 0.7), 0.012))
    C["click_03"] = mix(click(3000, 0.006), delay(lp(noise(0.05), 900) * env_exp(0.05, 0.015) * 0.5, 0.008))
    C["tick_01"] = click(5200, 0.008, 0.9)
    C["tick_02"] = mix(click(2100, 0.012), tone(0.03, 320, 300) * env_exp(0.03, 0.01) * 0.4)
    C["tick_03"] = lp(click(2600, 0.012), 3000)
    C["boom_01"] = boom(85, 42, 1.1, punch=0.6)
    C["boom_02"] = boom(95, 34, 0.85, drive=2.0)
    C["boom_03"] = boom(120, 70, 0.35, punch=1.0)
    C["ding_01"] = fm_bell(0.85, 1318, [(1, 1), (2.76, 0.35), (5.4, 0.12)], 0.28)
    C["ding_02"] = fm_bell(0.55, 1760, [(1, 1), (2.4, 0.3)], 0.16)
    C["ding_03"] = mix(fm_bell(0.5, 1318, [(1, 1), (2.76, 0.3)], 0.2),
                       delay(fm_bell(0.6, 1760, [(1, 1), (2.76, 0.3)], 0.24), 0.12))
    C["riser_01"] = sweep_bp(noise(1.2), 300, 3200, 1.3) * (np.linspace(0, 1, int(1.2 * SR)) ** 2.2)
    C["riser_02"] = hp(noise(1.0), 300) * (np.linspace(0, 1, int(1.0 * SR)) ** 3)
    riser_saw = mix(tone(1.2, 110, 220, "saw") * 0.5, tone(1.2, 110.7, 221.4, "saw") * 0.5,
                    tone(1.2, 55, 110, "saw") * 0.35)
    C["riser_03"] = lp(riser_saw, 2600) * (np.linspace(0, 1, int(1.2 * SR)) ** 2)
    C["swish_01"] = bp(noise(0.3), 2000, 8000) * env_arc(0.3, 0.42)
    C["swish_02"] = lp(noise(0.42), 3000) * env_arc(0.42, 0.5)
    C["swish_03"] = bp(noise(0.18), 3000, 10000) * env_arc(0.18, 0.38)
    gate1 = (signal.square(2 * np.pi * np.cumsum(RNG.uniform(28, 80, int(0.32 * SR))) / SR) > 0)
    C["glitch_01"] = np.round(tone(0.32, 180, 160, "square") * gate1 * 6) / 6 * 0.8
    gate2 = (RNG.random(int(0.26 * SR)) > 0.4).astype(float)
    C["glitch_02"] = hp(noise(0.26), 900) * signal.medfilt(gate2, 199)
    C["stamp_01"] = mix(boom(150, 95, 0.4, punch=0.9, drive=1.3), delay(click(1800, 0.01, 0.5), 0.02))
    C["stamp_02"] = mix(boom(95, 55, 0.55, punch=1.0, drive=1.7), delay(bp(noise(0.08), 700, 2400) * env_exp(0.08, 0.02) * 0.4, 0.03))
    tw = [delay(mix(click(2800, 0.006), delay(click(1400, 0.008, 0.6), 0.01)), i * 0.062) for i in range(4)]
    C["typewriter_01"] = mix(*tw)
    C["typewriter_02"] = mix(click(2900, 0.006), delay(tone(0.04, 260, 240) * env_exp(0.04, 0.012) * 0.5, 0.006))
    sp = [delay(fm_bell(0.5, float(RNG.uniform(3200, 8800)), [(1, 1)], 0.1) * 0.5, i * 0.045) for i in range(8)]
    C["sparkle_01"] = mix(*sp)
    C["sparkle_02"] = mix(sweep_bp(noise(0.8), 2500, 9000, 0.8) * env_arc(0.8, 0.3) * 0.7, *sp[:4])
    C["zap_01"] = soft(mix(tone(0.18, 2400, 280, "saw"), bp(noise(0.18), 800, 5000) * 0.4) * env_exp(0.18, 0.05), 2.2)
    C["zap_02"] = tone(0.12, 4200, 160) * env_exp(0.12, 0.03)
    C["thud_01"] = boom(130, 90, 0.24, punch=0.4, drive=1.2)
    C["thud_02"] = boom(75, 48, 0.45, drive=1.4)
    C["camera_01"] = mix(click(3200, 0.006), delay(bp(noise(0.07), 900, 2200) * env_exp(0.07, 0.03) * 0.35, 0.012),
                         delay(click(2600, 0.007, 0.8), 0.085))
    C["cash_01"] = mix(fm_bell(0.5, 1976, [(1, 1), (2.4, 0.4)], 0.18), delay(jingle(7, 0.45), 0.06))
    al = tone(0.09, 880, 880, "square") * env_exp(0.09, 0.05)
    C["alarm_01"] = mix(al, delay(al, 0.13), delay(al, 0.26)) * 0.7
    hb = boom(62, 50, 0.22, drive=1.3)
    C["heartbeat_01"] = mix(hb, delay(hb * 0.8, 0.32))
    return C


if __name__ == "__main__":
    index = json.loads((OUT / "index.json").read_text())
    built = build_all()
    missing = set(index["cues"]) - set(built)
    extra = set(built) - set(index["cues"])
    assert not missing and not extra, f"cue list drift: missing={missing} extra={extra}"
    for name, data in built.items():
        data = normalize(np.asarray(data, dtype=np.float64))
        # 24ms fade-out tail so nothing clicks on cut
        n_fade = int(0.024 * SR)
        if len(data) > n_fade:
            data[-n_fade:] *= np.linspace(1, 0, n_fade)
        sf.write(OUT / index["cues"][name]["file"], data.astype(np.float32), SR, subtype="PCM_16")
    durs = {n: round(len(d) / SR, 2) for n, d in built.items()}
    print(f"built {len(built)} cues, durations {min(durs.values())}–{max(durs.values())}s")
