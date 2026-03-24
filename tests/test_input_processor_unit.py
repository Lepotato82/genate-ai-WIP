"""Unit tests for agents/input_processor.py (25+ cases)."""

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


def test_filter_css_tokens_strips_mantine_prefix() -> None:
    raw = {"--mantine-color": "red", "--foreground": "#111"}
    assert "--mantine-color" not in input_processor._filter_css_tokens(raw)
    assert input_processor._filter_css_tokens(raw)["--foreground"] == "#111"


def test_filter_css_tokens_strips_all_framework_prefixes() -> None:
    prefixes = (
        "--mantine-x",
        "--osano-y",
        "--chakra-z",
        "--radix-a",
        "--tw-b",
        "--rsuite-c",
        "--ant-d",
    )
    raw = {p: "1" for p in prefixes}
    assert input_processor._filter_css_tokens(raw) == {}


def test_filter_css_tokens_keeps_custom_underscore_tokens() -> None:
    raw = {"--_font-body": "Inter", "--_color-brand": "#00f"}
    out = input_processor._filter_css_tokens(raw)
    assert out["--_font-body"] == "Inter"
    assert out["--_color-brand"] == "#00f"


def test_filter_css_tokens_skips_non_string_key_or_value() -> None:
    raw = {"--ok": "v", 1: "bad", "--bad": 2}
    out = input_processor._filter_css_tokens(raw)
    assert list(out.keys()) == ["--ok"]


def test_filter_css_tokens_skips_empty_value() -> None:
    assert input_processor._filter_css_tokens({"--x": "  "}) == {}


def test_word_count_empty_and_text() -> None:
    assert input_processor._word_count("") == 0
    assert input_processor._word_count("a b c") == 3


def test_og_image_url_property_before_content() -> None:
    html = '<head><meta property="og:image" content="/logo.png"></head>'
    assert input_processor._og_image_url_from_html(html, "https://ex.com") == "https://ex.com/logo.png"


def test_og_image_url_content_before_property() -> None:
    html = '<meta content="https://cdn.example.com/a.png" property="og:image" />'
    assert (
        input_processor._og_image_url_from_html(html, "https://ex.com")
        == "https://cdn.example.com/a.png"
    )


def test_og_image_url_none_when_missing() -> None:
    assert input_processor._og_image_url_from_html("<html></html>", "https://ex.com") is None


def test_fetch_og_image_returns_none_for_none_url() -> None:
    b, u = input_processor._fetch_og_image(None)
    assert b is None and u is None


def test_mock_run_sets_run_id_org_id_and_priority_fields() -> None:
    settings.MOCK_MODE = True
    pkg = input_processor.run(
        url="https://linear.app",
        run_id="rid-99",
        org_id="org-1",
        user_image=b"img",
        user_document="doc text " * 20,
        user_document_filename="brief.md",
    )
    assert pkg.run_id == "rid-99"
    assert pkg.org_id == "org-1"
    assert pkg.user_document_filename == "brief.md"
    assert pkg.get_primary_image() == b"img"
    assert "linear" in pkg.get_primary_text().lower() or len(pkg.get_primary_text()) > 10


def test_mock_run_data_source_scraped_only_without_user_doc() -> None:
    settings.MOCK_MODE = True
    pkg = input_processor.run(url="https://a.com", run_id="r1")
    assert pkg.data_source == "scraped_only"


def test_mock_run_data_source_scraped_and_user_document_when_both_present() -> None:
    settings.MOCK_MODE = True
    pkg = input_processor.run(
        url="https://a.com",
        run_id="r2",
        user_document="only me " * 15,
    )
    assert pkg.data_source == "scraped_and_user_document"


def test_invalid_url_returns_scrape_error_not_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _ok(*_a, **_k):
        raise AssertionError("should not scrape in invalid URL path")

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _ok)
    pkg = input_processor.run(url="not-a-url", run_id="x")
    assert pkg.scrape_error == "invalid URL"
    assert pkg.scraped_text == ""


def test_scrape_with_retry_monkeypatch_merges_into_package(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _fake(_url, _t, _r):
        return {
            "scraped_text": "hello world",
            "css_tokens": {"--foreground": "#000"},
            "screenshot_bytes": b"png",
            "og_image_url": None,
            "og_image_bytes": None,
            "scrape_error": None,
        }

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _fake)
    pkg = input_processor.run(url="https://valid.example", run_id="z1")
    assert pkg.scrape_error is None
    assert pkg.scraped_text == "hello world"
    assert pkg.css_tokens["--foreground"] == "#000"
    assert pkg.screenshot_bytes == b"png"


