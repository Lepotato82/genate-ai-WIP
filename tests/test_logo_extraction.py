"""Tests for logo extraction: schema validation, image helpers, and mock mode."""

from __future__ import annotations

import pytest

from agents import input_processor
from config import settings
from schemas.input_package import InputPackage


@pytest.fixture(autouse=True)
def _restore_mock_mode():
    old = settings.MOCK_MODE
    yield
    settings.MOCK_MODE = old


# ---------------------------------------------------------------------------
# _is_valid_image
# ---------------------------------------------------------------------------


def test_is_valid_image_png() -> None:
    data = b"\x89PNG" + b"\x00" * 1200
    assert input_processor._is_valid_image(data) is True


def test_is_valid_image_jpeg() -> None:
    data = b"\xff\xd8\xff" + b"\x00" * 1200
    assert input_processor._is_valid_image(data) is True


def test_is_valid_image_svg() -> None:
    data = b"<svg " + b"x" * 1200
    assert input_processor._is_valid_image(data) is True


def test_is_valid_image_webp() -> None:
    data = b"RIFF" + b"\x00" * 1200
    assert input_processor._is_valid_image(data) is True


def test_is_valid_image_gif() -> None:
    data = b"GIF8" + b"\x00" * 1200
    assert input_processor._is_valid_image(data) is True


def test_is_valid_image_svg_xml_declaration() -> None:
    data = b"<?xml" + b" " * 1200
    assert input_processor._is_valid_image(data) is True


def test_is_valid_image_false_under_min_bytes() -> None:
    data = b"\x89PNG" + b"\x00" * 10  # only 14 bytes
    assert input_processor._is_valid_image(data) is False


def test_is_valid_image_false_random_bytes() -> None:
    data = b"\x00\x01\x02\x03" * 500  # 2000 bytes but no valid magic
    assert input_processor._is_valid_image(data) is False


# ---------------------------------------------------------------------------
# URL resolution (urljoin used internally — test via _extract_logo helpers)
# ---------------------------------------------------------------------------


def test_resolve_relative_url() -> None:
    from urllib.parse import urljoin

    result = urljoin("https://example.com", "/logo.png")
    assert result == "https://example.com/logo.png"


def test_resolve_absolute_url_unchanged() -> None:
    from urllib.parse import urljoin

    result = urljoin("https://example.com", "https://cdn.example.com/logo.png")
    assert result == "https://cdn.example.com/logo.png"


# ---------------------------------------------------------------------------
# InputPackage logo field validation
# ---------------------------------------------------------------------------


def test_input_package_all_none_logo_fields() -> None:
    pkg = InputPackage(
        url="https://example.com",
        run_id="r1",
        logo_bytes=None,
        logo_url=None,
        logo_confidence=None,
    )
    assert pkg.logo_bytes is None
    assert pkg.logo_url is None
    assert pkg.logo_confidence is None


def test_input_package_all_non_none_logo_fields() -> None:
    logo_data = b"\x89PNG" + b"\x00" * 1200
    pkg = InputPackage(
        url="https://example.com",
        run_id="r2",
        logo_bytes=logo_data,
        logo_url="https://example.com/logo.png",
        logo_confidence="high",
    )
    assert pkg.logo_bytes == logo_data
    assert pkg.logo_url == "https://example.com/logo.png"
    assert pkg.logo_confidence == "high"


def test_input_package_partial_logo_state_raises() -> None:
    with pytest.raises(ValueError, match="Partial state is not permitted"):
        InputPackage(
            url="https://example.com",
            run_id="r3",
            logo_bytes=b"\x89PNG" + b"\x00" * 1200,
            logo_url=None,
            logo_confidence=None,
        )


def test_input_package_partial_logo_url_only_raises() -> None:
    with pytest.raises(ValueError, match="Partial state is not permitted"):
        InputPackage(
            url="https://example.com",
            run_id="r4",
            logo_bytes=None,
            logo_url="https://example.com/logo.png",
            logo_confidence=None,
        )


# ---------------------------------------------------------------------------
# has_logo property
# ---------------------------------------------------------------------------


