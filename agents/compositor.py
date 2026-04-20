"""
Step 8.5: Compositor.

Assembles complete branded post images using Pillow — no external API needed.
Combines brand colors (from BrandIdentity), designed geometric layouts, extracted
logo, and formatted copy text into a PNG image ready for social media.

7 layout archetypes selected deterministically from design_category + run metadata.
Same run_id always produces the same image; different runs produce varied layouts.

Gating: only runs for visual content types (single_image, carousel, multi_image, story).
text_post, poll, question_post, thread, single_tweet return immediately.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from agents import asset_layer
from agents.image_gen import _is_dark, _pick_accent_color, _truncate, _split_into_slides
from config import settings
from schemas.brand_identity import BrandIdentity
from schemas.content_brief import ContentBrief
from schemas.formatted_content import FormattedContent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VISUAL_CONTENT_TYPES: frozenset[str] = frozenset({
    "single_image",
    "carousel",
    "multi_image",
    "story",
})

CANVAS_SIZES: dict[tuple[str, str], tuple[int, int]] = {
    ("linkedin",  "single_image"):  (1200, 627),
    ("linkedin",  "carousel"):      (1080, 1080),
    ("linkedin",  "multi_image"):   (1200, 627),
    ("instagram", "single_image"):  (1080, 1080),
    ("instagram", "carousel"):      (1080, 1080),
    ("instagram", "story"):         (1080, 1920),
}
_DEFAULT_CANVAS = (1080, 1080)

DESIGN_CATEGORY_LAYOUTS: dict[str, list[str]] = {
    "minimal-saas":      ["typographic",    "sidebar",        "frame"],
    "bold-enterprise":   ["bold_block",     "photo_overlay",  "split_field",      "photo_bottom_text"],
    "developer-tool":    ["hero_text",      "sidebar",        "typographic"],
    "consumer-friendly": ["cutout_hero",    "stat_hero",      "soft_card",        "editorial_photo"],
    "data-dense":        ["stat_hero",       "sidebar",        "typographic"],
}

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_FONT_FILES: dict[str, str] = {
    "heading_bold":    "SpaceGrotesk-Bold.ttf",
    "heading_reg":     "SpaceGrotesk-Regular.ttf",
    "body_reg":        "Inter-Regular.ttf",
    "body_bold":       "Inter-Bold.ttf",             # heavier body weight
    "display_bold":    "PlayfairDisplay-Bold.ttf",   # display serif for editorial/typographic layouts
    "display_italic":  "PlayfairDisplay-Italic.ttf", # italic display for stat_hero two-level contrast
}

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_font(key: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bundled TTF. Falls back to PIL default on IOError."""
    path = _ASSETS_DIR / _FONT_FILES.get(key, _FONT_FILES["body_reg"])
    try:
        return ImageFont.truetype(str(path), size)
    except (IOError, OSError):
        logger.warning("[compositor] TTF not found at %s — using PIL default", path)
        return ImageFont.load_default()


def _strip_logo_bg(logo_bytes: bytes) -> bytes:
    """Remove logo background via rembg. Falls back to original bytes on any error."""
    try:
        from rembg import remove as rembg_remove  # optional dep
        return rembg_remove(logo_bytes)
    except ImportError:
        logger.warning("[compositor] rembg not installed — skipping logo bg removal")
        return logo_bytes
    except Exception as exc:
        logger.warning("[compositor] rembg failed: %s — using original logo", exc)
        return logo_bytes


def _remove_hero_bg(hero_bytes: bytes) -> bytes | None:
    """Remove background from hero photo using rembg. Returns RGBA PNG bytes or None."""
    try:
        from rembg import remove as rembg_remove  # optional dep
        return rembg_remove(hero_bytes)
    except ImportError:
        logger.warning("[compositor] rembg not installed — cutout_hero unavailable")
        return None
    except Exception as exc:
        logger.warning("[compositor] rembg failed on hero: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #rrggbb hex to (r, g, b) int tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _text_colors(bg: str) -> tuple[tuple[int,int,int], tuple[int,int,int]]:
    """Return (primary_text_rgb, secondary_text_rgb) for a given background."""
    if _is_dark(bg):
        return (255, 255, 255), (200, 200, 200)
    return (17, 17, 17), (85, 85, 85)


def _safe_color(identity: BrandIdentity, attr: str, fallback: str) -> str:
    """Return identity.{attr} if non-None, else fallback."""
    return getattr(identity, attr, None) or fallback


def _linear_gradient(
    w: int, h: int,
    c0: tuple[int, int, int],
    c1: tuple[int, int, int],
    vertical: bool = True,
) -> Image.Image:
    """Linear gradient from c0 to c1. Falls back to solid c0 on error."""
    try:
        axis_len = h if vertical else w
        t = np.linspace(0, 1, axis_len, dtype=np.float32)
        delta = np.array(c1, dtype=np.float32) - np.array(c0, dtype=np.float32)
        arr = (np.outer(t, delta) + np.array(c0, dtype=np.float32)).clip(0, 255).astype(np.uint8)
        if vertical:
            arr = arr[:, np.newaxis, :].repeat(w, axis=1)
        else:
            arr = arr[np.newaxis, :, :].repeat(h, axis=0)
        return Image.fromarray(arr, "RGB")
    except Exception:
        return Image.new("RGB", (w, h), c0)


def _lighten(rgb: tuple[int, int, int], amount: float = 0.25) -> tuple[int, int, int]:
    """Mix color toward white."""
    return tuple(min(255, int(c + (255 - c) * amount)) for c in rgb)  # type: ignore[return-value]


def _darken(rgb: tuple[int, int, int], amount: float = 0.20) -> tuple[int, int, int]:
    """Mix color toward black."""
    return tuple(max(0, int(c * (1 - amount))) for c in rgb)  # type: ignore[return-value]


def _paste_alpha(canvas: Image.Image, draw_fn) -> None:
    """Draw translucent RGBA shapes onto an RGB canvas via alpha compositing."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(overlay))
    merged = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    canvas.paste(merged.convert("RGB"))


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        test = " ".join(current + [word])
        try:
            bbox = draw.textbbox((0, 0), test, font=font)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w = len(test) * 8  # coarse fallback for bitmap fonts
        if w > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    x: int,
    y: int,
    max_width: int,
    fill: tuple[int, int, int],
    line_spacing: int = 8,
    max_lines: int = 6,
) -> int:
    """Draw word-wrapped text. Returns the y-coordinate after the last line."""
    lines = _wrap_text(draw, text, font, max_width)[:max_lines]
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_h = bbox[3] - bbox[1]
        except AttributeError:
            line_h = 16
        cy += line_h + line_spacing
    return cy


def _auto_scale_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    key: str,
    target_width: int,
    max_size: int = 120,
    min_size: int = 36,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    """Binary-search for largest font size where text fits target_width."""
    lo, hi = min_size, max_size
    best_font = _load_font(key, min_size)
    best_size = min_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _load_font(key, mid)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w = len(text) * mid // 2
        if w <= target_width:
            best_font, best_size = font, mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best_font, best_size


# ---------------------------------------------------------------------------
# Hero image helpers
# ---------------------------------------------------------------------------

def _download_hero(url: str) -> bytes | None:
    """Download hero image bytes from a URL. Returns None on any failure."""
    try:
        import httpx
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if ct.startswith("image/"):
                    return resp.content
    except Exception as exc:
        logger.warning("[compositor] hero download failed: %s", exc)
    return None


def _circle_crop(img_bytes: bytes, diameter: int) -> Image.Image:
    """Resize img_bytes to a circle of `diameter` px. Returns RGBA Image."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = img.resize((diameter, diameter), Image.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([(0, 0), (diameter - 1, diameter - 1)], fill=255)
    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask=mask)
    return result


