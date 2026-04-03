"""
Heuristic raster logo cleanup (Pillow only) — optional dark-plate background removal.

Gated by LOGO_BG_REMOVAL_ENABLED. Safe no-op when corners look light or image unchanged.

Treats uniform dark corners as plate color: near-black, charcoal gray, and dark navy
apple-touch-style tiles (not only #000).
"""

from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

# Skip when average corner luma is above this (corners too light → not a dark plate).
# 80 missed charcoal tiles (~#525252, luma ~82). 102 keeps medium UI grays safe.
_CORNER_LUMA_SKIP_ABOVE = 102

# Match plate: max abs delta per RGB channel (JPEG/fringe on gray/navy edges).
_COLOR_MATCH_THRESHOLD = 58

# Also match when squared Euclidean distance to corner-mean RGB is small (correlated
# noise on navy/blue-gray plates where all channels drift together slightly).
_COLOR_MATCH_DISTANCE_SQ = 5200


def maybe_remove_dark_background(png_bytes: bytes) -> bytes:
    """
    If PNG has uniformly dark corners (typical apple-touch-icon black plate),
    make matching pixels transparent. Otherwise return input unchanged.
    """
    if not png_bytes.startswith(b"\x89PNG"):
        return png_bytes
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception as exc:
        logger.debug("logo_postprocess: skip decode: %s", exc)
        return png_bytes

    w, h = img.size
    if w < 8 or h < 8:
        return png_bytes

    px = img.load()
    if px is None:
        return png_bytes

    def luma(p: tuple[int, ...]) -> float:
        r, g, b = p[0], p[1], p[2]
        return (r + g + b) / 3.0

    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    avg_luma = sum(luma(c) for c in corners) / 4.0
    if avg_luma > _CORNER_LUMA_SKIP_ABOVE:
        return png_bytes

    bg_r = sum(c[0] for c in corners) // 4
    bg_g = sum(c[1] for c in corners) // 4
    bg_b = sum(c[2] for c in corners) // 4

    def matches_plate(r: int, g: int, b: int) -> bool:
        dr = r - bg_r
        dg = g - bg_g
        db = b - bg_b
        if (
            abs(dr) <= _COLOR_MATCH_THRESHOLD
            and abs(dg) <= _COLOR_MATCH_THRESHOLD
            and abs(db) <= _COLOR_MATCH_THRESHOLD
        ):
            return True
        return dr * dr + dg * dg + db * db <= _COLOR_MATCH_DISTANCE_SQ

    changed = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if matches_plate(r, g, b):
                if a != 0:
                    px[x, y] = (r, g, b, 0)
                    changed = True

    if not changed:
        return png_bytes

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    new_bytes = out.getvalue()
    logger.info(
        "logo_postprocess: removed dark plate background (%sx%s, %s bytes -> %s)",
        w,
        h,
        len(png_bytes),
        len(new_bytes),
    )
    return new_bytes