def test_outer_exception_returns_input_package_with_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _boom(*_a, **_k):
        raise RuntimeError("surprise")

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _boom)
    pkg = input_processor.run(url="https://valid.example", run_id="e1")
    assert "surprise" in (pkg.scrape_error or "")
    assert isinstance(pkg, InputPackage)


def test_scrape_result_coerces_css_token_keys_to_str(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _fake(_u, _t, _r):
        return {
            "scraped_text": "",
            "css_tokens": {"--x": "y"},
            "screenshot_bytes": None,
            "og_image_url": None,
            "og_image_bytes": None,
            "scrape_error": None,
        }

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _fake)
    pkg = input_processor.run(url="https://valid.example", run_id="c1")
    assert isinstance(next(iter(pkg.css_tokens.keys())), str)


def test_framework_prefix_tuple_includes_sx() -> None:
    assert "--sx-" in input_processor._FRAMEWORK_PREFIXES


def test_filter_css_tokens_strips_sx_prefix() -> None:
    raw = {"--sx-color": "red", "--foreground": "#111"}
    out = input_processor._filter_css_tokens(raw)
    assert "--sx-color" not in out
    assert out["--foreground"] == "#111"


def test_framework_prefix_tuple_length() -> None:
    assert len(input_processor._FRAMEWORK_PREFIXES) == 8


def test_cookie_selectors_is_non_empty_list() -> None:
    assert len(input_processor._COOKIE_DISMISS_SELECTORS) >= 5


def test_extract_css_tokens_js_contains_computed_style() -> None:
    assert "getComputedStyle" in input_processor._EXTRACT_CSS_TOKENS_JS


def test_mock_input_package_helper_matches_run_mock_shape() -> None:
    settings.MOCK_MODE = True
    a = input_processor.run(url="https://b.com", run_id="m1")
    b = input_processor._mock_input_package(url="https://b.com", run_id="m1")
    assert type(a) is type(b)
    assert a.scrape_word_count == b.scrape_word_count


def test_scrape_with_retry_returns_last_result_on_repeated_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def _fail_page(_u, _t):
        calls["n"] += 1
        return {
            "scraped_text": "",
            "css_tokens": {},
            "screenshot_bytes": None,
            "og_image_url": None,
            "og_image_bytes": None,
            "scrape_error": "timeout",
        }

    monkeypatch.setattr(input_processor, "_scrape_page_sync", _fail_page)
    old = settings.SCRAPE_MAX_RETRIES
    try:
        settings.SCRAPE_MAX_RETRIES = 1
        out = input_processor._scrape_with_retry("https://x.com", 5, 1)
        assert out["scrape_error"] == "timeout"
        assert calls["n"] == 2
    finally:
        settings.SCRAPE_MAX_RETRIES = old


def test_scrape_with_retry_stops_early_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    n = {"c": 0}

    def _page(_u, _t):
        n["c"] += 1
        if n["c"] < 2:
            return {
                "scraped_text": "",
                "css_tokens": {},
                "screenshot_bytes": None,
                "og_image_url": None,
                "og_image_bytes": None,
                "scrape_error": "bad",
            }
        return {
            "scraped_text": "ok text here",
            "css_tokens": {},
            "screenshot_bytes": None,
            "og_image_url": None,
            "og_image_bytes": None,
            "scrape_error": None,
        }

    monkeypatch.setattr(input_processor, "_scrape_page_sync", _page)
    out = input_processor._scrape_with_retry("https://x.com", 5, 3)
    assert out["scraped_text"] == "ok text here"
    assert out["scrape_error"] is None
    assert n["c"] == 2


def test_filter_preserves_blue_and_gray_vars() -> None:
    raw = {"--blue-500": "#00f", "--gray-100": "#eee"}
    assert input_processor._filter_css_tokens(raw) == raw


def test_module_has_no_chat_completion_import() -> None:
    import agents.input_processor as mod

    assert not hasattr(mod, "chat_completion")


def test_playwright_proxy_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BRIGHTDATA_PROXY_URL", "")
    assert input_processor._playwright_proxy() is None


def test_playwright_proxy_none_for_invalid_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BRIGHTDATA_PROXY_URL", "not-a-valid-proxy-url")
    assert input_processor._playwright_proxy() is None


def test_playwright_proxy_returns_dict_for_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BRIGHTDATA_PROXY_URL", "http://127.0.0.1:24000")
    assert input_processor._playwright_proxy() == {"server": "http://127.0.0.1:24000"}
