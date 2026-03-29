"""
Step 1: Input Processor — Playwright scrape, CSS tokens, screenshots. No LLM.
"""

from __future__ import annotations

import logging
import re
import urllib.request
from urllib.parse import urljoin, urlparse

import httpx
from playwright.sync_api import sync_playwright

from config import settings
from schemas.input_package import InputPackage

logger = logging.getLogger(__name__)


def _word_count(text: str) -> int:
    return len(text.split())


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

_COOKIE_DISMISS_SELECTORS = [
    "button[id*='accept']",
    "button[id*='cookie']",
    "[aria-label*='Accept']",
    "[data-testid*='cookie-accept']",
    "button:has-text('Accept')",
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
    "[id*='cookie'] button",
]


def _filter_css_tokens(tokens: dict) -> dict:
    out: dict[str, str] = {}
    for k, v in tokens.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if not v.strip():
            continue
        if any(k.startswith(p) for p in _FRAMEWORK_PREFIXES):
            continue
        out[k] = v
    return out


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


# ---------------------------------------------------------------------------
# Real-mode helpers
# ---------------------------------------------------------------------------

def _playwright_proxy() -> dict[str, str] | None:
    raw = (settings.BRIGHTDATA_PROXY_URL or "").strip()
    if not raw:
        return None
    p = urlparse(raw)
    if p.scheme not in ("http", "https"):
        return None
    return {"server": raw}


def _og_image_url_from_html(html: str, base_url: str) -> str | None:
    for pattern in (
        r'property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
    ):
        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if m:
            link = m.group(1).strip()
            if link.startswith("http://") or link.startswith("https://"):
                return link
            return urljoin(base_url.rstrip("/") + "/", link.lstrip("/"))
    return None


def _fetch_og_image(url: str | None) -> tuple[bytes | None, str | None]:
    if not url:
        return None, None
    data = _download_image(url)
    return data, url


def _download_image(url: str, timeout: int = 10) -> bytes | None:
    """Download an image URL and return raw bytes, or None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:
        logger.debug("OG image download failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Logo extraction helpers
# ---------------------------------------------------------------------------

_VALID_IMAGE_MAGIC = [
    b"\x89PNG",       # PNG
    b"\xff\xd8\xff",  # JPEG
    b"RIFF",          # WebP (starts with RIFF....WEBP)
    b"GIF8",          # GIF
    b"<svg",          # SVG (inline serialized)
    b"<?xml",         # SVG with XML declaration
]

MIN_LOGO_BYTES = 1000


def _is_valid_image(data: bytes) -> bool:
    """Check that bytes look like a real image and are above minimum size."""
    if len(data) < MIN_LOGO_BYTES:
        return False
    return any(data.startswith(magic) for magic in _VALID_IMAGE_MAGIC)


def _download_logo(url: str) -> bytes | None:
    """Download a URL with httpx (sync) and return bytes, or None on failure."""
    try:
        with httpx.Client(
            timeout=8.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Genate/1.0)"},
        ) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as exc:
        logger.debug("Logo download failed for %s: %s", url, exc)
    return None


def _extract_logo(
    page,
    base_url: str,
    css_tokens: dict | None = None,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Extract the brand logo from a fully-rendered Playwright page (sync API).
    Returns (logo_bytes, logo_url, confidence) or (None, None, None).
    Never raises — all exceptions are caught and logged.

    Priority order:
      1. apple-touch-icon link tag                        -> high
      2. <link rel="icon"> size >= 192px                  -> high
      3. <img> in <header> with logo in attr              -> high
      3.5. SVG in header/nav matching brand color/label   -> high
      4. og:image meta tag                                -> medium
      5. Any declared favicon                             -> low
    """

    # ── Priority 1: apple-touch-icon ──────────────────────────────
    try:
        el = page.query_selector(
            'link[rel="apple-touch-icon"], '
            'link[rel="apple-touch-icon-precomposed"]'
        )
        if el:
            href = el.get_attribute("href")
            if href:
                resolved = urljoin(base_url, href)
                data = _download_logo(resolved)
                if data and _is_valid_image(data):
                    return data, resolved, "high"
    except Exception as exc:
        logger.debug("logo: apple-touch-icon failed: %s", exc)

    # ── Priority 2: large declared icon (>= 192px) ───────────────
    try:
        els = page.query_selector_all('link[rel~="icon"][sizes]')
        for el in els:
            sizes = el.get_attribute("sizes") or ""
            match = re.search(r"(\d+)x\d+", sizes)
            if match and int(match.group(1)) >= 192:
                href = el.get_attribute("href")
                if href:
                    resolved = urljoin(base_url, href)
                    data = _download_logo(resolved)
                    if data and _is_valid_image(data):
                        return data, resolved, "high"
    except Exception as exc:
        logger.debug("logo: large icon failed: %s", exc)

    # ── Priority 3: <img> in <header> with logo in class/id/alt ──
    try:
        imgs = page.query_selector_all('header img, [role="banner"] img')
        for img in imgs:
            cls = (img.get_attribute("class") or "").lower()
            id_ = (img.get_attribute("id") or "").lower()
            alt = (img.get_attribute("alt") or "").lower()
            src = img.get_attribute("src") or ""
            if any("logo" in x for x in [cls, id_, alt, src.lower()]):
                resolved = urljoin(base_url, src)
                data = _download_logo(resolved)
                if data and _is_valid_image(data):
                    return data, resolved, "high"
    except Exception as exc:
        logger.debug("logo: header img failed: %s", exc)

    # ── Priority 3.5: SVG in header/nav matching brand color or label ──
    try:
        # Extract brand color from css_tokens to match against SVG fill values
        brand_color: str | None = None
        if css_tokens:
            color_keys = [
                "--color-brand", "--color-primary", "--brand-color",
                "--primary", "--color-accent", "--accent",
                "--color-brand-primary", "--color-brand-bg",
            ]
            for key in color_keys:
                val = css_tokens.get(key)
                if val and isinstance(val, str) and val.startswith("#"):
                    brand_color = val.lower()
                    break

        svg_els = page.query_selector_all(
            "header svg, nav svg, [role=\"banner\"] svg, "
            ".navbar svg, .nav svg, .header svg"
        )

        svg_fallback: tuple[bytes, str] | None = None

        for svg_el in svg_els:
            svg_html = svg_el.evaluate("el => el.outerHTML")
            if not svg_html:
                continue

            svg_lower = svg_html.lower()

            color_match = bool(
                brand_color and brand_color.lstrip("#") in svg_lower
            )
            label_match = any(
                term in svg_lower
                for term in ["logo", "brand", "mark", "icon", "aria-label", "title"]
            )

            box = svg_el.bounding_box()
            size_ok = box and box["width"] >= 24 and box["height"] >= 24

            if (color_match or label_match) and size_ok:
                svg_bytes = svg_html.encode("utf-8")
                if len(svg_bytes) >= MIN_LOGO_BYTES:
                    url = f"{base_url}#svg-header-logo"
                    logger.info(
                        "logo: found header SVG (%s) for %s",
                        "color match" if color_match else "label match",
                        base_url,
                    )
                    return svg_bytes, url, "high"

            # Collect the first size-ok multi-path SVG as a fallback
            if svg_fallback is None and size_ok and svg_html.count("<path") >= 2:
                svg_bytes = svg_html.encode("utf-8")
                if len(svg_bytes) >= MIN_LOGO_BYTES:
                    svg_fallback = (svg_bytes, f"{base_url}#svg-header-logo-fallback")

        if svg_fallback:
            logger.info("logo: using header SVG (path-count heuristic) for %s", base_url)
            return svg_fallback[0], svg_fallback[1], "high"

    except Exception as exc:
        logger.debug("logo: SVG header extraction failed: %s", exc)

    # ── Priority 4: og:image ─────────────────────────────────────
    try:
        el = page.query_selector('meta[property="og:image"]')
        if el:
            content = el.get_attribute("content")
            if content:
                resolved = urljoin(base_url, content)
                data = _download_logo(resolved)
                if data and _is_valid_image(data):
                    return data, resolved, "medium"
    except Exception as exc:
        logger.debug("logo: og:image failed: %s", exc)

    # ── Priority 6: any favicon (last resort) ────────────────────
    try:
        favicon_url = urljoin(base_url, "/favicon.ico")
        data = _download_logo(favicon_url)
        if data and _is_valid_image(data):
            return data, favicon_url, "low"

        el = page.query_selector('link[rel~="icon"]')
        if el:
            href = el.get_attribute("href")
            if href:
                resolved = urljoin(base_url, href)
                data = _download_logo(resolved)
                if data and _is_valid_image(data):
                    return data, resolved, "low"
    except Exception as exc:
        logger.debug("logo: favicon failed: %s", exc)

    logger.info("logo: no logo found for %s", base_url)
    return None, None, None


