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
    const tokens = {};
    // 1. Read CSS custom properties from :root computed style
    const rootStyle = getComputedStyle(document.documentElement);
    for (const sheet of document.styleSheets) {
        try {
            for (const rule of sheet.cssRules) {
                if (rule.selectorText === ':root') {
                    const text = rule.cssText;
                    const matches = text.matchAll(/(-{2}[\\w-]+)\\s*:\\s*([^;]+);/g);
                    for (const m of matches) {
                        tokens[m[1].trim()] = m[2].trim();
                    }
                }
            }
        } catch (e) { /* cross-origin stylesheet — skip */ }
    }
    // 2. Also sample computed values for known custom properties found above
    for (const key of Object.keys(tokens)) {
        const computed = rootStyle.getPropertyValue(key).trim();
        if (computed) tokens[key] = computed;
    }
    // 3. Typography signals from element styles
    const elemSelectors = ['h1','h2','h3','p','a','button','code'];
    for (const sel of elemSelectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const s = getComputedStyle(el);
        tokens[`--_font-family-${sel}`] = s.fontFamily;
        tokens[`--_font-weight-${sel}`] = s.fontWeight;
        tokens[`--_font-size-${sel}`] = s.fontSize;
        tokens[`--_color-${sel}`] = s.color;
    }
    // 4. Background of body/main
    const bodyStyle = getComputedStyle(document.body);
    tokens['--_bg-body'] = bodyStyle.backgroundColor;
    // 5. Button variants (up to 10)
    const buttons = document.querySelectorAll('button, [role=button], a.btn');
    let btnCount = 0;
    for (const btn of buttons) {
        if (btnCount >= 10) break;
        const s = getComputedStyle(btn);
        const bg = s.backgroundColor;
        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
            tokens[`--_btn-bg-${btnCount}`] = bg;
            tokens[`--_btn-color-${btnCount}`] = s.color;
            btnCount++;
        }
    }
    return tokens;
}
"""

# ---------------------------------------------------------------------------
# Framework CSS token prefixes to strip (noise, not brand signals)
# ---------------------------------------------------------------------------

_FRAMEWORK_TOKEN_PREFIXES = (
    "--mantine-",
    "--chakra-",
    "--radix-",
    "--tw-",
    "--rsuite-",
    "--ant-",
)


def _filter_css_tokens(tokens: dict) -> dict:
    return {
        k: v
        for k, v in tokens.items()
        if not any(k.startswith(p) for p in _FRAMEWORK_TOKEN_PREFIXES)
    }


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_SCRAPED_TEXT = (
    "Linear is the issue tracking tool built for high-performance teams. "
    "Streamline software projects, sprints, tasks, and bug tracking. "
    "Linear helps thousands of companies like Vercel, Raycast, and Loom "
    "move faster with purpose-built tools for product development. "
    "Keyboard-first interface. Real-time sync. Git integration. "
    "Connect to GitHub, GitLab, Figma, Slack and 40+ integrations. "
    "99.9% uptime. SOC 2 certified. Used by over 10,000 engineering teams."
)

_MOCK_CSS_TOKENS: dict[str, str] = {
    "--color-brand-bg": "#5e6ad2",
    "--color-accent": "#7170ff",
    "--color-text-primary": "#1a1a2e",
    "--color-text-secondary": "#6b7280",
    "--color-border": "#e5e7eb",
    "--color-surface": "#ffffff",
    "--color-surface-raised": "#f9fafb",
    "--font-family-sans": "Inter, system-ui, sans-serif",
    "--font-family-mono": "JetBrains Mono, monospace",
    "--font-weight-regular": "400",
    "--font-weight-medium": "510",
    "--font-weight-semibold": "590",
    "--border-radius-sm": "4px",
    "--border-radius-md": "6px",
    "--spacing-unit": "4px",
    "--_bg-body": "rgb(255, 255, 255)",
    "--_font-family-h1": "Inter, system-ui, sans-serif",
    "--_font-weight-h1": "590",
    "--_font-size-h1": "48px",
}


def _mock_input_package(
    url: str,
    run_id: str,
    org_id: str | None,
    user_image: bytes | None,
    user_document: str | None,
) -> InputPackage:
    scraped_text = _MOCK_SCRAPED_TEXT
    return InputPackage(
        url=url,
        run_id=run_id,
        org_id=org_id,
        scraped_text=scraped_text,
        css_tokens=dict(_MOCK_CSS_TOKENS),
        screenshot_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 128,  # minimal PNG stub
        og_image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
        og_image_url="https://linear.app/og.png",
        user_image=user_image,
        user_document=user_document,
        scrape_error=None,
        scrape_word_count=len(scraped_text.split()),
    )


# ---------------------------------------------------------------------------
# Real-mode helpers
# ---------------------------------------------------------------------------

def _download_image(url: str, timeout: int = 10) -> bytes | None:
    """Download an image URL and return raw bytes, or None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:
        logger.debug("OG image download failed for %s: %s", url, exc)
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
            page = await context.new_page()

            try:
                await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=timeout_seconds * 1000,
                )
            except Exception:
                # Fallback: domcontentloaded is more permissive
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_seconds * 1000,
                )

            # Dismiss cookie banners (best effort)
            for selector in [
                "button[id*='accept']",
                "button[id*='cookie']",
                "[aria-label*='Accept']",
                "[data-testid*='cookie-accept']",
                "button:has-text('Accept')",
                "button:has-text('Accept all')",
                "button:has-text('I agree')",
                "[id*='cookie'] button",
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=500):
                        await btn.click()
                        await page.wait_for_timeout(300)
                        break
                except Exception:
                    pass

            # Scroll to bottom to trigger lazy-loaded content (SPAs like Vercel, Linear)
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
            except Exception:
                pass

            # Extract CSS tokens
            try:
                css_tokens = await page.evaluate(_CSS_TOKEN_JS)
                result["css_tokens"] = _filter_css_tokens(css_tokens or {})
            except Exception as exc:
                logger.warning("CSS token extraction failed: %s", exc)
                result["css_tokens"] = {}

            # Full-page screenshot
            try:
                result["screenshot_bytes"] = await page.screenshot(full_page=True)
            except Exception as exc:
                logger.warning("Screenshot failed: %s", exc)

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
