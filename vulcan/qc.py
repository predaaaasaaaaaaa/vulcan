"""Stage 6 — QC gates: deterministic checks on the rendered MP4.

Gates (config qc.*): duration delta vs audio, resolution/fps/codec, size cap,
frame sampling → luminance variance (dead-frame detector) + contact sheet,
program loudness. Fail → one auto-repair attempt upstream, then loud failure.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from . import config


class QCFailure(RuntimeError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def probe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def measure_program_lufs(path: Path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    start = proc.stderr.rfind("{")
    data = json.loads(proc.stderr[start:proc.stderr.rfind("}") + 1])
    return float(data["input_i"])


def extract_frames(mp4: Path, out_dir: Path, every_s: float) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(mp4),
         "-vf", f"fps=1/{every_s}", str(out_dir / "qc_%03d.png")],
        check=True,
    )
    return sorted(out_dir.glob("qc_*.png"))


def contact_sheet(frames: list[Path], out_path: Path, cols: int = 5, cell_w: int = 200) -> Path:
    if not frames:
        raise QCFailure(["no frames extracted"])
    thumbs = []
    for f in frames:
        img = Image.open(f)
        ratio = cell_w / img.width
        thumbs.append(img.resize((cell_w, int(img.height * ratio))))
    cell_h = thumbs[0].height
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (10, 10, 12))
    for i, tmb in enumerate(thumbs):
        sheet.paste(tmb, ((i % cols) * cell_w, (i // cols) * cell_h))
    sheet.save(out_path)
    return out_path


def run_qc(mp4: Path, manifest: dict, qc_dir: Path) -> dict:
    """Returns metrics dict; raises QCFailure listing every violated gate."""
    cfg = config.load()["qc"]
    problems: list[str] = []
    qc_dir.mkdir(parents=True, exist_ok=True)

    info = probe(mp4)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur_ms = round(float(info["format"]["duration"]) * 1000)
    size_mb = int(info["format"]["size"]) / 1e6

    want_ms = manifest["audio"]["duration_ms"]
    if abs(dur_ms - want_ms) > cfg["duration_delta_ms"]:
        problems.append(f"duration {dur_ms}ms vs audio {want_ms}ms (>±{cfg['duration_delta_ms']}ms)")
    if (v["width"], v["height"]) != (1080, 1920):
        problems.append(f"resolution {v['width']}x{v['height']} != 1080x1920")
    fps = eval(v["r_frame_rate"])  # e.g. "30/1"
    if abs(fps - 30) > 0.01:
        problems.append(f"fps {fps} != 30")
    if v["codec_name"] != "h264":
        problems.append(f"codec {v['codec_name']} != h264")
    if a is None:
        problems.append("no audio stream")
    if size_mb > cfg["max_size_mb"]:
        problems.append(f"size {size_mb:.1f}MB > {cfg['max_size_mb']}MB")

    frames = extract_frames(mp4, qc_dir / "frames", cfg["frame_sample_every_s"])
    dead = []
    for f in frames:
        arr = np.asarray(Image.open(f).convert("L"), dtype=np.float32)
        if arr.var() < cfg["min_luma_variance"]:
            dead.append(f.name)
    if dead:
        problems.append(f"dead frames (luma variance < {cfg['min_luma_variance']}): {dead[:5]}")
    sheet = contact_sheet(frames, qc_dir / "contact_sheet.png")

    lufs = measure_program_lufs(mp4)
    if abs(lufs - config.get("audio.target_lufs", -14.0)) > cfg["lufs_tolerance"]:
        problems.append(f"program loudness {lufs} LUFS outside -14±{cfg['lufs_tolerance']}")

    # Visual-richness gate (post-mortem 2026-07-14: a technically-perfect run
    # shipped 92s of captions on black). Measured on the FINAL manifest, i.e.
    # after asset failures degraded beats — the user-facing truth.
    from .validate import visual_coverage
    min_cov = cfg.get("min_visual_coverage", 0.20)
    cov = visual_coverage(manifest)
    if cov < min_cov:
        problems.append(
            f"visual coverage {cov:.0%} below floor {min_cov:.0%} — the video is "
            "text-only (assets failed or the Director under-planned); not shippable")

    metrics = {
        "duration_ms": dur_ms, "size_mb": round(size_mb, 2), "lufs": lufs,
        "frames_sampled": len(frames), "contact_sheet": str(sheet),
    }
    (qc_dir / "qc_report.json").write_text(json.dumps(
        {"metrics": metrics, "problems": problems}, indent=1))
    if problems:
        raise QCFailure(problems)
    return metrics
