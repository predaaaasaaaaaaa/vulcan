"""Stage 5 — render: pure function (manifest.json, assets/) → raw.mp4.

Invokes Remotion headless. No LLM anywhere near this file. Asset/audio paths
are rewritten to be staticFile()-relative (public/runs symlinks the runs dir),
so the composition never sees absolute paths.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config
from .paths import REMOTION_DIR, ROOT, SFX_INDEX


class RenderError(RuntimeError):
    pass


def _local_browser() -> str | None:
    import glob
    hits = sorted(glob.glob(str(
        Path.home() / ".cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell"
    )))
    return hits[-1] if hits else None


def _to_static_key(path: str | Path) -> str:
    """Absolute path under ~/vulcan → key servable by public/ symlinks."""
    p = Path(path).resolve()
    try:
        rel = p.relative_to(ROOT)
    except ValueError as e:
        raise RenderError(f"asset outside repo cannot be served: {p}") from e
    if rel.parts[0] not in ("runs", "sfx"):
        raise RenderError(f"asset must live under runs/ or sfx/: {p}")
    return str(rel)


def prepare_props(manifest: dict, run_dir: Path) -> Path:
    """Write the inputProps file: manifest with rewritten paths + style + sfx index."""
    m = json.loads(json.dumps(manifest))  # deep copy
    m["audio"]["path"] = _to_static_key(run_dir / "audio" / "mastered.wav")
    for a in m["assets"]:
        if a.get("path"):
            a["path"] = _to_static_key(a["path"])
    sfx_index = json.loads(SFX_INDEX.read_text())["cues"]
    props = {
        "manifest": m,
        "style": {"accent": config.get("style.accent_color", "#FFCC00")},
        "sfxIndex": sfx_index,
    }
    props_path = run_dir / "props.json"
    props_path.write_text(json.dumps(props))
    return props_path


def render(manifest: dict, run_dir: str | Path, out_name: str = "raw.mp4") -> Path:
    run_dir = Path(run_dir)
    props_path = prepare_props(manifest, run_dir)
    out_path = run_dir / "out" / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)

    concurrency = config.get("render.concurrency") or 4
    crf = config.get("render.crf", 23)
    timeout_min = config.get("render.timeout_min", 30)

    cmd = [
        "npx", "remotion", "render", "Master",
        "--props", str(props_path.resolve()),
        "--output", str(out_path.resolve()),
        "--codec", "h264",
        "--crf", str(crf),
        "--concurrency", str(concurrency),
        "--log", "error",
    ]
    # remotion.media (browser mirror + version check) is unreachable on this
    # network — Remotion crashes on an uncaught fetch rejection. Point it at
    # the puppeteer-cached chrome-headless-shell instead (see BUILDLOG Phase 4).
    browser = _local_browser()
    if browser:
        cmd += ["--browser-executable", browser]
    proc = subprocess.run(
        cmd, cwd=REMOTION_DIR, capture_output=True, text=True,
        timeout=timeout_min * 60,
    )
    log_path = run_dir / "out" / "render.log"
    log_path.write_text(proc.stdout[-20000:] + "\n---STDERR---\n" + proc.stderr[-20000:])
    if proc.returncode != 0:
        raise RenderError(f"remotion render failed (rc={proc.returncode}); tail: {proc.stderr[-600:]}")
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RenderError("render produced no output file")
    return out_path
