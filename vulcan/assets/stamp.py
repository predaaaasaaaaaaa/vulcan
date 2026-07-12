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


def keep_largest_component(img: Image.Image, min_solidity: float = 0.75) -> Image.Image:
    """Kill fragmented cutouts (lightning bolts, crumbs, floating text).

    Keeps the largest connected alpha component; raises if even that component
    holds < min_solidity of the alpha mass (the cutout is inherently shredded).
    Learned from the Eiffel-lightning failure in the Phase 3 eye check.
    """
    from scipy import ndimage

    alpha = np.asarray(img.split()[-1])
    mask = alpha > 20
    if not mask.any():
        raise ValueError("empty alpha")
    labels, n = ndimage.label(mask)
    if n <= 1:
        return img
    sizes = ndimage.sum_labels(mask, labels, index=range(1, n + 1))
    largest = int(np.argmax(sizes)) + 1
    solidity = float(sizes.max() / mask.sum())
    if solidity < min_solidity:
        raise ValueError(f"cutout too fragmented ({n} pieces, largest holds {solidity:.0%})")
    keep = labels == largest
    out = np.array(img)
    out[..., 3] = np.where(keep, out[..., 3], 0)
    return Image.fromarray(out)


def mean_luma(img: Image.Image) -> float:
    """Mean luminance (0..1) of opaque pixels — dark logos vanish on our bg."""
    arr = np.asarray(img.convert("RGBA"), dtype=np.float32)
    a = arr[..., 3] > 128
    if not a.any():
        return 0.0
    rgb = arr[..., :3][a] / 255.0
    return float((0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]).mean())


def add_stroke_and_shadow(img: Image.Image, stroke_px: int = STROKE_PX,
                          stroke_color=(255, 255, 255, 255)) -> Image.Image:
    """White sticker stroke via alpha dilation + soft drop shadow underneath."""
    margin = stroke_px + SHADOW_BLUR + abs(SHADOW_OFFSET[1]) + 8
    canvas_size = (img.width + margin * 2, img.height + margin * 2)

    base = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    base.paste(img, (margin, margin), img)
    alpha = base.split()[-1]

    # stroke = alpha dilated by MaxFilter (odd kernel ≥3), filled white.
    # stroke_px=0 (icons/emoji) skips dilation — MaxFilter(1) crashes PIL's C layer.
    if stroke_px > 0:
        kernel = min(stroke_px * 2 + 1, 31)  # PIL MaxFilter caps out; 31 ≈ 15px stroke
        dilated = alpha.filter(ImageFilter.MaxFilter(kernel))
    else:
        dilated = alpha
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


# Smooth-shaded art (3D icons, emoji, flat vectors) upscales cleanly with
# Lanczos; photos don't. Floors reflect that (fluent 3D emoji ship at 256px —
# best account-free source found, see BUILDLOG Phase 3).
MIN_EDGE_BY_KIND = {
    "photo_cutout": 500,
    "screenshot": 500,
    "3d_icon": 250,
    "emoji": 250,
    "flat_icon": 250,
    "logo": 250,
}
SMOOTH_KINDS = {"3d_icon", "emoji", "flat_icon", "logo"}


def stamp(raw_bytes: bytes, out_path: str | Path, kind: str = "photo_cutout",
          min_edge: int | None = None) -> dict:
    """bytes → stamped PNG on disk. Returns {width,height,coverage}. Raises on junk.

    kind controls treatment: photo_cutout gets rembg+stroke; icons/emoji keep
    their native alpha and get NO stroke (they're already designed objects) but
    do get the soft shadow for depth; screenshots stay rectangular (framed by
    the renderer) and are only size-checked.
    """
    if min_edge is None:
        min_edge = MIN_EDGE_BY_KIND.get(kind, MIN_SOURCE_EDGE)
    img = Image.open(io.BytesIO(raw_bytes))
    img = img.convert("RGBA")
    if max(img.size) < min_edge:
        raise ValueError(f"source too small: {img.size} (need ≥{min_edge}px long edge)")
    if kind in SMOOTH_KINDS and max(img.size) < 512:
        f = 512 / max(img.size)
        img = img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)

    if kind == "screenshot":
        img.thumbnail((1400, 1400), Image.LANCZOS)
        img.save(out_path, "PNG")
        return {"width": img.width, "height": img.height, "coverage": 1.0}

    if kind == "photo_cutout":
        if not has_real_alpha(img):
            img = remove_background(img)
        img = keep_largest_component(img)
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
    """SVG → PNG bytes, in a SUBPROCESS — cairosvg can segfault on hostile SVGs
    and must never take the engine down with it (learned the hard way, Phase 3)."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-c", (
            "import sys, cairosvg;"
            f"sys.stdout.buffer.write(cairosvg.svg2png(bytestring=sys.stdin.buffer.read(), output_width={size}, output_height={size}))"
        )],
        input=svg_bytes, capture_output=True, timeout=30,
    )
    if proc.returncode != 0:
        raise ValueError(f"svg rasterization failed (rc={proc.returncode}): {proc.stderr[-200:]!r}")
    if not proc.stdout:
        raise ValueError("svg rasterization produced no output")
    return proc.stdout
