"""cache/media.db — every validated asset ever fetched, with its embedding.

Recurring topics compound: before any network fetch the engine asks the cache
for a semantically similar prior asset (SigLIP text↔image space).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import numpy as np

from ..paths import CACHE_DIR

DB_PATH = CACHE_DIR / "media.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    query TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    score REAL,
    embedding TEXT,            -- JSON list, SigLIP image embedding (unit norm)
    width INTEGER,
    height INTEGER,
    uses INTEGER DEFAULT 0,
    created_at REAL,
    UNIQUE(path)
);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(asset_type);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def add(query: str, asset_type: str, source: str, path: str | Path,
        score: float | None, embedding: np.ndarray | None,
        width: int, height: int) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO media (query, asset_type, source, path, score, embedding, width, height, uses, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,COALESCE((SELECT uses FROM media WHERE path=?),0),?)",
            (
                query, asset_type, source, str(path), score,
                json.dumps(embedding.tolist()) if embedding is not None else None,
                width, height, str(path), time.time(),
            ),
        )


def migrate_run_assets(run_assets_dir: Path, shared_dir: Path) -> int:
    """Move media.db-referenced assets out of a run dir into the shared store
    (cache/assets/) and update their DB paths — run cleanup must not cost the
    cross-run cache its files. Returns number migrated."""
    import shutil

    shared_dir.mkdir(parents=True, exist_ok=True)
    run_assets_dir = run_assets_dir.resolve()
    moved = 0
    with _conn() as c:
        rows = c.execute("SELECT id, path FROM media").fetchall()
        for row_id, path in rows:
            p = Path(path)
            try:
                inside = p.resolve().parent == run_assets_dir
            except OSError:
                continue
            if not inside or not p.exists():
                continue
            dest = shared_dir / p.name
            if dest.exists():
                dest = shared_dir / f"{p.stem}_{row_id}{p.suffix}"
            shutil.move(str(p), dest)
            c.execute("UPDATE media SET path = ? WHERE id = ?", (str(dest), row_id))
            moved += 1
    return moved


def find_similar(text_embedding: np.ndarray, asset_type: str, threshold: float) -> dict | None:
    """Best cached asset of this type whose image embedding ⋅ text embedding ≥ threshold."""
    with _conn() as c:
        rows = c.execute(
            "SELECT path, score, embedding, width, height FROM media"
            " WHERE asset_type = ? AND embedding IS NOT NULL",
            (asset_type,),
        ).fetchall()
    best, best_sim = None, threshold
    for path, score, emb_json, w, h in rows:
        if not Path(path).exists():
            continue
        emb = np.asarray(json.loads(emb_json), dtype=np.float32)
        sim = float(np.dot(emb, text_embedding))
        if sim >= best_sim:
            best_sim = sim
            best = {"path": path, "score": score, "sim": sim, "width": w, "height": h}
    if best is not None:
        with _conn() as c:
            c.execute("UPDATE media SET uses = uses + 1 WHERE path = ?", (best["path"],))
    return best