def _duotone(
    img: Image.Image,
    dark_color: tuple[int, int, int],
    light_color: tuple[int, int, int],
) -> Image.Image:
    """
    Apply a two-color duotone treatment to an image.

    Desaturates the image to greyscale, then maps:
      black pixels → dark_color  (shadow tones — usually a darkened brand primary)
      white pixels → light_color (highlight tones — usually the brand primary itself)
      midtones     → interpolated blend

    Returns an RGB Image the same size as the input.
    """
    from PIL import ImageOps
    grey = img.convert("L")
    black_hex = "#{:02x}{:02x}{:02x}".format(*dark_color)
    white_hex = "#{:02x}{:02x}{:02x}".format(*light_color)
    return ImageOps.colorize(grey, black=black_hex, white=white_hex).convert("RGB")


def _apply_photo_texture(
    img: Image.Image,
    brand_color: tuple[int, int, int],
) -> Image.Image:
    """Apply halftone dot overlay to a photo for editorial/risograph feel."""
    w, h = img.size
    spacing = max(18, w // 54)
    dot_r = max(4, spacing // 3)
    overlay = _halftone_overlay(w, h, brand_color, alpha=35, dot_r=dot_r, spacing=spacing)
    rgba = img.convert("RGBA")
    return Image.alpha_composite(rgba, overlay).convert("RGB")


def _halftone_overlay(
    w: int,
    h: int,
    color: tuple[int, int, int],
    alpha: int = 40,
    dot_r: int = 7,
    spacing: int = 22,
) -> Image.Image:
    """
    Generate an RGBA halftone dot-grid overlay.

    Staggered rows (each odd row offset by spacing/2) give the authentic
    risograph/screen-print feel. Returns a transparent RGBA image for
    alpha_composite onto any canvas.
    """
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    fill = (*color, alpha)
    row = 0
    y = 0
    while y <= h + spacing:
        x_off = (spacing // 2) if (row % 2) else 0
        x = x_off
        while x <= w + spacing:
            d.ellipse([(x - dot_r, y - dot_r), (x + dot_r, y + dot_r)], fill=fill)
            x += spacing
        y += spacing
        row += 1
    return overlay


def _soft_blob(
    canvas: Image.Image,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
    alpha_max: int = 60,
) -> None:
    """
    Radial gradient blob — fades from alpha_max at center to 0 at radius.
    Composites directly onto the canvas. Used for warm background decoration.
    """
    w, h = canvas.size
    x0, y0 = max(0, cx - radius), max(0, cy - radius)
    x1, y1 = min(w, cx + radius), min(h, cy + radius)
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0:
        return

    xs = np.arange(bw, dtype=np.float32) + x0 - cx
    ys = np.arange(bh, dtype=np.float32) + y0 - cy
    xx, yy = np.meshgrid(xs, ys)
    dist = np.sqrt(xx ** 2 + yy ** 2)
    alpha = np.clip(1.0 - dist / radius, 0.0, 1.0) * alpha_max
    alpha_u8 = alpha.astype(np.uint8)

    blob = np.zeros((bh, bw, 4), dtype=np.uint8)
    blob[:, :, 0] = color[0]
    blob[:, :, 1] = color[1]
    blob[:, :, 2] = color[2]
    blob[:, :, 3] = alpha_u8
    blob_img = Image.fromarray(blob, "RGBA")

    tmp = canvas.convert("RGBA")
    tmp.paste(blob_img, (x0, y0), blob_img)
    canvas.paste(tmp.convert("RGB"), (0, 0))


# ---------------------------------------------------------------------------
# Logo stamping
# ---------------------------------------------------------------------------

def _stamp_logo(
    canvas: Image.Image,
    logo_bytes: bytes,
    position: str = "bottom-right",
    max_size: tuple[int, int] = (160, 80),
    padding: int = 40,
) -> None:
    """Paste logo_bytes PNG onto canvas at the specified corner."""
    try:
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    except Exception as exc:
        logger.warning("[compositor] logo decode failed: %s", exc)
        return

    logo.thumbnail(max_size, Image.LANCZOS)
    lw, lh = logo.size
    cw, ch = canvas.size

    match position:
        case "top-left":     x, y = padding, padding
        case "top-right":    x, y = cw - lw - padding, padding
        case "bottom-right": x, y = cw - lw - padding, ch - lh - padding
        case _:              x, y = padding, ch - lh - padding  # bottom-left

    # Composite logo alpha channel onto canvas
    if canvas.mode == "RGB":
        tmp = canvas.convert("RGBA")
        tmp.paste(logo, (x, y), logo)
        # Copy composited result back to RGB canvas
        canvas.paste(tmp.convert("RGB"), (0, 0))
    else:
        canvas.paste(logo, (x, y), logo)


# ---------------------------------------------------------------------------
# Decorative asset stamping
# ---------------------------------------------------------------------------

def _stamp_decoration(
    canvas: Image.Image,
    decoration_bytes: bytes,
    position: str = "top-center",
    scale: float = 0.28,
    padding: int = 40,
) -> None:
    """Paste a decorative PNG onto canvas at the given position. Alpha-aware.

    ``scale`` is a fraction of canvas width the decoration should occupy.
    Supports six positions: top-left, top-right, top-center, bottom-left,
    bottom-right, bottom-center. Any unknown value falls back to top-center.
    """
    try:
        deco = Image.open(io.BytesIO(decoration_bytes)).convert("RGBA")
    except Exception as exc:
        logger.warning("[compositor] decoration decode failed: %s", exc)
        return

    cw, ch = canvas.size
    target_w = max(64, int(cw * scale))
    deco.thumbnail((target_w, target_w), Image.LANCZOS)
    dw, dh = deco.size

    match position:
        case "top-left":      x, y = padding, padding
        case "top-right":     x, y = cw - dw - padding, padding
        case "top-center":    x, y = (cw - dw) // 2, padding
        case "bottom-left":   x, y = padding, ch - dh - padding
        case "bottom-right":  x, y = cw - dw - padding, ch - dh - padding
        case "bottom-center": x, y = (cw - dw) // 2, ch - dh - padding
        case _:               x, y = (cw - dw) // 2, padding

    if canvas.mode == "RGB":
        tmp = canvas.convert("RGBA")
        tmp.paste(deco, (x, y), deco)
        canvas.paste(tmp.convert("RGB"), (0, 0))
    else:
        canvas.paste(deco, (x, y), deco)


# ---------------------------------------------------------------------------
# Layout archetype drawing functions
# ---------------------------------------------------------------------------

def _layout_typographic(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Clean typographic layout: solid background, 4px accent rule, large centered headline.
    Visual language: minimal-saas, developer-tool, data-dense.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    # Gradient background — very subtle warmth shift
    canvas.paste(_linear_gradient(w, h, bg_rgb, _lighten(bg_rgb, 0.06)), (0, 0))

    # Translucent decorative circle — bottom-right anchor
    r = int(min(w, h) * 0.40)
    _paste_alpha(canvas, lambda d: d.ellipse(
        [(w - r, h - r), (w + r // 2, h + r // 2)],
        fill=(*accent_rgb, 55),
    ))

    # Editorial accent rule: 8px, 40% width, left-aligned
    rule_y = int(h * 0.42)
    draw.line([(int(w * 0.08), rule_y), (int(w * 0.48), rule_y)], fill=accent_rgb, width=8)

    # Auto-scale headline to fill ~80% canvas width — display serif for drama
    padding_x = int(w * 0.08)
    font, _ = _auto_scale_font(draw, headline, "display_bold", int(w * 0.82), max_size=96, min_size=36)

    # Measure headline block height for vertical centering
    lines = _wrap_text(draw, headline, font, int(w * 0.84))[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 40
    total_h = len(lines) * (line_h + 10)
    start_y = rule_y - total_h - 32

    cy = max(int(h * 0.06), start_y)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 10

    # Subtext below rule
    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            padding_x, rule_y + 24,
            int(w * 0.84), text_secondary,
            max_lines=4,
        )

    # Slide label bottom-right
    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - padding_x, h - int(h * 0.06)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_bold_block(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Large filled accent block occupies top 42%; white/bg block below with subtext.
    Visual language: bold-enterprise, consumer-friendly.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    _, accent_text = _text_colors(accent)
    text_primary, text_secondary = _text_colors(bg)

    split_y = int(h * 0.42)

    # Top accent block — gradient from accent to lightened accent
    block_grad = _linear_gradient(w, split_y, accent_rgb, _lighten(accent_rgb, 0.18))
    canvas.paste(block_grad, (0, 0))
    # Bottom bg block — subtle gradient
    bg_grad = _linear_gradient(w, h - split_y, bg_rgb, _lighten(bg_rgb, 0.04))
    canvas.paste(bg_grad, (0, split_y))
    # 6px join strip in white
    draw.line([(0, split_y), (w, split_y)], fill=(255, 255, 255), width=6)
    # Small accent badge above join line
    badge_w, badge_h = int(w * 0.06), 5
    draw.rectangle([(int(w * 0.07), split_y - badge_h - 10),
                    (int(w * 0.07) + badge_w, split_y - 10)],
                   fill=_lighten(accent_rgb, 0.45))

    # Headline inside top block — auto-scale
    padding_x = int(w * 0.07)
    font, _ = _auto_scale_font(draw, headline, "heading_bold", int(w * 0.82), max_size=88, min_size=32)
    lines = _wrap_text(draw, headline, font, int(w * 0.86))[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 40
    total_text_h = len(lines) * (line_h + 8)
    cy = (split_y - total_text_h) // 2
    cy = max(int(h * 0.05), cy)
    inv_color = (255, 255, 255) if _is_dark(accent) else (17, 17, 17)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=inv_color)
        cy += line_h + 8

    # Subtext in lower block
    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            padding_x, split_y + 32,
            int(w * 0.86), text_secondary,
            max_lines=4,
        )

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - padding_x, h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_sidebar(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Thin vertical accent bar on left (8% width); text fills remaining 92%.
    Visual language: minimal-saas, developer-tool, data-dense.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    bar_w = int(w * 0.08)
    padding_x = bar_w + int(w * 0.06)
    content_w = w - padding_x - int(w * 0.04)

    # Subtle horizontal gradient on background
    canvas.paste(_linear_gradient(w, h, bg_rgb, _lighten(bg_rgb, 0.05), vertical=False), (0, 0))
    # Accent bar — vertical gradient for depth
    bar_grad = _linear_gradient(bar_w, h, accent_rgb, _darken(accent_rgb, 0.25))
    canvas.paste(bar_grad, (0, 0))
    # Small accent dots at top of bar
    dot_r = 4
    dot_x = bar_w // 2
    dot_color = _lighten(accent_rgb, 0.5)
    for i in range(4):
        dot_y = int(h * 0.06) + i * 14
        draw.ellipse([(dot_x - dot_r, dot_y - dot_r), (dot_x + dot_r, dot_y + dot_r)],
                     fill=dot_color)

    # Headline
    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=90, min_size=32)
    lines = _wrap_text(draw, headline, font, content_w)[:4]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 40
    cy = int(h * 0.18)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 10

    # Subtext
    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        cy += 16
        _draw_wrapped_text(draw, subtext, sub_font, padding_x, cy, content_w, text_secondary, max_lines=4)

    # Slide label
    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - int(w * 0.04), h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_frame(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Double border-frame: outer 5px + inner 2px in accent color; centered headline.
    Visual language: minimal-saas, data-dense.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    m = int(min(w, h) * 0.055)   # outer margin

    # Subtle gradient background
    canvas.paste(_linear_gradient(w, h, bg_rgb, _lighten(bg_rgb, 0.04)), (0, 0))
    # Outer frame border — rounded
    gap = 12
    draw.rounded_rectangle([(m, m), (w - m, h - m)], radius=16, outline=accent_rgb, width=5)
    # Inner frame border — rounded
    draw.rounded_rectangle([(m + gap, m + gap), (w - m - gap, h - m - gap)],
                           radius=10, outline=accent_rgb, width=2)
    # Corner accent squares at inner frame corners
    cs = 12  # corner square size
    inner_x0, inner_y0 = m + gap, m + gap
    inner_x1, inner_y1 = w - m - gap, h - m - gap
    for cx_c, cy_c in [(inner_x0, inner_y0), (inner_x1, inner_y0),
                        (inner_x0, inner_y1), (inner_x1, inner_y1)]:
        draw.rectangle([(cx_c - cs // 2, cy_c - cs // 2),
                         (cx_c + cs // 2, cy_c + cs // 2)], fill=accent_rgb)

    # Content area inside inner border
    content_x = m + gap + 24
    content_y = m + gap + 32
    content_w = w - 2 * (m + gap + 24)

    # Headline centered in frame
    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=84, min_size=28)
    lines = _wrap_text(draw, headline, font, content_w)[:4]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 40
    total_h = len(lines) * (line_h + 8)
    # Vertically center headline in upper 60% of frame interior
    available_h = int(h * 0.6) - (m + gap + 24)
    cy = content_y + max(0, (available_h - total_h) // 2)
    for line in lines:
        draw.text((content_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 8

    # Subtext
    if subtext:
        sub_font = _load_font("body_reg", max(16, w // 55))
        _draw_wrapped_text(draw, subtext, sub_font, content_x, cy + 20, content_w, text_secondary, max_lines=3)

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - m - gap - 16, h - m - gap - 16), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_hero_text(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Full-bleed primary color background; auto-scaled headline dominates; accent ellipse decoration.
    Visual language: bold-enterprise, developer-tool.
    """
    bg = _safe_color(identity, "primary_color", "#1a1a2e")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)
    padding_x = int(w * 0.08)
    content_w = int(w * 0.82)

    # Full-bleed gradient background — primary → darkened primary
    canvas.paste(_linear_gradient(w, h, bg_rgb, _darken(bg_rgb, 0.28)), (0, 0))

    # Layered translucent circles — bokeh cluster top-right
    def _draw_circles(d: ImageDraw.ImageDraw) -> None:
        # Large background circle
        r1 = int(w * 0.28)
        d.ellipse([(int(w * 0.68), int(-h * 0.08)),
                   (int(w * 0.68) + r1 * 2, int(-h * 0.08) + r1 * 2)],
                  fill=(*accent_rgb, 28))
        # Medium circle, offset
        r2 = int(w * 0.18)
        d.ellipse([(int(w * 0.76), int(h * 0.06)),
                   (int(w * 0.76) + r2 * 2, int(h * 0.06) + r2 * 2)],
                  fill=(*accent_rgb, 22))
        # Small circle
        r3 = int(w * 0.10)
        d.ellipse([(int(w * 0.62), int(h * 0.14)),
                   (int(w * 0.62) + r3 * 2, int(h * 0.14) + r3 * 2)],
                  fill=(*accent_rgb, 18))
    _paste_alpha(canvas, _draw_circles)

    # Auto-scale headline for dramatic effect
    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=120, min_size=40)
    lines = _wrap_text(draw, headline, font, content_w)[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 48
    total_text_h = len(lines) * (line_h + 10)
    cy = (h // 2) - (total_text_h // 2)
    cy = max(int(h * 0.18), cy)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 10

    # Subtext
    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        _draw_wrapped_text(draw, subtext, sub_font, padding_x, cy + 24, content_w, text_secondary, max_lines=3)

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - padding_x, h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_split_field(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Left 45% in primary color (logo area), right 55% in background (text area).
    Visual language: bold-enterprise.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    primary = _pick_accent_color(identity)
    accent = _safe_color(identity, "secondary_color", primary)
    bg_rgb = _rgb(bg)
    primary_rgb = _rgb(primary)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    split_x = int(w * 0.45)
    padding = int(w * 0.05)

    # Left gradient block — primary → darkened
    left_grad = _linear_gradient(split_x, h, primary_rgb, _darken(primary_rgb, 0.22))
    canvas.paste(left_grad, (0, 0))
    # Right bg block
    canvas.paste(_linear_gradient(w - split_x, h, bg_rgb, _lighten(bg_rgb, 0.03)), (split_x, 0))
    # Angled divider: slight diagonal (lean 20px) for dynamic boundary
    lean = 20
    draw.polygon([(split_x - lean, 0), (split_x + lean, 0),
                  (split_x + lean, h), (split_x - lean, h)],
                 fill=accent_rgb)
    # Thin highlight line on divider left edge
    draw.line([(split_x - lean, int(h * 0.08)), (split_x - lean, int(h * 0.92))],
              fill=_lighten(accent_rgb, 0.4), width=2)

    # Headline in right block
    content_w = w - split_x - 2 * padding
    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=80, min_size=28)
    lines = _wrap_text(draw, headline, font, content_w)[:4]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 36
    total_h = len(lines) * (line_h + 8)
    cy = (h - total_h) // 2
    cy = max(int(h * 0.12), cy)
    for line in lines:
        draw.text((split_x + padding, cy), line, font=font, fill=text_primary)
        cy += line_h + 8

    if subtext:
        sub_font = _load_font("body_reg", max(16, w // 55))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            split_x + padding, cy + 20,
            content_w, text_secondary,
            max_lines=3,
        )

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - padding, h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_diagonal_split(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Solid background + diagonal trapezoid block in primary color at top.
    Visual language: consumer-friendly.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    primary = _pick_accent_color(identity)
    accent = _safe_color(identity, "secondary_color", primary)
    bg_rgb = _rgb(bg)
    primary_rgb = _rgb(primary)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    # Background — subtle vertical gradient
    canvas.paste(_linear_gradient(w, h, bg_rgb, _lighten(bg_rgb, 0.04)), (0, 0))

    # Diagonal trapezoid: spans full width at top, angled bottom edge
    top_y_left  = 0
    top_y_right = 0
    bot_y_left  = int(h * 0.48)
    bot_y_right = int(h * 0.34)
    poly = [(0, top_y_left), (w, top_y_right), (w, bot_y_right), (0, bot_y_left)]

    # Gradient trapezoid — build gradient image then mask with polygon
    grad_h = bot_y_left  # tallest point
    grad_img = _linear_gradient(w, max(grad_h, 1), primary_rgb, _lighten(primary_rgb, 0.20))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    canvas.paste(grad_img.crop((0, 0, w, h)), (0, 0), mask=mask.crop((0, 0, w, h)))

    # Primary accent line along the diagonal edge
    draw.line([(0, bot_y_left), (w, bot_y_right)], fill=accent_rgb, width=5)
    # Double-line echo — 2px, 40% opacity, 6px below
    def _draw_echo(d: ImageDraw.ImageDraw) -> None:
        d.line([(0, bot_y_left + 6), (w, bot_y_right + 6)], fill=(*accent_rgb, 102), width=2)
    _paste_alpha(canvas, _draw_echo)

    # Headline in upper (colored) zone
    padding_x = int(w * 0.07)
    content_w = int(w * 0.86)
    inv_color = (255, 255, 255) if _is_dark(primary) else (17, 17, 17)
    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=84, min_size=28)
    lines = _wrap_text(draw, headline, font, content_w)[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 40
    cy = int(h * 0.08)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=inv_color)
        cy += line_h + 8

    # Subtext in lower (background) zone
    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        lower_start = max(bot_y_right + 32, int(h * 0.54))
        _draw_wrapped_text(draw, subtext, sub_font, padding_x, lower_start, content_w, text_secondary, max_lines=4)

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - padding_x, h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="rb")


def _layout_editorial_photo(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
    hero_bytes: bytes | None = None,
) -> None:
    """
    Left 55% text zone, right 45% circular photo (or accent fallback).
    Visual language: editorial, magazine-style — matches carousel_samples/image3.png.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    padding_x = int(w * 0.06)
    content_w = int(w * 0.50)

    # Subtle gradient background
    canvas.paste(_linear_gradient(w, h, bg_rgb, _lighten(bg_rgb, 0.04)), (0, 0))

    # Accent rule — editorial top-left marker
    rule_y = int(h * 0.12)
    rule_w = int(w * 0.35)
    draw.rectangle([(padding_x, rule_y), (padding_x + rule_w, rule_y + 6)], fill=accent_rgb)

    # Headline — display serif for editorial magazine feel
    font, _ = _auto_scale_font(draw, headline, "display_bold", content_w, max_size=72, min_size=28)
    lines = _wrap_text(draw, headline, font, content_w)[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 38
    cy = int(h * 0.22)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 10

    # Subtext
    if subtext:
        sub_font = _load_font("body_reg", max(16, w // 55))
        _draw_wrapped_text(draw, subtext, sub_font, padding_x, cy + 20, content_w, text_secondary, max_lines=4)

    # Slide label
    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((padding_x, h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_secondary, anchor="lb")

    # Circle — photo or accent fallback
    diameter = int(h * 0.52)
    cx = int(w * 0.60)
    cy_circle = (h - diameter) // 2

    if hero_bytes:
        try:
            circle_img = _circle_crop(hero_bytes, diameter)
            # Halftone texture on circle photo
            if settings.COMPOSITOR_PHOTO_TEXTURE_ENABLED:
                rgb_layer = circle_img.convert("RGB")
                rgb_layer = _apply_photo_texture(rgb_layer, accent_rgb)
                circle_img = Image.merge("RGBA", (*rgb_layer.split(), circle_img.split()[3]))
            # Paste on RGB canvas using alpha
            tmp = canvas.convert("RGBA")
            tmp.paste(circle_img, (cx, cy_circle), mask=circle_img)
            canvas.paste(tmp.convert("RGB"), (0, 0))
        except Exception as exc:
            logger.warning("[compositor] editorial_photo circle failed: %s", exc)
            hero_bytes = None  # fall through to accent fallback

    if not hero_bytes:
        # Accent-colored filled circle as fallback
        def _draw_fallback(d: ImageDraw.ImageDraw) -> None:
            d.ellipse([(cx, cy_circle), (cx + diameter, cy_circle + diameter)],
                      fill=(*accent_rgb, 80))
        _paste_alpha(canvas, _draw_fallback)

    # Accent ring around circle
    draw.ellipse(
        [(cx - 4, cy_circle - 4), (cx + diameter + 4, cy_circle + diameter + 4)],
        outline=accent_rgb,
        width=4,
    )


def _layout_photo_overlay(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
    hero_bytes: bytes | None = None,
) -> None:
    """
    Full-bleed hero photo as canvas base, dark gradient overlay on the left for text.
    Visual language: bold, cinematic. Falls back to _layout_hero_text when no photo.
    """
    accent = _pick_accent_color(identity)
    accent_rgb = _rgb(accent)

    if not hero_bytes:
        # Graceful fallback — use the solid dark layout
        _layout_hero_text(canvas, draw, w, h, headline, subtext, slide_label, identity)
        return

    try:
        hero = Image.open(io.BytesIO(hero_bytes)).convert("RGB")
        hero = hero.resize((w, h), Image.LANCZOS)

        # Duotone treatment: desaturate then tint with brand primary color
        # Gives the authentic brand-colored lifestyle photo look (like Lemon Health)
        if settings.COMPOSITOR_DUOTONE_ENABLED:
            primary = _safe_color(identity, "primary_color", "#1a1a2e")
            primary_rgb = _rgb(primary)
            hero = _duotone(
                hero,
                dark_color=_darken(primary_rgb, 0.55),
                light_color=_lighten(primary_rgb, 0.20),
            )

        # Halftone dot texture for editorial/print feel
        if settings.COMPOSITOR_PHOTO_TEXTURE_ENABLED:
            p = _safe_color(identity, "primary_color", "#1a1a2e")
            hero = _apply_photo_texture(hero, _rgb(p))

        canvas.paste(hero, (0, 0))
    except Exception as exc:
        logger.warning("[compositor] photo_overlay hero paste failed: %s", exc)
        _layout_hero_text(canvas, draw, w, h, headline, subtext, slide_label, identity)
        return

    # Horizontal gradient dark overlay — left side for text legibility
    overlay_w = int(w * 0.70)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ov_arr = np.zeros((h, w, 4), dtype=np.uint8)
    # Horizontal fade: alpha 210 at x=0, 0 at x=overlay_w
    alphas = np.linspace(210, 0, overlay_w, dtype=np.uint8)
    ov_arr[:, :overlay_w, 3] = alphas[np.newaxis, :]
    overlay = Image.fromarray(ov_arr, "RGBA")
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"), (0, 0))

    # Text — always white on the dark overlay
    padding_x = int(w * 0.07)
    content_w = int(w * 0.52)
    text_white = (255, 255, 255)
    text_off_white = (220, 220, 220)

    # Thin accent line at top-left
    draw.rectangle([(padding_x, int(h * 0.10)), (padding_x + int(w * 0.08), int(h * 0.10) + 4)],
                   fill=accent_rgb)

    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=84, min_size=28)
    lines = _wrap_text(draw, headline, font, content_w)[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 42
    cy = int(h * 0.20)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_white)
        cy += line_h + 10

    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        _draw_wrapped_text(draw, subtext, sub_font, padding_x, cy + 24, content_w, text_off_white, max_lines=3)

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((padding_x, h - int(h * 0.05)), slide_label, font=lbl_font,
                  fill=text_off_white, anchor="lb")


def _layout_risograph(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Risograph / screen-print inspired layout.

    Flat solid background + halftone dot field (full canvas, low alpha) +
    dense corner clusters (top-right + bottom-left) + display serif headline
    in accent color + inset border frame.

    Visual language: consumer-friendly, indie editorial, print-inspired.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    # --- Background: flat solid (print feel, no gradients) ---
    canvas.paste(Image.new("RGB", (w, h), bg_rgb))

    # --- Halftone texture layers ---
    # Scale dot geometry to canvas size so it looks consistent at 1080×1080
    spacing = max(18, w // 54)
    dot_r   = max(4, spacing // 3)

    # Layer 1: full-canvas atmosphere — very subtle
    rgba = canvas.convert("RGBA")
    rgba = Image.alpha_composite(
        rgba,
        _halftone_overlay(w, h, accent_rgb, alpha=18, dot_r=dot_r, spacing=spacing),
    )

    # Layer 2: dense cluster — top-right quadrant
    cw, ch_cluster = int(w * 0.46), int(h * 0.46)
    cluster = _halftone_overlay(cw, ch_cluster, accent_rgb, alpha=52, dot_r=dot_r + 2, spacing=spacing - 4)
    frame_tr = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    frame_tr.paste(cluster, (w - cw, 0))
    rgba = Image.alpha_composite(rgba, frame_tr)

    # Layer 3: dense cluster — bottom-left quadrant (mirrored)
    frame_bl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    frame_bl.paste(cluster, (0, h - ch_cluster))
    rgba = Image.alpha_composite(rgba, frame_bl)

    canvas.paste(rgba.convert("RGB"))

    # Refresh draw after canvas paste
    draw_obj = ImageDraw.Draw(canvas)

    # --- Inset border frame (4 px) ---
    draw_obj.rectangle([(10, 10), (w - 11, h - 11)], outline=accent_rgb, width=4)

    # --- Headline: display serif, accent-colored on light bg for print pop ---
    padding_x = int(w * 0.09)
    usable_w  = int(w * 0.82)
    font, _   = _auto_scale_font(draw_obj, headline, "display_bold", usable_w, max_size=88, min_size=30)
    lines     = _wrap_text(draw_obj, headline, font, usable_w)[:4]
    try:
        line_h = draw_obj.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 40

    total_text_h = len(lines) * (line_h + 10)
    # Place headline in upper ~60% of canvas
    text_zone_end = int(h * 0.62) if subtext else int(h * 0.88)
    cy = max(int(h * 0.12), (text_zone_end - total_text_h) // 2)

    # Use accent color for headline on light backgrounds (risograph pop)
    headline_color = accent_rgb if not _is_dark(bg) else (255, 255, 255)
    for line in lines:
        draw_obj.text((padding_x, cy), line, font=font, fill=headline_color)
        cy += line_h + 10

    # --- Subtext ---
    if subtext:
        sub_font = _load_font("body_reg", max(17, w // 52))
        _draw_wrapped_text(
            draw_obj, subtext, sub_font,
            padding_x, int(h * 0.68),
            usable_w, text_secondary,
            max_lines=3,
        )

    # --- Slide label ---
    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw_obj.text(
            (w - padding_x, h - int(h * 0.05)),
            slide_label, font=lbl_font,
            fill=text_secondary, anchor="rb",
        )


def _layout_stat_hero(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Research-stat hook slide.

    Flat solid brand-primary background (no gradient — print feel), italic display
    headline for the stat/short phrase, regular bold second line for the descriptor,
    separator rule, body text below.

    This matches Lemon Health's "Viceral Fat: / The Invisible danger" pattern:
      line 1 (italic) = the stat or bold claim
      line 2 (regular bold) = the framing/descriptor

    Visual language: consumer-friendly, data-dense, health/wellness research carousels.
    """
    primary = _safe_color(identity, "primary_color", "#1b1be8")
    accent = _pick_accent_color(identity)
    primary_rgb = _rgb(primary)
    accent_rgb = _rgb(accent)

    # Flat fill — no gradient. Print/editorial feel.
    canvas.paste(Image.new("RGB", (w, h), primary_rgb))

    # Text colors on the brand primary background
    text_primary, text_secondary = _text_colors(primary)
    padding_x = int(w * 0.09)
    content_w = int(w * 0.82)

    # ── Slide label (top-right, small) ──────────────────────────────────────
    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 68))
        draw.text(
            (w - padding_x, int(h * 0.06)),
            slide_label,
            font=lbl_font,
            fill=(*text_secondary, 200) if len(text_secondary) == 3 else text_secondary,
            anchor="rt",
        )

    # ── Split headline into two lines: italic + regular ──────────────────────
    # If subtext is provided that acts as descriptor, use headline+subtext split.
    # Otherwise split the headline at the first colon or natural midpoint.
    italic_line = headline
    regular_line = ""
    if ":" in headline:
        parts = headline.split(":", 1)
        italic_line = parts[0].strip() + ":"
        regular_line = parts[1].strip()
    elif subtext:
        regular_line = ""  # subtext goes below rule instead

    # Auto-scale italic line to fill content width
    italic_font, _ = _auto_scale_font(
        draw, italic_line, "display_italic", content_w, max_size=140, min_size=48
    )
    try:
        italic_h = draw.textbbox((0, 0), "Ag", font=italic_font)[3]
    except AttributeError:
        italic_h = 60

    # Regular second line — smaller than italic for hierarchy
    regular_font = _load_font("display_bold", max(36, italic_h - 10))
    if regular_line:
        reg_lines = _wrap_text(draw, regular_line, regular_font, content_w)[:2]
        try:
            reg_h = draw.textbbox((0, 0), "Ag", font=regular_font)[3]
        except AttributeError:
            reg_h = 40
    else:
        reg_lines = []
        reg_h = 0

    # Vertical centering — place text block in upper 55% of canvas
    total_block_h = italic_h + 14 + (len(reg_lines) * (reg_h + 8))
    cy = max(int(h * 0.18), int(h * 0.28) - total_block_h // 2)

    # Draw italic headline
    italic_lines = _wrap_text(draw, italic_line, italic_font, content_w)[:2]
    for line in italic_lines:
        draw.text((padding_x, cy), line, font=italic_font, fill=text_primary)
        cy += italic_h + 14

    # Draw regular second line
    for line in reg_lines:
        draw.text((padding_x, cy), line, font=regular_font, fill=text_primary)
        cy += reg_h + 8

    # ── Accent separator rule ────────────────────────────────────────────────
    rule_y = cy + 20
    draw.line(
        [(padding_x, rule_y), (padding_x + int(w * 0.20), rule_y)],
        fill=accent_rgb,
        width=4,
    )

    # ── Body / subtext below rule ────────────────────────────────────────────
    if subtext and not regular_line:
        # Subtext acts as the descriptor when there was no colon split
        sub_font = _load_font("body_reg", max(18, w // 50))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            padding_x, rule_y + 22,
            content_w, text_secondary,
            max_lines=4,
        )
    elif subtext and regular_line:
        # Additional supporting context below the two-line headline
        sub_font = _load_font("body_reg", max(16, w // 55))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            padding_x, rule_y + 22,
            content_w, text_secondary,
            max_lines=3,
        )

    # Decorative accent circle — bottom-left corner
    circle_r = int(min(w, h) * 0.03)
    _paste_alpha(canvas, lambda d: d.ellipse(
        [(int(w * 0.08), h - circle_r * 2 - int(h * 0.06)),
         (int(w * 0.08) + circle_r * 2, h - int(h * 0.06))],
        fill=(*accent_rgb, 120),
    ))


def _layout_soft_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Lemon Health-inspired warm card layout.

    Soft radial gradient blobs on a light background give organic depth without
    harsh geometric blocks.  Display serif headline + body text + accent pip.
    Visual language: consumer-friendly, wellness, food, lifestyle.
    """
    bg = _safe_color(identity, "background_color", "#ffffff")
    accent = _pick_accent_color(identity)
    bg_rgb = _rgb(bg)
    accent_rgb = _rgb(accent)
    text_primary, text_secondary = _text_colors(bg)

    # For very dark brand backgrounds, flip to an off-white canvas so the card
    # stays warm and legible.
    if _is_dark(bg):
        canvas_bg: tuple[int, int, int] = (250, 248, 244)
        text_primary = (24, 24, 24)
        text_secondary = (90, 85, 80)
    else:
        canvas_bg = bg_rgb
    canvas.paste(Image.new("RGB", (w, h), canvas_bg))

    # --- Soft radial blobs (background warmth) ---
    # Large blob: top-right; medium: bottom-left; tiny center whisper
    _soft_blob(canvas, int(w * 0.82), int(h * 0.14), int(w * 0.48), accent_rgb, alpha_max=70)
    _soft_blob(canvas, int(w * 0.16), int(h * 0.84), int(w * 0.36), _lighten(accent_rgb, 0.20), alpha_max=55)
    _soft_blob(canvas, int(w * 0.52), int(h * 0.52), int(w * 0.20), accent_rgb, alpha_max=20)

    # --- Content zone: generous padding ---
    padding_x = int(w * 0.10)
    content_w = int(w * 0.80)

    # Overline / category pip
    pip_y = int(h * 0.15)
    draw.rectangle(
        [(padding_x, pip_y), (padding_x + int(w * 0.07), pip_y + 6)],
        fill=accent_rgb,
    )

    # Slide label or overline text
    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 68))
        draw.text(
            (padding_x + int(w * 0.07), pip_y - 2),
            slide_label.upper(),
            font=lbl_font,
            fill=accent_rgb,
        )

    # Large display serif headline — centered in upper ~65% of canvas
    font, _ = _auto_scale_font(draw, headline, "display_bold", content_w, max_size=90, min_size=34)
    lines = _wrap_text(draw, headline, font, content_w)[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 44

    total_text_h = len(lines) * (line_h + 12)
    # Place block so that it feels centered in the top 65%
    zone_mid = int(h * 0.38)
    cy = max(int(h * 0.24), zone_mid - total_text_h // 2)

    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 12

    # Thin separator rule between headline and body
    sep_y = cy + 18
    draw.line(
        [(padding_x, sep_y), (padding_x + int(w * 0.18), sep_y)],
        fill=accent_rgb,
        width=3,
    )

    # Body text
    if subtext:
        sub_font = _load_font("body_reg", max(17, w // 52))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            padding_x, sep_y + 20,
            content_w, text_secondary,
            max_lines=5,
        )

    # Bottom-right corner: accent ellipse decoration
    corner_r = int(min(w, h) * 0.09)
    _paste_alpha(canvas, lambda d: d.ellipse(
        [(w - corner_r * 2 - int(w * 0.04), h - corner_r * 2 - int(h * 0.04)),
         (w - int(w * 0.04), h - int(h * 0.04))],
        fill=(*accent_rgb, 110),
    ))


def _layout_cutout_hero(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
    hero_bytes: bytes | None = None,
) -> None:
    """
    Photo cutout on solid brand-primary background.
    Subject (bg removed via rembg) composited right, headline left.
    Matches lemon1.png — running person on flat blue.
    Falls back to full-width headline when cutout is unavailable.
    """
    primary = _safe_color(identity, "primary_color", "#1b1be8")
    accent = _pick_accent_color(identity)
    primary_rgb = _rgb(primary)
    accent_rgb = _rgb(accent)

    # Solid flat background — print feel
    canvas.paste(Image.new("RGB", (w, h), primary_rgb))
    text_primary, text_secondary = _text_colors(primary)

    # Try cutout
    cutout_ok = False
    if hero_bytes and settings.COMPOSITOR_CUTOUT_ENABLED:
        cutout_bytes = _remove_hero_bg(hero_bytes)
        if cutout_bytes:
            try:
                cutout = Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")
                # Scale to fit right 55% of canvas, max 90% height
                target_w = int(w * 0.55)
                target_h = int(h * 0.90)
                cutout.thumbnail((target_w, target_h), Image.LANCZOS)
                # Apply halftone texture to the cutout (opaque pixels only)
                if settings.COMPOSITOR_PHOTO_TEXTURE_ENABLED:
                    rgb_layer = cutout.convert("RGB")
                    rgb_layer = _apply_photo_texture(rgb_layer, primary_rgb)
                    cutout = Image.merge("RGBA", (*rgb_layer.split(), cutout.split()[3]))
                # Position: right-center
                cx = w - cutout.width - int(w * 0.02)
                cy = (h - cutout.height) // 2
                tmp = canvas.convert("RGBA")
                tmp.paste(cutout, (cx, cy), cutout)
                canvas.paste(tmp.convert("RGB"), (0, 0))
                cutout_ok = True
            except Exception as exc:
                logger.warning("[compositor] cutout paste failed: %s", exc)

    # Headline — left side (narrow if cutout present, full width otherwise)
    padding_x = int(w * 0.07)
    content_w = int(w * 0.45) if cutout_ok else int(w * 0.82)
    font, _ = _auto_scale_font(draw, headline, "heading_bold", content_w, max_size=96, min_size=36)
    lines = _wrap_text(draw, headline, font, content_w)[:3]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 44
    cy = int(h * 0.15)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 10

    # Subtext below headline
    if subtext:
        sub_font = _load_font("body_reg", max(18, w // 50))
        _draw_wrapped_text(
            draw, subtext, sub_font,
            padding_x, cy + 20, content_w, text_secondary,
            max_lines=4,
        )

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((padding_x, h - int(h * 0.06)), slide_label, font=lbl_font,
                  fill=text_secondary)


def _layout_photo_bottom_text(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
    hero_bytes: bytes | None = None,
) -> None:
    """
    Photo fills top ~60%, solid brand primary fills bottom with headline.
    Photo gets duotone + halftone texture. Matches lemonresearch1hook.png.
    Falls back to darkened primary top when no photo is available.
    """
    primary = _safe_color(identity, "primary_color", "#1b1be8")
    accent = _pick_accent_color(identity)
    primary_rgb = _rgb(primary)
    accent_rgb = _rgb(accent)
    text_primary, _ = _text_colors(primary)

    split_y = int(h * 0.60)

    # Bottom panel: solid brand primary
    canvas.paste(Image.new("RGB", (w, h - split_y), primary_rgb), (0, split_y))

    if hero_bytes:
        try:
            hero = Image.open(io.BytesIO(hero_bytes)).convert("RGB")
            hero = hero.resize((w, split_y), Image.LANCZOS)
            # Duotone
            if settings.COMPOSITOR_DUOTONE_ENABLED:
                hero = _duotone(hero, _darken(primary_rgb, 0.55), _lighten(primary_rgb, 0.20))
            # Halftone texture
            if settings.COMPOSITOR_PHOTO_TEXTURE_ENABLED:
                hero = _apply_photo_texture(hero, primary_rgb)
            canvas.paste(hero, (0, 0))
        except Exception:
            canvas.paste(Image.new("RGB", (w, split_y), _darken(primary_rgb, 0.30)), (0, 0))
    else:
        canvas.paste(Image.new("RGB", (w, split_y), _darken(primary_rgb, 0.30)), (0, 0))

    # Headline in bottom panel — italic + regular two-line split (like stat_hero)
    padding_x = int(w * 0.07)
    content_w = int(w * 0.86)
    italic_line = headline
    regular_line = ""
    if ":" in headline:
        parts = headline.split(":", 1)
        italic_line = parts[0].strip() + ":"
        regular_line = parts[1].strip()

    italic_font, _ = _auto_scale_font(
        draw, italic_line, "display_italic", content_w, max_size=100, min_size=40
    )
    try:
        italic_h = draw.textbbox((0, 0), "Ag", font=italic_font)[3]
    except AttributeError:
        italic_h = 50

    cy = split_y + int((h - split_y) * 0.12)
    for line in _wrap_text(draw, italic_line, italic_font, content_w)[:2]:
        draw.text((padding_x, cy), line, font=italic_font, fill=text_primary)
        cy += italic_h + 10

    if regular_line:
        reg_font = _load_font("display_bold", max(34, italic_h - 12))
        for line in _wrap_text(draw, regular_line, reg_font, content_w)[:2]:
            draw.text((padding_x, cy), line, font=reg_font, fill=text_primary)
            try:
                rh = draw.textbbox((0, 0), line, font=reg_font)[3]
            except AttributeError:
                rh = 36
            cy += rh + 8

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text((w - padding_x, h - int(h * 0.04)), slide_label, font=lbl_font,
                  fill=text_primary, anchor="rb")


def _layout_editorial_with_assets(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
) -> None:
    """
    Light editorial layout with empty top ~45% reserved for a decorative
    asset cluster (stamped afterwards in _compose_slide). Headline anchored
    in the lower-middle, subtext below. Matches lemonappUI.png style.

    The decoration paste happens in _compose_slide — this function handles
    only the text zones. A dark brand background is overridden with a warm
    off-white so the botanical assets read correctly.
    """
    bg_hex = _safe_color(identity, "background_color", "#ffffff")
    if _is_dark(bg_hex):
        bg_hex = "#fdfaf5"
        canvas.paste(Image.new("RGB", (w, h), _rgb(bg_hex)))
    text_primary, text_secondary = _text_colors(bg_hex)

    padding_x = int(w * 0.08)
    content_w = int(w * 0.84)

    font, _ = _auto_scale_font(
        draw, headline, "display_bold", content_w, max_size=88, min_size=36
    )
    lines = _wrap_text(draw, headline, font, content_w)[:4]
    try:
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    except AttributeError:
        line_h = 44

    cy = int(h * 0.48)
    for line in lines:
        draw.text((padding_x, cy), line, font=font, fill=text_primary)
        cy += line_h + 8

    if subtext:
        sub_font = _load_font("body_reg", max(20, w // 46))
        _draw_wrapped_text(
            draw, subtext, sub_font, padding_x, cy + 24,
            content_w, text_secondary, max_lines=5,
        )

    if slide_label:
        lbl_font = _load_font("heading_reg", max(14, w // 65))
        draw.text(
            (padding_x, h - int(h * 0.06)),
            slide_label, font=lbl_font, fill=text_secondary,
        )


# ---------------------------------------------------------------------------
# Layout dispatch table
# ---------------------------------------------------------------------------

_LAYOUT_FNS: dict[str, Callable] = {
    "typographic":     _layout_typographic,
    "bold_block":      _layout_bold_block,
    "sidebar":         _layout_sidebar,
    "frame":           _layout_frame,
    "hero_text":       _layout_hero_text,
    "split_field":     _layout_split_field,
    "diagonal_split":  _layout_diagonal_split,
    "editorial_photo": _layout_editorial_photo,
    "photo_overlay":   _layout_photo_overlay,
    "risograph":       _layout_risograph,
    "soft_card":       _layout_soft_card,
    "stat_hero":       _layout_stat_hero,
    "cutout_hero":     _layout_cutout_hero,
    "photo_bottom_text": _layout_photo_bottom_text,
    "editorial_with_assets": _layout_editorial_with_assets,
}

# ---------------------------------------------------------------------------
# Layout selection
# ---------------------------------------------------------------------------

def _select_layout(identity: BrandIdentity, brief: ContentBrief) -> str:
    """
    Deterministic layout selection for single-slide content types.
    hash(run_id[:8] + narrative_arc + content_pillar) → index into design_category's family.
    Same run → same layout. Different runs → varied layouts.
    """
    family = DESIGN_CATEGORY_LAYOUTS.get(identity.design_category, ["typographic", "sidebar"])
    seed = (brief.run_id[:8] + brief.narrative_arc + brief.content_pillar).encode()
    idx = int(hashlib.md5(seed).hexdigest(), 16) % len(family)
    return family[idx]


# ---------------------------------------------------------------------------
# Slide-role layout mapping (carousel only)
# ---------------------------------------------------------------------------

ROLE_LAYOUT_MAP: dict[str, dict[str, list[str]]] = {
    "consumer-friendly": {
        "hook":  ["cutout_hero", "photo_bottom_text", "editorial_with_assets", "stat_hero"],
        "body":  ["soft_card", "editorial_with_assets", "risograph", "typographic"],
        "cta":   ["bold_block", "hero_text"],
    },
    "bold-enterprise": {
        "hook":  ["photo_overlay", "photo_bottom_text", "bold_block"],
        "body":  ["split_field", "sidebar", "typographic"],
        "cta":   ["hero_text", "bold_block"],
    },
    "developer-tool": {
        "hook":  ["hero_text", "stat_hero", "photo_overlay"],
        "body":  ["sidebar", "typographic", "frame"],
        "cta":   ["hero_text", "typographic"],
    },
    "minimal-saas": {
        "hook":  ["typographic", "stat_hero", "editorial_photo"],
        "body":  ["sidebar", "frame", "soft_card"],
        "cta":   ["typographic", "bold_block"],
    },
    "data-dense": {
        "hook":  ["stat_hero", "hero_text", "sidebar"],
        "body":  ["typographic", "sidebar", "frame"],
        "cta":   ["typographic", "bold_block"],
    },
}


def _assign_slide_role(slide_index: int, total_slides: int) -> str:
    """Assign hook/body/cta role based on position in carousel."""
    if slide_index == 0:
        return "hook"
    if slide_index == total_slides - 1 and total_slides > 2:
        return "cta"
    return "body"


def _select_role_layout(
    identity: BrandIdentity,
    brief: ContentBrief,
    role: str,
    body_index: int = 0,
) -> str:
    """Pick layout for a specific slide role, deterministic by run_id."""
    cat = identity.design_category or "minimal-saas"
    role_map = ROLE_LAYOUT_MAP.get(cat, ROLE_LAYOUT_MAP["minimal-saas"])
    candidates = role_map.get(role, ["typographic"])
    seed = (brief.run_id[:8] + role + str(body_index)).encode()
    idx = int(hashlib.md5(seed).hexdigest(), 16) % len(candidates)
    return candidates[idx]


# ---------------------------------------------------------------------------
# Slide data extraction
# ---------------------------------------------------------------------------

def _build_slide_data(
    formatted: FormattedContent,
    brief: ContentBrief,
    content_type: str,
) -> list[dict]:
    """Extract headline/subtext/label for each slide from FormattedContent."""

    if content_type == "carousel":
        # Reuse image_gen's existing split logic
        return _split_into_slides(formatted)

    if content_type in ("single_image", "multi_image"):
        if formatted.linkedin_content:
            return [{
                "headline": _truncate(formatted.linkedin_content.hook, 120),
                "body_text": "",
                "slide_label": None,
            }]
        if formatted.instagram_content:
            return [{
                "headline": _truncate(formatted.instagram_content.preview_text, 120),
                "body_text": "",
                "slide_label": None,
            }]

    if content_type == "story":
        if formatted.instagram_story_content:
            sc = formatted.instagram_story_content
            return [{
                "headline": _truncate(sc.hook, 80),
                "body_text": sc.cta_text,
                "slide_label": None,
            }]

    # Fallback
    return [{"headline": "See why brands choose us.", "body_text": "", "slide_label": None}]


# ---------------------------------------------------------------------------
# Single-slide renderer
# ---------------------------------------------------------------------------

_PHOTO_LAYOUTS: frozenset[str] = frozenset({"editorial_photo", "photo_overlay", "cutout_hero", "photo_bottom_text"})


def _compose_slide(
    headline: str,
    subtext: str,
    slide_label: str | None,
    identity: BrandIdentity,
    layout: str,
    canvas_size: tuple[int, int],
    hero_bytes: bytes | None = None,
    decoration_bytes: bytes | None = None,
) -> bytes:
    """Render one slide to raw PNG bytes."""
    w, h = canvas_size
    bg_hex = _safe_color(identity, "background_color", "#ffffff")
    canvas = Image.new("RGB", (w, h), color=_rgb(bg_hex))
    draw = ImageDraw.Draw(canvas)

    fn = _LAYOUT_FNS.get(layout, _layout_typographic)
    if layout in _PHOTO_LAYOUTS:
        fn(canvas, draw, w, h, headline, subtext, slide_label, identity, hero_bytes=hero_bytes)
    else:
        fn(canvas, draw, w, h, headline, subtext, slide_label, identity)

    # Decoration: stamp AFTER layout so it sits above the background but
    # BEFORE the logo so the logo always remains topmost.
    if (
        decoration_bytes
        and settings.COMPOSITOR_DECORATIONS_ENABLED
    ):
        if layout == "editorial_with_assets":
            _stamp_decoration(
                canvas, decoration_bytes,
                position="top-center", scale=0.42, padding=0,
            )
        elif layout in ("typographic", "soft_card"):
            _stamp_decoration(
                canvas, decoration_bytes,
                position="bottom-right", scale=0.18, padding=60,
            )

    # Logo: stamp AFTER layout drawing so it always appears on top
    if identity.logo_compositing_enabled and identity.logo_bytes:
        # Photo-heavy / hook layouts: logo top-right (matches Lemon Health style).
        # editorial_with_assets also uses top-right so the logo sits beside
        # the decoration cluster rather than overlapping it at top-center.
        if layout in ("cutout_hero", "photo_bottom_text", "photo_overlay",
                      "stat_hero", "editorial_with_assets"):
            logo_pos = "top-right"
        elif layout in ("split_field", "editorial_photo"):
            logo_pos = "bottom-left"   # keep logo in text zone for these layouts
        else:
            logo_pos = "bottom-right"
        _stamp_logo(canvas, identity.logo_bytes, position=logo_pos)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Mock result
# ---------------------------------------------------------------------------

def _mock_result(content_type: str) -> dict:
    """
    In mock mode, still render real Pillow images so the frontend can be tested
    without real API keys. Uses a fixed brand palette and placeholder copy.
    """
    n = 3 if content_type == "carousel" else 1
    layout = "typographic"

    class _MockIdentity:
        primary_color = "#5e6ad2"
        background_color = "#ffffff"
        secondary_color = "#333333"
        accent_color = "#ffde21"
        design_category = "minimal-saas"
        logo_bytes = None
        logo_url = None
        logo_confidence = None
        logo_compositing_enabled = False

    mock_identity = _MockIdentity()  # type: ignore[arg-type]
    slides = []
    for i in range(n):
        label = f"{i + 1:02d} / {n:02d}" if n > 1 else None
        headline = "Your SaaS product headline goes here." if i == 0 else f"Key point {i + 1} — generated in real mode."
        subtext = "This is a mock preview. Run the pipeline in real mode to see branded images."
        try:
            png_bytes = _compose_slide(
                headline=headline,
                subtext=subtext,
                slide_label=label,
                identity=mock_identity,  # type: ignore[arg-type]
                layout=layout,
                canvas_size=(1080, 1080),
            )
            png_b64 = base64.b64encode(png_bytes).decode("ascii")
        except Exception:
            png_b64 = ""
        slides.append({
            "slide_index": i,
            "png_b64": png_b64,
            "width": 1080,
            "height": 1080,
            "layout": layout,
        })

    return {
        "composed_images": slides,
        "layout": layout,
        "slide_count": n,
        "compositor_enabled": True,
        "error": None,
    }


_DISABLED_RESULT: dict = {
    "composed_images": [],
    "layout": None,
    "slide_count": 0,
    "compositor_enabled": False,
    "error": None,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    formatted: FormattedContent,
    identity: BrandIdentity,
    brief: ContentBrief,
    images: dict | None = None,
) -> dict:
    """
    Produce composed PNG images for visual content types.

    Returns:
        composed_images: list[dict]  — each has slide_index, png_b64, width, height, layout
        layout: str | None           — archetype used
        slide_count: int
        compositor_enabled: bool
        error: str | None

    Non-visual content types return immediately with compositor_enabled=False.
    All exceptions are caught internally — this function never raises.
    """
    content_type = brief.content_type

    if content_type not in VISUAL_CONTENT_TYPES:
        return dict(_DISABLED_RESULT)

    if settings.MOCK_MODE:
        return _mock_result(content_type)

    if not settings.COMPOSITOR_ENABLED:
        return dict(_DISABLED_RESULT)

    try:
        canvas_size = CANVAS_SIZES.get((brief.platform, content_type), _DEFAULT_CANVAS)
        slides = _build_slide_data(formatted, brief, content_type)
        composed: list[dict] = []

        # Carousel: role-based layout selection (hook/body/cta).
        # Single-slide types keep the existing deterministic hash selection.
        is_carousel = content_type == "carousel"

        # Strip logo background once before the slide loop (Pydantic model_copy
        # avoids mutating the caller's identity object).
        if settings.LOGO_BG_REMOVAL_ENABLED and identity.logo_bytes:
            stripped = _strip_logo_bg(identity.logo_bytes)
            identity = identity.model_copy(update={"logo_bytes": stripped})

        # Pre-compute all layouts to know if any need hero images
        total_slides = len(slides)
        if is_carousel:
            slide_layouts = []
            for i in range(total_slides):
                role = _assign_slide_role(i, total_slides)
                body_idx = i - 1 if role == "body" else 0
                slide_layouts.append(_select_role_layout(identity, brief, role, body_idx))
        else:
            slide_layouts = [_select_layout(identity, brief)]

        # Download hero image once if any layout needs it
        hero_bytes: bytes | None = None
        if any(l in _PHOTO_LAYOUTS for l in slide_layouts):
            hero_url = (images or {}).get("background_hero_url")
            if hero_url:
                hero_bytes = _download_hero(hero_url)
                if hero_bytes:
                    logger.info("[compositor] hero image downloaded (%d KB)", len(hero_bytes) // 1024)
                else:
                    logger.info("[compositor] hero download failed — photo layouts will use fallback")

        # Pre-fetch decoration pack once per run. Returns [None]*n when the
        # category has no bundled assets, so this is always safe to call.
        if settings.COMPOSITOR_DECORATIONS_ENABLED:
            decoration_pack = asset_layer.fetch_pack(
                identity.design_category or "minimal-saas",
                brief.run_id,
                total_slides,
            )
        else:
            decoration_pack = [None] * total_slides

        for i, slide in enumerate(slides):
            layout = slide_layouts[i] if i < len(slide_layouts) else slide_layouts[-1]
            png_bytes = _compose_slide(
                headline=slide.get("headline", ""),
                subtext=slide.get("body_text", ""),
                slide_label=slide.get("slide_label"),
                identity=identity,
                layout=layout,
                canvas_size=canvas_size,
                hero_bytes=hero_bytes if layout in _PHOTO_LAYOUTS else None,
                decoration_bytes=decoration_pack[i] if i < len(decoration_pack) else None,
            )
            composed.append({
                "slide_index": i,
                "png_b64": base64.b64encode(png_bytes).decode("ascii"),
                "width": canvas_size[0],
                "height": canvas_size[1],
                "layout": layout,
                "headline": slide.get("headline", ""),
                "body_text": slide.get("body_text", ""),
                "slide_label": slide.get("slide_label"),
            })

        return {
            "composed_images": composed,
            "layout": slide_layouts[0],   # primary (hook) layout for display
            "slide_count": len(composed),
            "compositor_enabled": True,
            "error": None,
        }

    except Exception as exc:
        logger.exception("[compositor] render failed: %s", exc)
        return {
            "composed_images": [],
            "layout": None,
            "slide_count": 0,
            "compositor_enabled": False,
            "error": str(exc),
        }
