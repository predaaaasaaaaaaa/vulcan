"""Asset source waterfall — each source returns candidate URLs, engine.py fetches,
stamps, scores and caches. A dead source logs and yields nothing; it never raises
past its boundary (the waterfall just moves on).

Source map (RECON §4 + Phase 3 probes):
  photo_cutout : wikimedia → ddg images (transparent first, then any photo → rembg)
  3d_icon      : fluent-emoji 3D (reliable, MIT) → 3dicons.co (probed at build)
  flat_icon    : iconify search API
  logo         : iconify 'logos' + 'simple-icons' sets
  emoji        : fluent-emoji 3D by unicode name (hi-res PNG)
  screenshot   : ddg images
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("vulcan.assets")

UA = "VulcanForge/0.1 (personal automation; contact: local)"
TIMEOUT = httpx.Timeout(20.0, connect=8.0)


@dataclass
class Candidate:
    url: str
    source: str
    width: int = 0
    height: int = 0
    likely_alpha: bool = False
    extra: dict = field(default_factory=dict)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True)


# ---------------------------------------------------------------- wikimedia

def wikimedia(query: str, max_results: int = 6) -> list[Candidate]:
    try:
        with _client() as c:
            r = c.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query", "format": "json",
                    "generator": "search",
                    "gsrsearch": f"filetype:bitmap {query}",
                    "gsrnamespace": 6, "gsrlimit": max_results,
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime",
                    "iiurlwidth": 1400,
                },
            )
            r.raise_for_status()
            pages = (r.json().get("query") or {}).get("pages", {})
        out = []
        for p in pages.values():
            for info in p.get("imageinfo", []):
                if info.get("mime") not in ("image/png", "image/jpeg"):
                    continue
                if min(info.get("width", 0), info.get("height", 0)) < 400:
                    continue
                out.append(Candidate(
                    url=info.get("thumburl") or info["url"],
                    source="wikimedia",
                    width=info.get("thumbwidth", info.get("width", 0)),
                    height=info.get("thumbheight", info.get("height", 0)),
                    likely_alpha=info.get("mime") == "image/png",
                ))
        return out
    except Exception as e:
        log.warning("wikimedia source failed for %r: %s", query, e)
        return []


# ---------------------------------------------------------------- duckduckgo

# stock-photo preview hosts watermark their images — a watermarked cutout
# fails the postable bar instantly (Phase 4 eye check: the VectorStock pearl)
STOCK_BLOCKLIST = (
    "vectorstock", "shutterstock", "alamy", "dreamstime", "istockphoto",
    "123rf", "depositphotos", "gettyimages", "bigstockphoto", "canstockphoto",
    "fotolia", "stockfresh", "colourbox", "agefotostock", "featurepics",
)


def ddg_images(query: str, transparent: bool = False, max_results: int = 8) -> list[Candidate]:
    try:
        from ddgs import DDGS
    except ImportError:  # older package name
        from duckduckgo_search import DDGS
    try:
        kwargs = {"safesearch": "moderate", "size": "Large", "max_results": max_results + 6}
        if transparent:
            kwargs["type_image"] = "transparent"
        with DDGS() as ddgs:
            results = list(ddgs.images(query, **kwargs))
        out = []
        for r in results:
            url = str(r.get("image", ""))
            if any(s in url.lower() for s in STOCK_BLOCKLIST):
                continue
            out.append(Candidate(
                url=url, source="ddg",
                width=int(r.get("width") or 0), height=int(r.get("height") or 0),
                likely_alpha=transparent or url.lower().endswith(".png"),
            ))
        return out[:max_results]
    except Exception as e:
        log.warning("ddg source failed for %r (transparent=%s): %s", query, transparent, e)
        return []


# ---------------------------------------------------------------- iconify

def iconify(query: str, sets: str | None = None, color: str | None = None,
            max_results: int = 8) -> list[Candidate]:
    """Iconify search → rasterizable SVG URLs (engine rasterizes at 1024px)."""
    try:
        params = {"query": query, "limit": max_results * 2}
        if sets:
            params["prefixes"] = sets
        with _client() as c:
            r = c.get("https://api.iconify.design/search", params=params)
            r.raise_for_status()
            icons = r.json().get("icons", [])
        out = []
        for icon in icons[:max_results]:
            prefix, _, name = icon.partition(":")
            url = f"https://api.iconify.design/{prefix}/{name}.svg?height=1024"
            if color:
                url += f"&color={color.replace('#', '%23')}"
            out.append(Candidate(url=url, source=f"iconify/{prefix}", width=1024, height=1024,
                                 likely_alpha=True, extra={"svg": True}))
        return out
    except Exception as e:
        log.warning("iconify source failed for %r: %s", query, e)
        return []


def logos(query: str, max_results: int = 6) -> list[Candidate]:
    return iconify(query, sets="logos,simple-icons", max_results=max_results)


# ---------------------------------------------------------------- fluent emoji (3D)

_FLUENT_RAW = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets"


def _fluent_slug(name: str) -> tuple[str, str]:
    """Fluent folders are sentence case: 'money bag' → ('Money bag', 'money_bag_3d.png')."""
    folder = name.strip().lower().capitalize()
    fname = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") + "_3d.png"
    return folder, fname


def fluent_emoji_by_char(emoji_char: str) -> list[Candidate]:
    """Resolve an emoji character to its fluent 3D PNG via its unicode name."""
    try:
        base = emoji_char[0]
        uname = unicodedata.name(base, "").lower()  # 'FIRE' → 'fire'
    except Exception:
        uname = ""
    if not uname:
        return []
    candidates = [uname]
    # unicode names vs fluent folder names differ in known ways
    cleaned = uname.replace("face with ", "").replace(" symbol", "").replace("heavy ", "")
    if cleaned != uname:
        candidates.append(cleaned)
    return [c for name in candidates for c in fluent_emoji_by_name(name)]


def fluent_emoji_by_name(name: str) -> list[Candidate]:
    folder, fname = _fluent_slug(name)
    return [Candidate(
        url=f"{_FLUENT_RAW}/{folder}/3D/{fname}".replace(" ", "%20"),
        source="fluent3d", width=1024, height=1024, likely_alpha=True,
    )]


# ---------------------------------------------------------------- waterfall

def candidates_for(asset_type: str, query: str) -> list[Candidate]:
    """Ordered candidate list for one query string."""
    if asset_type == "photo_cutout":
        return (ddg_images(query + " png", transparent=True, max_results=5)
                + wikimedia(query)
                + ddg_images(query, transparent=False, max_results=5))
    if asset_type == "3d_icon":
        return fluent_emoji_by_name(query) + iconify(query, max_results=4)
    if asset_type == "flat_icon":
        return iconify(query, color="#FFFFFF")
    if asset_type == "logo":
        return logos(query) + ddg_images(query + " logo transparent png", transparent=True, max_results=4)
    if asset_type == "emoji":
        return fluent_emoji_by_char(query) + fluent_emoji_by_name(query)
    if asset_type == "screenshot":
        return ddg_images(query + " website screenshot", max_results=6)
    if asset_type == "lottie":
        return []  # backed by the curated local pack — engine.py resolves it
    raise ValueError(f"unknown asset type {asset_type}")