def _scrape_page_sync(url: str, timeout_seconds: int) -> dict:
    timeout_ms = max(1000, int(timeout_seconds * 1000))
    proxy = _playwright_proxy()

    scraped_text = ""
    css_tokens: dict[str, str] = {}
    screenshot_bytes: bytes | None = None
    og_image_url: str | None = None
    og_image_bytes: bytes | None = None
    logo_bytes: bytes | None = None
    logo_url: str | None = None
    logo_confidence: str | None = None
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

            try:
                page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=timeout_ms,
                )
            except Exception:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )

            for selector in _COOKIE_DISMISS_SELECTORS:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=500):
                        btn.click()
                        page.wait_for_timeout(300)
                        break
                except Exception:
                    pass

            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            except Exception:
                pass

            try:
                raw_css = page.evaluate(_EXTRACT_CSS_TOKENS_JS)
                css_tokens = _filter_css_tokens(raw_css or {})
            except Exception as exc:
                logger.warning("CSS token extraction failed: %s", exc)

            try:
                scraped_text = page.inner_text("body")[:200_000]
            except Exception:
                scraped_text = ""

            try:
                screenshot_bytes = page.screenshot(full_page=True)
            except Exception as exc:
                logger.warning("Screenshot failed: %s", exc)

            try:
                logo_bytes, logo_url, logo_confidence = _extract_logo(
                    page, url, css_tokens=css_tokens
                )
            except Exception as exc:
                logger.warning("Logo extraction failed: %s", exc)

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
        "logo_bytes": logo_bytes,
        "logo_url": logo_url,
        "logo_confidence": logo_confidence,
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
        "logo_bytes": None,
        "logo_url": None,
        "logo_confidence": None,
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
    scraped_text = _MOCK_SCRAPED_TEXT
    return InputPackage(
        url=url,
        run_id=run_id,
        org_id=org_id,
        scraped_text=scraped_text,
        css_tokens=dict(_MOCK_CSS_TOKENS),
        screenshot_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 128,
        og_image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
        og_image_url="https://linear.app/og.png",
        logo_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 1200,
        logo_url="https://mock.example.com/logo.png",
        logo_confidence="high",
        user_image=user_image,
        user_document=user_document,
        user_document_filename=user_document_filename,
        scrape_error=None,
        scrape_word_count=_word_count(scraped_text),
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
            logo_bytes=result.get("logo_bytes"),
            logo_url=result.get("logo_url"),
            logo_confidence=result.get("logo_confidence"),
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
