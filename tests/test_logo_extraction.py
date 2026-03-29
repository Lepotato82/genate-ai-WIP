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


# ---------------------------------------------------------------------------
# _extract_logo — css_tokens parameter
# ---------------------------------------------------------------------------


class _NullPage:
    """Mock Playwright page that returns None/[] for all selectors."""

    def query_selector(self, *_a, **_kw):
        return None

    def query_selector_all(self, *_a, **_kw):
        return []


def test_extract_logo_css_tokens_none_does_not_crash() -> None:
    result = input_processor._extract_logo(_NullPage(), "https://example.com", css_tokens=None)
    assert result == (None, None, None)


def test_extract_logo_css_tokens_empty_does_not_crash() -> None:
    result = input_processor._extract_logo(_NullPage(), "https://example.com", css_tokens={})
    assert result == (None, None, None)


def test_extract_logo_svg_priority_before_og_image() -> None:
    """Priority 3.5 SVG extraction returns high-confidence before reaching og:image."""

    # Build a large enough SVG with multiple paths and a logo label
    svg_content = (
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="logo" '
        'width="120" height="40">'
        + "<path d='M0 0'/>" * 10
        + "</svg>"
    )
    svg_content = svg_content + " " * max(0, input_processor.MIN_LOGO_BYTES - len(svg_content))
    svg_bytes = svg_content.encode("utf-8")

    class _BoundingBox:
        def bounding_box(self):
            return {"width": 120, "height": 40}

        def evaluate(self, _expr):
            return svg_content

    class _SvgPage:
        def query_selector(self, selector):
            # og:image exists — but should NOT be reached before SVG succeeds
            if "og:image" in selector:
                raise AssertionError("og:image was reached — SVG priority failed")
            return None

        def query_selector_all(self, selector):
            if "svg" in selector:
                return [_BoundingBox()]
            return []

    logo_bytes, logo_url, confidence = input_processor._extract_logo(
        _SvgPage(), "https://example.com", css_tokens={}
    )

    assert confidence == "high"
    assert logo_url is not None and "svg" in logo_url
    assert logo_bytes is not None and len(logo_bytes) >= input_processor.MIN_LOGO_BYTES
