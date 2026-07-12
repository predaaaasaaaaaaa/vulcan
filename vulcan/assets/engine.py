"""Asset engine — waterfall: cache → sources → download → stamp → score → cache.

SigLIP gating policy (deterministic):
  - photo_cutout / screenshot / 3d_icon-from-search: MUST clear the calibrated
    SigLIP threshold vs the query phrase (wrong-person/wrong-object risk).
  - iconify / fluent-emoji results: relevance is guaranteed by exact name search;
    gate is resolution + alpha sanity only. SigLIP embedding still computed and
    cached so the cross-run cache can match them semantically later.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import httpx

from .. import config
from . import cache as media_cache
from .sources import UA, Candidate, candidates_for
from .stamp import rasterize_svg, stamp

log = logging.getLogger("vulcan.assets")

DOWNLOAD_CAP_BYTES = 12 * 1024 * 1024
SEARCH_GATED_SOURCES = ("ddg", "wikimedia")  # SigLIP mandatory for these


def _download(url: str) -> bytes:
    with httpx.Client(headers={"User-Agent": UA}, timeout=httpx.Timeout(25.0, connect=8.0),
                      follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        if len(r.content) > DOWNLOAD_CAP_BYTES:
            raise ValueError(f"file too large ({len(r.content)} bytes)")
        return r.content


def _needs_siglip(candidate: Candidate) -> bool:
    return any(candidate.source.startswith(s) for s in SEARCH_GATED_SOURCES)


def _score_phrase(asset: dict, query: str) -> str:
    """Phrase scored against the image. For emoji, the char itself is meaningless."""
    if asset["type"] == "emoji":
        import unicodedata
        try:
            return unicodedata.name(query[0]).lower()
        except (ValueError, IndexError):
            return query
    return query


def resolve_asset(asset: dict, out_dir: str | Path, threshold: float | None = None) -> dict:
    """Fetch/validate one manifest asset in place. Returns the mutated dict.

    Sets status=validated + path + score on success; status=failed with
    _failure_log on exhaustion (Director Pass C can then swap the treatment).
    """
    if threshold is None:
        threshold = config.get("assets.siglip_threshold") or 0.06
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    from .scorer import relevance, text_embedding

    for query in asset["queries"]:
        phrase = _score_phrase(asset, query)

        # 1) cache first — recurring topics compound
        try:
            cached = media_cache.find_similar(text_embedding(phrase), asset["type"], threshold + 0.02)
            if cached:
                asset.update(path=cached["path"], status="validated",
                             score=round(cached["sim"], 4))
                log.info("cache hit for %r → %s (sim %.3f)", query, cached["path"], cached["sim"])
                return asset
        except Exception as e:
            failures.append(f"cache lookup failed: {e}")

        # 2) source waterfall
        for cand in candidates_for(asset["type"], query):
            tag = hashlib.sha1(cand.url.encode()).hexdigest()[:10]
            out_path = out_dir / f"{asset['asset_id']}_{tag}.png"
            try:
                raw = _download(cand.url)
                if cand.extra.get("svg"):
                    raw = rasterize_svg(raw, size=1024)
                info = stamp(raw, out_path, kind=asset["type"])

                # dark logos vanish on the near-black canvas — refetch mono
                # iconify sets in white; reject dark rasters outright
                if asset["type"] == "logo":
                    from .stamp import mean_luma
                    from PIL import Image as _Img
                    if mean_luma(_Img.open(out_path)) < 0.22:
                        if cand.extra.get("svg") and "color=" not in cand.url:
                            raw = _download(cand.url + "&color=%23FFFFFF")
                            raw = rasterize_svg(raw, size=1024)
                            info = stamp(raw, out_path, kind=asset["type"])
                            if mean_luma(_Img.open(out_path)) < 0.22:
                                raise ValueError("logo still too dark after white recolor")
                        else:
                            raise ValueError("logo too dark for near-black canvas")

                if _needs_siglip(cand):
                    score, img_emb = relevance(out_path, phrase)
                    if score < threshold:
                        failures.append(f"{cand.source} {cand.url[:80]} scored {score:.3f} < {threshold}")
                        out_path.unlink(missing_ok=True)
                        continue
                else:
                    score, img_emb = relevance(out_path, phrase)  # advisory + cache embedding

                asset.update(path=str(out_path), status="validated", score=round(score, 4))
                media_cache.add(query, asset["type"], cand.source, out_path, score,
                                img_emb, info["width"], info["height"])
                log.info("resolved %s %r via %s (score %.3f)", asset["asset_id"], query, cand.source, score)
                return asset
            except Exception as e:
                failures.append(f"{cand.source} {cand.url[:80]}: {e}")
                out_path.unlink(missing_ok=True)
                continue
        time.sleep(0.4)  # be polite between query variants

    asset["status"] = "failed"
    asset["_failure_log"] = failures[-12:]
    log.warning("asset %s FAILED after %d attempts", asset["asset_id"], len(failures))
    return asset


def resolve_all(manifest: dict, out_dir: str | Path) -> tuple[dict, list[str]]:
    """Resolve every asset. Returns (manifest, list of failed asset_ids)."""
    failed = []
    for asset in manifest["assets"]:
        if asset["status"] == "validated" and asset.get("path") and Path(asset["path"]).exists():
            continue
        resolve_asset(asset, out_dir)
        if asset["status"] != "validated":
            failed.append(asset["asset_id"])
    return manifest, failed
