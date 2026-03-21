"""
agents/input_processor.py
Genate — Input Processor agent (Step 1)

Renders the target URL in a real browser, extracts CSS tokens via
getComputedStyle(), captures a full-page screenshot, downloads the OG
image, and packages everything into an InputPackage.

NEVER raises on scrape failure — returns a partial InputPackage with
scrape_error populated so the pipeline can continue with user-provided
data only.
"""

import asyncio
import logging
import os
import re
import urllib.request

from config import settings
from schemas.input_package import InputPackage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JavaScript injected into the rendered page to extract CSS design tokens
# ---------------------------------------------------------------------------

_CSS_TOKEN_JS = """
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


async def _scrape_async(
    url: str,
    timeout_seconds: int,
) -> dict:
    """
    Single Playwright session:
    1. Connect (Browserless CDP or local Chromium).
    2. Navigate and wait for networkidle.
    3. Extract CSS tokens via JS.
    4. Capture full-page screenshot.
    5. Extract OG image URL.
    6. Extract rendered text from body.

    Returns a dict with keys:
        scraped_text, css_tokens, screenshot_bytes,
        og_image_url, og_image_bytes, scrape_error
    """
    from playwright.async_api import async_playwright

    result: dict = {
        "scraped_text": "",
        "css_tokens": {},
        "screenshot_bytes": None,
        "og_image_url": None,
        "og_image_bytes": None,
        "scrape_error": None,
    }

    browserless_key = settings.BROWSERLESS_API_KEY

    try:
        async with async_playwright() as pw:
            if browserless_key:
                # Connect to Browserless hosted service via CDP
                cdp_url = (
                    f"wss://chrome.browserless.io?token={browserless_key}"
                )
                browser = await pw.chromium.connect_over_cdp(cdp_url)
            else:
                browser = await pw.chromium.launch(headless=True)

            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
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

            # Extract CSS tokens
            try:
                css_tokens = await page.evaluate(_CSS_TOKEN_JS)
                result["css_tokens"] = css_tokens or {}
            except Exception as exc:
                logger.warning("CSS token extraction failed: %s", exc)
                result["css_tokens"] = {}

            # Full-page screenshot
            try:
                result["screenshot_bytes"] = await page.screenshot(full_page=True)
            except Exception as exc:
                logger.warning("Screenshot failed: %s", exc)

            # OG image
            try:
                og_url = await page.get_attribute(
                    'meta[property="og:image"]', "content"
                )
                if og_url:
                    result["og_image_url"] = og_url
                    result["og_image_bytes"] = _download_image(
                        og_url, timeout=timeout_seconds
                    )
            except Exception as exc:
                logger.debug("OG image extraction failed: %s", exc)

            # Rendered text
            try:
                text = await page.inner_text("body")
                # Collapse whitespace
                text = re.sub(r"\s+", " ", text).strip()
                result["scraped_text"] = text
            except Exception as exc:
                logger.warning("Text extraction failed: %s", exc)

            await context.close()
            await browser.close()

    except Exception as exc:
        result["scrape_error"] = str(exc)
        logger.error("Scrape failed for %s: %s", url, exc)

    return result


def _scrape_with_retry(url: str, timeout_seconds: int, max_retries: int) -> dict:
    """Run the async scrape with retry logic, returning the result dict."""
    last_result: dict = {
        "scraped_text": "",
        "css_tokens": {},
        "screenshot_bytes": None,
        "og_image_url": None,
        "og_image_bytes": None,
        "scrape_error": "Max retries exceeded",
    }

    for attempt in range(max_retries):
        try:
            result = asyncio.run(_scrape_async(url, timeout_seconds))
            if not result.get("scrape_error"):
                return result
            last_result = result
            logger.warning(
                "Scrape attempt %d/%d failed: %s",
                attempt + 1,
                max_retries,
                result["scrape_error"],
            )
        except Exception as exc:
            last_result["scrape_error"] = str(exc)
            logger.warning(
                "Scrape attempt %d/%d raised: %s", attempt + 1, max_retries, exc
            )

    return last_result


# ---------------------------------------------------------------------------
# LangFuse tracing (graceful if unavailable)
# ---------------------------------------------------------------------------

def _trace_langfuse(
    url: str,
    css_token_count: int,
    scrape_word_count: int,
    has_og_image: bool,
    scrape_error: str | None,
) -> None:
    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
        )
        lf.trace(
            name="input_processor",
            input={"url": url},
            output={
                "css_token_count": css_token_count,
                "scrape_word_count": scrape_word_count,
                "has_og_image": has_og_image,
                "scrape_error": scrape_error,
            },
        )
    except Exception as exc:
        logger.debug("LangFuse trace failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(
    url: str,
    run_id: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
    user_document_filename: str | None = None,
) -> InputPackage:
    """
    Step 1 — Input Processor.

    In MOCK_MODE returns deterministic data for rapid local development.
    In real mode renders the URL with Playwright, extracts CSS tokens,
    screenshot, OG image, and rendered text.

    NEVER raises — returns a partial InputPackage with scrape_error on
    failure so the pipeline can continue with user-provided data.
    """
    if settings.MOCK_MODE:
        pkg = _mock_input_package(url, run_id, org_id, user_image, user_document)
        _trace_langfuse(
            url=url,
            css_token_count=len(pkg.css_tokens),
            scrape_word_count=pkg.scrape_word_count,
            has_og_image=pkg.og_image_bytes is not None,
            scrape_error=None,
        )
        return pkg

    # ── Real mode ────────────────────────────────────────────────────
    timeout = settings.SCRAPE_TIMEOUT_SECONDS
    max_retries = settings.SCRAPE_MAX_RETRIES

    result = _scrape_with_retry(url, timeout, max_retries)

    scraped_text: str = result.get("scraped_text", "") or ""
    scrape_word_count = len(scraped_text.split()) if scraped_text else 0

    pkg = InputPackage(
        url=url,
        run_id=run_id,
        org_id=org_id,
        scraped_text=scraped_text,
        css_tokens=result.get("css_tokens") or {},
        screenshot_bytes=result.get("screenshot_bytes"),
        og_image_bytes=result.get("og_image_bytes"),
        og_image_url=result.get("og_image_url"),
        user_image=user_image,
        user_document=user_document,
        scrape_error=result.get("scrape_error"),
        scrape_word_count=scrape_word_count,
    )

    _trace_langfuse(
        url=url,
        css_token_count=len(pkg.css_tokens),
        scrape_word_count=pkg.scrape_word_count,
        has_og_image=pkg.og_image_bytes is not None,
        scrape_error=pkg.scrape_error,
    )

    return pkg
