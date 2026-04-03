"""Tests for heuristic PNG dark-plate background removal."""

from __future__ import annotations

import io

from PIL import Image

from agents.logo_postprocess import maybe_remove_dark_background


def _png_bytes_rgba(w: int, h: int, fill: tuple[int, int, int, int]) -> bytes:
    img = Image.new("RGBA", (w, h), fill)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_maybe_remove_dark_background_uniform_black_plate() -> None:
    """Black corners + black background: interior non-black pixel should remain."""
    w, h = 64, 64
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    px = img.load()
    assert px is not None
    px[32, 32] = (255, 255, 255, 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    out = maybe_remove_dark_background(raw)
    assert out != raw
    result = Image.open(io.BytesIO(out)).convert("RGBA")
    assert result.getpixel((32, 32))[:3] == (255, 255, 255)
    assert result.getpixel((0, 0))[3] == 0


def test_maybe_remove_dark_background_light_corners_noop() -> None:
    raw = _png_bytes_rgba(32, 32, (250, 250, 250, 255))
    assert maybe_remove_dark_background(raw) == raw


def test_maybe_remove_dark_background_charcoal_gray_plate() -> None:
    """#525252 corners have luma ~82; old cutoff (80) skipped these apple-style plates."""
    w, h = 48, 48
    plate = (0x52, 0x52, 0x52, 255)
    img = Image.new("RGBA", (w, h), plate)
    px = img.load()
    assert px is not None
    px[24, 24] = (255, 255, 255, 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    out = maybe_remove_dark_background(raw)
    assert out != raw
    result = Image.open(io.BytesIO(out)).convert("RGBA")
    assert result.getpixel((24, 24))[:3] == (255, 255, 255)
    assert result.getpixel((0, 0))[3] == 0


def test_maybe_remove_dark_background_navy_plate() -> None:
    """Dark navy tile (not pure black) with a bright glyph should keep the glyph."""
    w, h = 48, 48
    plate = (15, 22, 58, 255)
    img = Image.new("RGBA", (w, h), plate)
    px = img.load()
    assert px is not None
    px[24, 24] = (255, 214, 60, 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    out = maybe_remove_dark_background(raw)
    assert out != raw
    result = Image.open(io.BytesIO(out)).convert("RGBA")
    assert result.getpixel((24, 24))[:3] == (255, 214, 60)
    assert result.getpixel((0, 0))[3] == 0


def test_maybe_remove_dark_background_medium_gray_corners_noop() -> None:
    """Corners too light to be treated as a dark plate."""
    raw = _png_bytes_rgba(32, 32, (120, 120, 120, 255))
    assert maybe_remove_dark_background(raw) == raw


def test_maybe_remove_dark_background_non_png_noop() -> None:
    assert maybe_remove_dark_background(b"not a png") == b"not a png"