def test_has_logo_false_when_none() -> None:
    pkg = InputPackage(url="https://example.com", run_id="r5")
    assert pkg.has_logo is False


def test_has_logo_true_when_set() -> None:
    pkg = InputPackage(
        url="https://example.com",
        run_id="r6",
        logo_bytes=b"\x89PNG" + b"\x00" * 1200,
        logo_url="https://example.com/logo.png",
        logo_confidence="medium",
    )
    assert pkg.has_logo is True


# ---------------------------------------------------------------------------
# MOCK_MODE returns deterministic logo fields
# ---------------------------------------------------------------------------


def test_mock_mode_returns_non_none_logo() -> None:
    settings.MOCK_MODE = True
    pkg = input_processor.run(url="https://example.com", run_id="m1")
    assert pkg.logo_bytes is not None
    assert pkg.logo_url == "https://mock.example.com/logo.png"
    assert pkg.logo_confidence == "high"
    assert pkg.has_logo is True
    assert len(pkg.logo_bytes) > input_processor.MIN_LOGO_BYTES


# ---------------------------------------------------------------------------
# Real-mode monkeypatch: logo fields propagate through run()
# ---------------------------------------------------------------------------


def test_real_mode_logo_fields_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False
    logo_data = b"\x89PNG" + b"\x00" * 2000

    def _fake(_u, _t, _r):
        return {
            "scraped_text": "hello",
            "css_tokens": {},
            "screenshot_bytes": None,
            "og_image_url": None,
            "og_image_bytes": None,
            "logo_bytes": logo_data,
            "logo_url": "https://example.com/apple-touch-icon.png",
            "logo_confidence": "high",
            "scrape_error": None,
        }

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _fake)
    pkg = input_processor.run(url="https://example.com", run_id="r7")
    assert pkg.logo_bytes == logo_data
    assert pkg.logo_url == "https://example.com/apple-touch-icon.png"
    assert pkg.logo_confidence == "high"


def test_real_mode_no_logo_returns_all_none(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _fake(_u, _t, _r):
        return {
            "scraped_text": "hello",
            "css_tokens": {},
            "screenshot_bytes": None,
            "og_image_url": None,
            "og_image_bytes": None,
            "logo_bytes": None,
            "logo_url": None,
            "logo_confidence": None,
            "scrape_error": None,
        }

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _fake)
    pkg = input_processor.run(url="https://example.com", run_id="r8")
    assert pkg.logo_bytes is None
    assert pkg.logo_url is None
    assert pkg.logo_confidence is None
    assert pkg.has_logo is False


# ---------------------------------------------------------------------------
# MIN_LOGO_BYTES constant
# ---------------------------------------------------------------------------


def test_min_logo_bytes_is_1000() -> None:
    assert input_processor.MIN_LOGO_BYTES == 1000


def test_logo_deep_query_js_traverses_open_shadow_roots() -> None:
    assert "shadowRoot" in input_processor._LOGO_DEEP_QUERY_JS
    assert "querySelectorAll" in input_processor._LOGO_DEEP_QUERY_JS


# ---------------------------------------------------------------------------
# _logo_screenshot_box_ok (CLIP candidate geometry)
# ---------------------------------------------------------------------------


def test_logo_screenshot_box_ok_typical_logo_size() -> None:
    assert input_processor._logo_screenshot_box_ok(120.0, 40.0) is True


def test_logo_screenshot_box_ok_rejects_tiny() -> None:
    assert input_processor._logo_screenshot_box_ok(20.0, 40.0) is False


def test_logo_screenshot_box_ok_accepts_24px_nav_mark() -> None:
    assert input_processor._logo_screenshot_box_ok(24.0, 24.0) is True


def test_logo_screenshot_box_ok_rejects_below_min_edge() -> None:
    assert input_processor._logo_screenshot_box_ok(20.0, 24.0) is False


def test_logo_screenshot_box_ok_rejects_wide_strip() -> None:
    assert input_processor._logo_screenshot_box_ok(500.0, 40.0) is False


def test_logo_screenshot_box_ok_rejects_extreme_aspect() -> None:
    assert input_processor._logo_screenshot_box_ok(300.0, 30.0) is False


