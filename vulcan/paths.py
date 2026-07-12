"""Repo-root anchored paths so every stage resolves files identically."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA_PATH = ROOT / "schemas" / "manifest.schema.json"
CONFIG_PATH = ROOT / "config.yaml"
SFX_DIR = ROOT / "sfx"
SFX_INDEX = SFX_DIR / "index.json"
RUNS_DIR = ROOT / "runs"
CACHE_DIR = ROOT / "cache"
REMOTION_DIR = ROOT / "remotion"


def run_dir(video_id: str) -> Path:
    return RUNS_DIR / video_id
