"""
Step 1: Input Processor — Playwright scrape, CSS tokens, screenshots. No LLM.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from playwright.sync_api import sync_playwright

from config import settings
from schemas.input_package import InputPackage

logger = logging.getLogger(__name__)

_FRAMEWORK_PREFIXES = (
    "--mantine-",
    "--osano-",
    "--chakra-",
    "--radix-",
    "--tw-",
    "--rsuite-",
    "--ant-",
    "--sx-",
)

_EXTRACT_CSS_TOKENS_JS = """
() => {
  const out = {};
  const style = getComputedStyle(document.documentElement);
  for (let i = 0; i < style.length; i++) {
    const name = style.item(i);
    if (name && name.startsWith("--")) {
      const v = style.getPropertyValue(name).trim();
      if (v) out[name] = v;
    }
  }
  return out;
}
"""

_COOKIE_DISMISS_SELECTORS = [
    "#onetrust-accept-btn-handler",
    ".osano-cm-accept-all",
    'button:has-text("Accept all")',
    'button:has-text("Accept All")',
    'button:has-text("Accept")',
    'button:has-text("I agree")',
    'button:has-text("Got it")',
    '[data-testid="cookie-accept"]',
]


def _filter_css_tokens(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if any(k.startswith(p) for p in _FRAMEWORK_PREFIXES):
            continue
        if v.strip():
            out[k] = v.strip()
    return out


def _word_count(text: str) -> int:
    return len(text.split())


def _og_image_url_from_html(html: str, base_url: str) -> str | None:
    for m in re.finditer(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    ):
        return urljoin(base_url, m.group(1).strip())
    for m in re.finditer(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        html,
        re.I,
    ):
        return urljoin(base_url, m.group(1).strip())
    return None


def _fetch_og_image(url: str | None) -> tuple[bytes | None, str | None]:
    if not url:
        return None, None
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            if len(r.content) > 6 * 1024 * 1024:
                return None, url
            return r.content, url
    except Exception as exc:  # noqa: BLE001 — scrape must not raise
        logger.debug("OG image fetch failed: %s", exc)
        return None, url


def _try_dismiss_cookies(page) -> None:
    for sel in _COOKIE_DISMISS_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=2000)
                page.wait_for_timeout(300)
                break
        except Exception:  # noqa: BLE001
            continue


def _playwright_proxy() -> dict[str, str] | None:
    """Return proxy config only when URL is valid; bad .env placeholders break new_context."""
    raw = settings.BRIGHTDATA_PROXY_URL.strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https", "socks5"):
        logger.warning("BRIGHTDATA_PROXY_URL ignored (need http/https/socks5 URL): %s", raw[:80])
        return None
    if not parsed.netloc:
        logger.warning("BRIGHTDATA_PROXY_URL ignored (missing host): %s", raw[:80])
        return None
    return {"server": raw}


def _scrape_page_sync(url: str, timeout_seconds: int) -> dict:
    timeout_ms = max(1000, int(timeout_seconds * 1000))
    proxy = _playwright_proxy()

    scraped_text = ""
    css_tokens: dict[str, str] = {}
    screenshot_bytes: bytes | None = None
    og_image_url: str | None = None
    og_image_bytes: bytes | None = None
    scrape_error: str | None = None

    with sync_playwright() as p:
        browser = None
        try:
            if settings.BROWSERLESS_API_KEY.strip():
                ws = (
                    f"wss://chrome.browserless.io?token={settings.BROWSERLESS_API_KEY.strip()}"
                )
                browser = p.chromium.connect_over_cdp(ws)
            else:
                browser = p.chromium.launch(headless=True)

            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                proxy=proxy,
                ignore_https_errors=True,
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            _try_dismiss_cookies(page)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)

            raw_html = page.content()
            og_image_url = _og_image_url_from_html(raw_html, page.url)

            scraped_text = page.inner_text("body", timeout=timeout_ms) or ""
            raw_tokens = page.evaluate(_EXTRACT_CSS_TOKENS_JS)
            if isinstance(raw_tokens, dict):
                css_tokens = _filter_css_tokens(raw_tokens)

            try:
                screenshot_bytes = page.screenshot(full_page=True, type="png")
            except Exception as exc:  # noqa: BLE001
                logger.debug("Screenshot failed: %s", exc)

            context.close()
        except Exception as exc:  # noqa: BLE001
            scrape_error = str(exc)
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass

    if og_image_url and scrape_error is None:
        og_image_bytes, og_image_url = _fetch_og_image(og_image_url)

    return {
        "scraped_text": scraped_text,
        "css_tokens": css_tokens,
        "screenshot_bytes": screenshot_bytes,
        "og_image_url": og_image_url,
        "og_image_bytes": og_image_bytes,
        "scrape_error": scrape_error,
    }


def _scrape_with_retry(url: str, timeout: int, max_retries: int) -> dict:
    last: dict | None = None
    attempts = max(0, max_retries) + 1
    for _ in range(attempts):
        last = _scrape_page_sync(url, timeout)
        if last.get("scrape_error") is None and (
            last.get("scraped_text") or last.get("css_tokens")
        ):
            return last
        if last.get("scrape_error") is None and not last.get("scraped_text"):
            last["scrape_error"] = "empty scrape result"
    return last or {
        "scraped_text": "",
        "css_tokens": {},
        "screenshot_bytes": None,
        "og_image_url": None,
        "og_image_bytes": None,
        "scrape_error": "scrape failed",
    }


def _mock_input_package(
    url: str,
    run_id: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
    user_document_filename: str | None = None,
) -> InputPackage:
    scraped = (
        "Linear is a purpose-built issue tracking tool for planning and building "
        "products. Streamline your workflow, collaborate across teams, and ship "
        "faster with cycles, projects, and roadmaps. Modern software teams use "
        "Linear to manage issues, track progress, and align engineering execution."
    )
    tokens = {
        "--color-brand-bg": "#5e6ad2",
        "--color-accent": "#7170ff",
        "--foreground": "#111111",
        "--background": "#ffffff",
        "--border-radius-md": "6px",
        "--spacing-unit": "4px",
    }
    return InputPackage(
        url=url,
        run_id=run_id,
        org_id=org_id,
        scraped_text=scraped,
        css_tokens=tokens,
        screenshot_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
        og_image_bytes=None,
        og_image_url=None,
        user_image=user_image,
        user_document=user_document,
        user_document_filename=user_document_filename,
        scrape_error=None,
        scrape_word_count=_word_count(scraped),
    )


def run(
    url: str,
    run_id: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
    user_document_filename: str | None = None,
) -> InputPackage:
    try:
        if settings.MOCK_MODE:
            return _mock_input_package(
                url=url,
                run_id=run_id,
                org_id=org_id,
                user_image=user_image,
                user_document=user_document,
                user_document_filename=user_document_filename,
            )

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return InputPackage(
                url=url,
                run_id=run_id,
                org_id=org_id,
                user_image=user_image,
                user_document=user_document,
                user_document_filename=user_document_filename,
                scrape_error="invalid URL",
                scrape_word_count=0,
            )

        result = _scrape_with_retry(
            url,
            settings.SCRAPE_TIMEOUT_SECONDS,
            settings.SCRAPE_MAX_RETRIES,
        )
        scraped_text = str(result.get("scraped_text") or "")
        css_tokens = result.get("css_tokens") if isinstance(result.get("css_tokens"), dict) else {}
        css_tokens = {str(k): str(v) for k, v in css_tokens.items()}

        return InputPackage(
            url=url,
            run_id=run_id,
            org_id=org_id,
            scraped_text=scraped_text,
            css_tokens=css_tokens,
            screenshot_bytes=result.get("screenshot_bytes"),
            og_image_bytes=result.get("og_image_bytes"),
            og_image_url=result.get("og_image_url"),
            user_image=user_image,
            user_document=user_document,
            user_document_filename=user_document_filename,
            scrape_error=result.get("scrape_error"),
            scrape_word_count=_word_count(scraped_text),
        )
    except Exception as exc:  # noqa: BLE001 — never crash callers
        logger.exception("input_processor.run failed")
        return InputPackage(
            url=url,
            run_id=run_id,
            org_id=org_id,
            user_image=user_image,
            user_document=user_document,
            user_document_filename=user_document_filename,
            scrape_error=str(exc),
            scrape_word_count=0,
        )