def test_finalize_raster_logo_bytes_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(input_processor.settings, "LOGO_BG_REMOVAL_ENABLED", False)
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 500
    assert input_processor._finalize_raster_logo_bytes(data) == data


def test_finalize_raster_logo_bytes_calls_postprocess_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(input_processor.settings, "LOGO_BG_REMOVAL_ENABLED", True)
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 500

    def _fake(b: bytes) -> bytes:
        return b"processed"

    monkeypatch.setattr(
        "agents.logo_postprocess.maybe_remove_dark_background",
        _fake,
    )
    assert input_processor._finalize_raster_logo_bytes(data) == b"processed"


# ---------------------------------------------------------------------------
# _extract_logo — null page / CLIP path
# ---------------------------------------------------------------------------


class _NullPage:
    """Mock Playwright page that returns None/[] for all selectors."""

    def query_selector(self, *_a, **_kw):
        return None

    def query_selector_all(self, *_a, **_kw):
        return []


def test_extract_logo_null_page_returns_none() -> None:
    result = input_processor._extract_logo(_NullPage(), "https://example.com")
    assert result == (None, None, None)


def test_extract_logo_clip_before_og_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """Priority 3 CLIP wins before header img and og:image when enabled and mocked."""

    monkeypatch.setattr(input_processor.settings, "LOGO_CLIP_ENABLED", True)
    png_winner = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1200
    png_other = b"\x89PNG\r\n\x1a\n" + b"\x01" * 1200

    monkeypatch.setattr(
        input_processor,
        "_collect_header_nav_screenshots",
        lambda _page: [png_winner, png_other],
    )
    monkeypatch.setattr(
        "agents.logo_clip.clip_dependencies_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "agents.logo_clip.pick_best_logo_candidate",
        lambda _shots, _name: (png_winner, 0.99),
    )

    class _Page:
        def query_selector(self, selector):
            if "og:image" in selector:
                raise AssertionError("og:image should not run when CLIP succeeds")
            return None

        def query_selector_all(self, *_a, **_kw):
            return []

    logo_bytes, logo_url, confidence = input_processor._extract_logo(
        _Page(), "https://example.com"
    )
    assert confidence == "high"
    assert logo_url is not None and "clip" in logo_url
    assert logo_bytes == png_winner


# ---------------------------------------------------------------------------
# og:image size guard
# ---------------------------------------------------------------------------


def test_og_image_passes_size_guard_all_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(input_processor.settings, "LOGO_OG_IMAGE_MAX_BYTES", 0)
    monkeypatch.setattr(input_processor.settings, "LOGO_OG_IMAGE_MAX_EDGE_PX", 0)
    assert input_processor._og_image_passes_size_guard(b"\x00" * 50_000) is True


def test_og_image_passes_size_guard_default_max_bytes_rejects_large() -> None:
    """Default LOGO_OG_IMAGE_MAX_BYTES skips hero-sized og assets."""
    assert input_processor._og_image_passes_size_guard(b"x" * 600_000) is False
    assert input_processor._og_image_passes_size_guard(b"x" * 400_000) is True


def test_og_image_passes_size_guard_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(input_processor.settings, "LOGO_OG_IMAGE_MAX_BYTES", 800)
    assert input_processor._og_image_passes_size_guard(b"x" * 900) is False
    assert input_processor._og_image_passes_size_guard(b"x" * 700) is True


def test_og_image_passes_size_guard_max_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from PIL import Image

    monkeypatch.setattr(input_processor.settings, "LOGO_OG_IMAGE_MAX_EDGE_PX", 100)
    big = Image.new("RGB", (200, 40), color=(1, 2, 3))
    buf = io.BytesIO()
    big.save(buf, format="PNG")
    assert input_processor._og_image_passes_size_guard(buf.getvalue()) is False

    small = Image.new("RGB", (90, 32), color=(1, 2, 3))
    buf2 = io.BytesIO()
    small.save(buf2, format="PNG")
    assert input_processor._og_image_passes_size_guard(buf2.getvalue()) is True
