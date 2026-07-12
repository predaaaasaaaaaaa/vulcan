"""House-style stamping — every raster asset leaves here looking like it belongs
to the same show: cut out, autocropped, white sticker stroke, soft drop shadow.

Pipeline: ensure alpha (rembg isnet-general-use when opaque) → autocrop →
stroke+shadow stamp → resize → PNG.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

log = logging.getLogger("vulcan.assets")

MIN_SOURCE_EDGE = 500          # reject smaller sources (config assets.min_edge_px)
TARGET_LONG_EDGE = 1000        # display raster size
STROKE_PX = 12                 # white sticker stroke at target size
SHADOW_BLUR = 18
SHADOW_OFFSET = (0, 14)
SHADOW_ALPHA = 110

_REMBG_SESSION = None


def _rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session
        _REMBG_SESSION = new_session("isnet-general-use")
    return _REMBG_SESSION


def has_real_alpha(img: Image.Image) -> bool:
    """True when the alpha channel actually cuts something out (not a solid rect)."""
    if img.mode != "RGBA":
        return False
    alpha = np.asarray(img.split()[-1])
    return bool((alpha < 200).mean() > 0.02)


def remove_background(img: Image.Image) -> Image.Image:
    from rembg import remove
    return remove(img, session=_rembg_session()).convert("RGBA")


def autocrop(img: Image.Image, pad: int = 8) -> Image.Image:
    alpha = np.asarray(img.split()[-1])
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        raise ValueError("image is fully transparent after cutout")
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, img.width - 1)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, img.height - 1)
    return img.crop((x0, y0, x1 + 1, y1 + 1))


def coverage(img: Image.Image) -> float:
    """Fraction of pixels that are opaque-ish — sanity for broken cutouts."""
    alpha = np.asarray(img.split()[-1])
    return float((alpha > 128).mean())


def add_stroke_and_shadow(img: Image.Image, stroke_px: int = STROKE_PX,
                          stroke_color=(255, 255, 255, 255)) -> Image.Image:
    """White sticker stroke via alpha dilation + soft drop shadow underneath."""
    margin = stroke_px + SHADOW_BLUR + abs(SHADOW_OFFSET[1]) + 8
    canvas_size = (img.width + margin * 2, img.height + margin * 2)

    base = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    base.paste(img, (margin, margin), img)
    alpha = base.split()[-1]

    # stroke = alpha dilated by MaxFilter (odd kernel), filled white
    kernel = stroke_px * 2 + 1
    dilated = alpha.filter(ImageFilter.MaxFilter(kernel))
    stroke_layer = Image.new("RGBA", canvas_size, stroke_color)
    stroke_layer.putalpha(dilated)

    # shadow = stroke silhouette blurred, offset, dark
    shadow_mask = dilated.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 255))
    shadow_layer.putalpha(shadow_mask.point(lambda a: a * SHADOW_ALPHA // 255))

    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    out.paste(shadow_layer, SHADOW_OFFSET, shadow_layer)
    out.alpha_composite(stroke_layer)
    out.alpha_composite(base)
    return autocrop(out, pad=4)


def stamp(raw_bytes: bytes, out_path: str | Path, kind: str = "photo_cutout",
          min_edge: int = MIN_SOURCE_EDGE) -> dict:
    """bytes → stamped PNG on disk. Returns {width,height,coverage}. Raises on junk.

    kind controls treatment: photo_cutout gets rembg+stroke; icons/emoji keep
    their native alpha and get NO stroke (they're already designed objects) but
    do get the soft shadow for depth; screenshots stay rectangular (framed by
    the renderer) and are only size-checked.
    """
    img = Image.open(io.BytesIO(raw_bytes))
    img = img.convert("RGBA")
    if max(img.size) < min_edge:
        raise ValueError(f"source too small: {img.size} (need ≥{min_edge}px long edge)")

    if kind == "screenshot":
        img.thumbnail((1400, 1400), Image.LANCZOS)
        img.save(out_path, "PNG")
        return {"width": img.width, "height": img.height, "coverage": 1.0}

    if kind == "photo_cutout":
        if not has_real_alpha(img):
            img = remove_background(img)
        img = autocrop(img)
        cov = coverage(img)
        if cov < 0.08:
            raise ValueError(f"cutout nearly empty (coverage {cov:.3f})")
        if cov > 0.98:
            raise ValueError("cutout failed — alpha is a solid rectangle")
        img = add_stroke_and_shadow(img)
    else:  # 3d_icon, flat_icon, logo, emoji — native alpha, shadow only
        if not has_real_alpha(img):
            # e.g. a logo served as JPEG — cut it out, but keep no stroke
            img = remove_background(img)
        img = autocrop(img)
        cov = coverage(img)
        if cov < 0.04:
            raise ValueError(f"icon nearly empty (coverage {cov:.3f})")
        img = add_stroke_and_shadow(img, stroke_px=0)

    if max(img.size) > TARGET_LONG_EDGE:
        img.thumbnail((TARGET_LONG_EDGE, TARGET_LONG_EDGE), Image.LANCZOS)
    img.save(out_path, "PNG")
    return {"width": img.width, "height": img.height, "coverage": coverage(img)}


def rasterize_svg(svg_bytes: bytes, size: int = 1024) -> bytes:
    """SVG → PNG bytes. Uses resvg/cairosvg if available, else Pillow can't — raise."""
    try:
        import cairosvg
        return cairosvg.svg2png(bytestring=svg_bytes, output_width=size, output_height=size)
    except ImportError as e:
        raise RuntimeError("cairosvg not installed — needed for iconify SVGs") from e
