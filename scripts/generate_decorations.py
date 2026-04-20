"""
Procedural decoration generator for assets/decorations/consumer-friendly/.

Draws six botanical-style decorations using Pillow primitives on a transparent
canvas. Output is deterministic, reproducible, and MIT-licensed (generated
code, no external assets). Designed as a starter pack — swap in curated
watercolor PNGs later with no code changes as long as they land in the
same directory with the same file name pattern.

Run from repo root:
    python scripts/generate_decorations.py

Regenerates all PNGs in assets/decorations/consumer-friendly/ idempotently.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CANVAS_SIZE = 800
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "decorations" / "consumer-friendly"

# Natural botanical palette
LEAF_DARK = (74, 124, 89, 255)       # deep sage green
LEAF_MID = (107, 155, 107, 255)      # muted green
LEAF_LIGHT = (156, 191, 149, 255)    # pale green
STEM = (90, 115, 75, 255)            # woody stem
CITRUS_YELLOW = (244, 196, 48, 255)  # ripe lemon
CITRUS_ORANGE = (232, 155, 40, 255)  # warm citrus
FLOWER_PINK = (232, 140, 150, 255)   # soft rose
FLOWER_CENTER = (245, 220, 120, 255) # warm pollen


def _new_canvas() -> Image.Image:
    return Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))


def _soften(img: Image.Image) -> Image.Image:
    """Apply a mild blur for a hand-painted feel."""
    return img.filter(ImageFilter.GaussianBlur(radius=1.2))


def _leaf(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    length: int,
    width: int,
    angle_deg: float,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a rotated oval leaf at (cx, cy)."""
    layer = Image.new("RGBA", (length * 2, length * 2), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    lx = length - length // 2
    ly = length - width // 2
    ld.ellipse([lx, ly, lx + length, ly + width], fill=color)
    # Midrib for texture
    mid_color = (max(0, color[0] - 25), max(0, color[1] - 25), max(0, color[2] - 25), 200)
    ld.line([lx + 6, length, lx + length - 6, length], fill=mid_color, width=2)
    rotated = layer.rotate(angle_deg, resample=Image.BICUBIC, expand=False)
    rw, rh = rotated.size
    # Paste centered at (cx, cy)
    ox = cx - rw // 2
    oy = cy - rh // 2
    # Need access to parent image — use the draw's image
    draw._image.alpha_composite(rotated, (ox, oy))


def _patch_draw(draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
    """Attach the underlying image to draw so _leaf can composite onto it."""
    draw._image = img


# ---------------------------------------------------------------------------
# Decoration recipes
# ---------------------------------------------------------------------------

def botanical_sprig(seed: int) -> Image.Image:
    """Vertical stem with alternating leaves along its length."""
    rng = random.Random(seed)
    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    _patch_draw(draw, img)

    # Stem: slight curve via two line segments
    stem_top = (CANVAS_SIZE // 2 - 40, 90)
    stem_mid = (CANVAS_SIZE // 2 - 10, CANVAS_SIZE // 2)
    stem_bot = (CANVAS_SIZE // 2 + 20, CANVAS_SIZE - 120)
    draw.line([stem_top, stem_mid], fill=STEM, width=10)
    draw.line([stem_mid, stem_bot], fill=STEM, width=10)

    # Leaves at intervals along the stem
    n = 9
    for i in range(n):
        t = (i + 1) / (n + 1)
        if t < 0.5:
            x = stem_top[0] + (stem_mid[0] - stem_top[0]) * (t * 2)
            y = stem_top[1] + (stem_mid[1] - stem_top[1]) * (t * 2)
        else:
            tt = (t - 0.5) * 2
            x = stem_mid[0] + (stem_bot[0] - stem_mid[0]) * tt
            y = stem_mid[1] + (stem_bot[1] - stem_mid[1]) * tt

        side = 1 if i % 2 == 0 else -1
        length = rng.randint(150, 190)
        width = int(length * 0.4)
        angle = 30 + rng.uniform(-15, 15)
        color = LEAF_MID if i % 2 == 0 else LEAF_DARK
        _leaf(draw, int(x) + side * 60, int(y), length, width, angle * side, color)

    return _soften(img)


def citrus_cluster(seed: int) -> Image.Image:
    """Three citrus fruits with surrounding leaves — Lemon Health style."""
    rng = random.Random(seed)
    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    _patch_draw(draw, img)

    # Three citrus circles
    positions = [
        (CANVAS_SIZE // 2 - 140, 320, 150),  # x, y, radius
        (CANVAS_SIZE // 2 + 80, 280, 170),
        (CANVAS_SIZE // 2 - 20, 490, 155),
    ]
    for i, (x, y, r) in enumerate(positions):
        color = CITRUS_YELLOW if i != 1 else CITRUS_ORANGE
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
        # Pith highlight
        highlight = (
            min(255, color[0] + 20),
            min(255, color[1] + 25),
            min(255, color[2] + 40),
            180,
        )
        draw.ellipse(
            [x - r + r // 3, y - r + r // 3, x - r + r // 2 + 20, y - r + r // 2 + 10],
            fill=highlight,
        )

    # Leaves tucked between fruits
    leaf_spots = [
        (CANVAS_SIZE // 2 - 250, 200, 200, 85, -30),
        (CANVAS_SIZE // 2 + 220, 180, 220, 90, 40),
        (CANVAS_SIZE // 2 + 180, 480, 180, 75, -20),
        (CANVAS_SIZE // 2 - 210, 560, 180, 80, 30),
    ]
    for spot in leaf_spots:
        x, y, length, width, angle = spot
        color = LEAF_DARK if rng.random() > 0.5 else LEAF_MID
        _leaf(draw, x, y, length, width, angle, color)

    return _soften(img)


def leaf_arc(seed: int) -> Image.Image:
    """A horizontal arc of leaves — top-edge decoration."""
    rng = random.Random(seed)
    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    _patch_draw(draw, img)

    # Leaves spread along an arc
    n = 11
    arc_cx, arc_cy = CANVAS_SIZE // 2, 180
    arc_r = 320
    for i in range(n):
        t = i / (n - 1)
        theta = math.pi + t * math.pi  # from π to 2π (upper arc)
        x = int(arc_cx + arc_r * math.cos(theta))
        y = int(arc_cy + arc_r * math.sin(theta) * 0.35)
        length = rng.randint(140, 180)
        width = int(length * 0.42)
        angle = math.degrees(theta) + 90 + rng.uniform(-20, 20)
        color = LEAF_DARK if i % 3 == 0 else LEAF_MID if i % 3 == 1 else LEAF_LIGHT
        _leaf(draw, x, y + 100, length, width, angle, color)

    return _soften(img)


def herb_sprig(seed: int) -> Image.Image:
    """Symmetric thin herb with small paired leaves."""
    rng = random.Random(seed)
    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    _patch_draw(draw, img)

    # Central stem
    stem_x = CANVAS_SIZE // 2
    draw.line([(stem_x, 120), (stem_x, CANVAS_SIZE - 120)], fill=STEM, width=6)

    n_pairs = 8
    for i in range(n_pairs):
        y = 150 + i * 65
        length = 100 + rng.randint(-10, 20)
        width = int(length * 0.35)
        _leaf(draw, stem_x - 55, y, length, width, -45 + rng.uniform(-8, 8), LEAF_MID)
        _leaf(draw, stem_x + 55, y, length, width, 45 + rng.uniform(-8, 8), LEAF_MID)

    return _soften(img)


def floral_dots(seed: int) -> Image.Image:
    """Cluster of abstract 6-petal flowers with leafy backing."""
    rng = random.Random(seed)
    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    _patch_draw(draw, img)

    # Backing leaves
    for _ in range(6):
        x = rng.randint(150, CANVAS_SIZE - 150)
        y = rng.randint(150, CANVAS_SIZE - 150)
        _leaf(draw, x, y, rng.randint(160, 210), 70, rng.uniform(-60, 60), LEAF_DARK)

    # Flowers on top
    flower_spots = [
        (CANVAS_SIZE // 2 - 140, 280, 90),
        (CANVAS_SIZE // 2 + 100, 330, 100),
        (CANVAS_SIZE // 2 - 30, 500, 85),
    ]
    for fx, fy, fr in flower_spots:
        for k in range(6):
            theta = k * math.pi / 3
            px = fx + int(fr * 0.75 * math.cos(theta))
            py = fy + int(fr * 0.75 * math.sin(theta))
            draw.ellipse([px - fr // 2, py - fr // 2, px + fr // 2, py + fr // 2], fill=FLOWER_PINK)
        draw.ellipse([fx - fr // 3, fy - fr // 3, fx + fr // 3, fy + fr // 3], fill=FLOWER_CENTER)

    return _soften(img)


def mixed_bunch(seed: int) -> Image.Image:
    """Generic mixed cluster — leaves, a citrus, a flower."""
    rng = random.Random(seed)
    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    _patch_draw(draw, img)

    # Several oriented leaves
    leaf_specs = [
        (260, 260, 200, 80, -30, LEAF_DARK),
        (540, 240, 210, 85, 45, LEAF_MID),
        (380, 340, 190, 75, 10, LEAF_LIGHT),
        (300, 530, 170, 70, 55, LEAF_MID),
        (520, 520, 180, 75, -50, LEAF_DARK),
    ]
    for spec in leaf_specs:
        _leaf(draw, *spec)

    # One citrus
    cx, cy, r = CANVAS_SIZE // 2, 420, 130
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CITRUS_YELLOW)
    draw.ellipse([cx - r + 30, cy - r + 25, cx - r + 90, cy - r + 75], fill=(255, 235, 140, 180))

    # One flower
    fx, fy, fr = CANVAS_SIZE // 2 + 160, 300, 70
    for k in range(6):
        theta = k * math.pi / 3
        px = fx + int(fr * 0.75 * math.cos(theta))
        py = fy + int(fr * 0.75 * math.sin(theta))
        draw.ellipse([px - fr // 2, py - fr // 2, px + fr // 2, py + fr // 2], fill=FLOWER_PINK)
    draw.ellipse([fx - fr // 3, fy - fr // 3, fx + fr // 3, fy + fr // 3], fill=FLOWER_CENTER)

    return _soften(img)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

RECIPES = [
    ("botanical_sprig_01.png", botanical_sprig, 1),
    ("citrus_cluster_02.png", citrus_cluster, 2),
    ("leaf_arc_03.png", leaf_arc, 3),
    ("herb_sprig_04.png", herb_sprig, 4),
    ("floral_dots_05.png", floral_dots, 5),
    ("mixed_bunch_06.png", mixed_bunch, 6),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn, seed in RECIPES:
        img = fn(seed)
        path = OUT_DIR / name
        img.save(path, format="PNG")
        print(f"  wrote {path.relative_to(OUT_DIR.parent.parent.parent)}")
    print(f"\n{len(RECIPES)} decorations written to {OUT_DIR}")


if __name__ == "__main__":
    main()
