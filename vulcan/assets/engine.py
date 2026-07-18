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

# Stage-4 runaway guards (post-mortem 2026-07-12: one asset burned 34 attempts
# and 16 minutes on a rate-limited network before anyone gave up):
MAX_ATTEMPTS_PER_ASSET = 10      # candidates actually downloaded/stamped/scored
PER_ASSET_BUDGET_S = 75          # wall-clock cap per asset
NETWORK_TRIP_THRESHOLD = 6       # consecutive network errors across the stage → degraded

_NETWORK_ERRORS = (httpx.TimeoutException, httpx.TransportError, httpx.ConnectError)


class _Breaker:
    """Stage-wide circuit breaker: when the network is clearly degraded, stop
    burning minutes — remaining assets fail fast and their beats degrade to
    kinetic_type (the render must ship)."""

    def __init__(self) -> None:
        self.consecutive = 0
        self.tripped = False

    def record(self, ok: bool) -> None:
        self.consecutive = 0 if ok else self.consecutive + 1
        if self.consecutive >= NETWORK_TRIP_THRESHOLD and not self.tripped:
            self.tripped = True
            log.warning("network circuit breaker TRIPPED after %d consecutive failures — "
                        "remaining assets fail fast", self.consecutive)


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


def resolve_asset(asset: dict, out_dir: str | Path, threshold: float | None = None,
                  breaker: "_Breaker | None" = None) -> dict:
    """Fetch/validate one manifest asset in place. Returns the mutated dict.

    Sets status=validated + path + score on success; status=failed on
    exhaustion (failure trail in the log; the CLI then degrades its beats,
    build_golden refuses). Bounded by
    MAX_ATTEMPTS_PER_ASSET, PER_ASSET_BUDGET_S and the stage circuit breaker.
    """
    if threshold is None:
        threshold = config.get("assets.siglip_threshold") or 0.06
    breaker = breaker or _Breaker()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    attempts = 0
    started = time.monotonic()

    def budget_left() -> bool:
        if breaker.tripped:
            failures.append("network degraded — circuit breaker tripped")
            return False
        if attempts >= MAX_ATTEMPTS_PER_ASSET:
            failures.append(f"attempt cap reached ({MAX_ATTEMPTS_PER_ASSET})")
            return False
        if time.monotonic() - started > PER_ASSET_BUDGET_S:
            failures.append(f"time budget exceeded ({PER_ASSET_BUDGET_S}s)")
            return False
        return True

    from .scorer import relevance, text_embedding

    for query in asset["queries"]:
        if not budget_left():
            break
        phrase = _score_phrase(asset, query)

        # 1) cache first — recurring topics compound. Screenshots/logos are
        # entity-specific: a loose match reused a Stripe homepage for a "GPT"
        # beat (2026-07-14) — they need a much stronger similarity to reuse.
        cache_floor = threshold + 0.02
        if asset["type"] in ("screenshot", "logo"):
            cache_floor = max(cache_floor, 0.12)
        try:
            cached = media_cache.find_similar(text_embedding(phrase), asset["type"], cache_floor)
            if cached:
                asset.update(path=cached["path"], status="validated",
                             score=round(cached["sim"], 4))
                log.info("cache hit for %r → %s (sim %.3f)", query, cached["path"], cached["sim"])
                return asset
        except Exception as e:
            failures.append(f"cache lookup failed: {e}")

        # 2) source waterfall
        for cand in candidates_for(asset["type"], query):
            if not budget_left():
                break
            attempts += 1
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
                breaker.record(ok=True)
                return asset
            except _NETWORK_ERRORS as e:
                failures.append(f"{cand.source} {cand.url[:80]}: NETWORK {type(e).__name__}")
                out_path.unlink(missing_ok=True)
                breaker.record(ok=False)
                continue
            except Exception as e:
                failures.append(f"{cand.source} {cand.url[:80]}: {e}")
                out_path.unlink(missing_ok=True)
                breaker.record(ok=True)  # content rejection, not network trouble
                continue
        time.sleep(0.4)  # be polite between query variants

    asset["status"] = "failed"
    # forensics go to the log, never onto the dict: manifest assets are
    # schema-validated with additionalProperties:false, and a stray key here
    # buries the real render-gate error under E_SCHEMA noise
    log.warning("asset %s FAILED after %d attempts; failures: %s",
                asset["asset_id"], attempts,
                "; ".join(failures[-12:]) if failures else "no candidates")
    return asset


def resolve_all(manifest: dict, out_dir: str | Path) -> tuple[dict, list[str]]:
    """Resolve every asset with a shared circuit breaker. Returns
    (manifest, failed asset_ids). Worst case is bounded: assets × 75s, and a
    degraded network trips the breaker long before that."""
    failed = []
    breaker = _Breaker()
    for asset in manifest["assets"]:
        if asset["status"] == "validated" and asset.get("path") and Path(asset["path"]).exists():
            continue
        resolve_asset(asset, out_dir, breaker=breaker)
        if asset["status"] != "validated":
            failed.append(asset["asset_id"])
    return manifest, failed
