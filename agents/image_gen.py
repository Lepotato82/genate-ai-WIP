"""
Image Generation Agent — Phase 2 / Phase 6.

- Bannerbear: branded carousel slides when IMAGE_GENERATION_ENABLED=true.
- Hero background: text-to-image URL when HERO_IMAGE_ENABLED=true (Pollinations, Fal, …).
  Uses image_prompt from visual_gen (passed as ``visual``).

Falls back gracefully when disabled or when API calls fail.

Consumed by: pipeline._run_entry(), pipeline.run_stream()
"""

from __future__ import annotations

import logging
import time

import httpx

from agents.hero_image_providers import fetch_hero_image
from config import settings
from schemas.brand_identity import BrandIdentity
from schemas.formatted_content import FormattedContent

logger = logging.getLogger(__name__)

BANNERBEAR_API_BASE = "https://api.bannerbear.com/v2"


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock_result() -> dict:
    return {
        "image_urls": [
            "https://mock.example.com/slide_01.png",
            "https://mock.example.com/slide_02.png",
            "https://mock.example.com/slide_03.png",
        ],
        "slide_count": 3,
        "template_uid": "mock",
        "generation_enabled": False,
        "error": None,
        "background_hero_url": "https://mock.example.com/hero_bg.png",
        "hero_generation_enabled": True,
        "hero_error": None,
    }


def _hero_fields(visual: dict | None) -> dict[str, object]:
    """Run hero T2I when enabled. Always returns the three hero keys."""
    visual = visual or {}
    out: dict[str, object] = {
        "background_hero_url": None,
        "hero_generation_enabled": False,
        "hero_error": None,
    }
    prov = (settings.HERO_IMAGE_PROVIDER or "none").strip().lower()
    if not settings.HERO_IMAGE_ENABLED or prov in ("none", ""):
        return out

    prompt = (visual.get("image_prompt") or "").strip()
    if not prompt:
        out["hero_error"] = "no image_prompt from visual_gen"
        return out

    url, err = fetch_hero_image(prompt)
    out["background_hero_url"] = url
    out["hero_generation_enabled"] = url is not None
    out["hero_error"] = err
    return out


# ---------------------------------------------------------------------------
# Copy splitting
# ---------------------------------------------------------------------------

def _split_into_slides(formatted: FormattedContent) -> list[dict[str, str]]:
    """
    Split FormattedContent into slide dicts for Bannerbear.
    Each dict has: headline, body_text, slide_label.

    LinkedIn carousel structure:
      Slide 1: hook as headline, first body paragraph as body_text
      Slides 2-N: remaining paragraphs split into pairs
      Last slide: CTA or proof point as headline

    Returns a list of dicts, one per slide. Max 8 slides.
    """
    slides = []

    if formatted.linkedin_content:
        lc = formatted.linkedin_content
        hook = lc.hook or ""
        body = lc.body or ""

        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

        # Slide 1: hook + first paragraph
        slides.append({
            "headline": hook,
            "body_text": paragraphs[0] if paragraphs else "",
        })

        # Middle slides: pair remaining paragraphs
        remaining = paragraphs[1:]
        for i in range(0, len(remaining), 2):
            pair = remaining[i : i + 2]
            slides.append({
                "headline": pair[0],
                "body_text": pair[1] if len(pair) > 1 else "",
            })

    elif formatted.instagram_content:
        ic = formatted.instagram_content
        slides.append({
            "headline": ic.preview_text or "",
            "body_text": ic.body or "",
        })

    else:
        slides.append({
            "headline": "See why brands choose us.",
            "body_text": "",
        })

    # Cap at 8 slides, add slide labels
    slides = slides[:8]
    total = len(slides)
    for i, slide in enumerate(slides):
        slide["slide_label"] = f"{i + 1:02d} / {total:02d}"

    return slides


# ---------------------------------------------------------------------------
# Text truncation
# ---------------------------------------------------------------------------

def _truncate(text: str, max_chars: int) -> str:
    """
    Truncate text to max_chars at a word boundary.
    Bannerbear clips text that overflows — truncating here gives
    control over where it cuts.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:") + "\u2026"


# ---------------------------------------------------------------------------
# Bannerbear API helpers
# ---------------------------------------------------------------------------

def _luminance(hex_color: str) -> float:
    """
    Relative luminance of a hex color (0.0 = black, 1.0 = white).
    Uses sRGB linearisation per WCAG 2.1.
    """
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def _lin(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    """
    WCAG contrast ratio between two hex colors.
    Returns a value between 1.0 (no contrast) and 21.0 (max contrast).
    """
    la = _luminance(hex_a)
    lb = _luminance(hex_b)
    lighter = max(la, lb)
    darker = min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _is_dark(hex_color: str) -> bool:
    """Returns True if the color is dark (luminance < 0.5)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5


def _pick_accent_color(identity) -> str:
    """
    Pick the best accent color for the accent bar.

    Priority:
      1. primary_color   — if contrast against background > 1.5
      2. secondary_color — if contrast against background > 1.5
      3. accent_color    — if contrast against background > 1.5
      4. #ffffff / #000000 fallback based on background darkness

    A contrast ratio of 1.5 catches primary_color == background_color
    (ratio = 1.0) without requiring WCAG AA compliance.
    """
    bg = identity.background_color or "#ffffff"

    candidates = [
        identity.primary_color,
        identity.secondary_color,
        identity.accent_color,
    ]

    for color in candidates:
        if color and _contrast_ratio(color, bg) > 1.5:
            return color

    return "#ffffff" if _is_dark(bg) else "#000000"


def _build_modifications(
    slide: dict[str, str],
    identity: BrandIdentity,
) -> list[dict]:
    """
    Build the modifications list for one Bannerbear API call.
    Each modification targets a named layer in the template.
    """
    bg = identity.background_color or "#ffffff"
    text_primary = "#ffffff" if _is_dark(bg) else "#111111"
    text_secondary = "#cccccc" if _is_dark(bg) else "#444444"

    mods: list[dict] = [
        {
            "name": "background_color",
            "color": bg,
        },
        {
            "name": "accent_bar",
            "color": _pick_accent_color(identity),
        },
        {
            "name": "slide_label",
            "text": slide["slide_label"],
            "color": identity.secondary_color or "#888888",
        },
        {
            "name": "headline",
            "text": _truncate(slide["headline"], 120),
            "color": text_primary,
        },
        {
            "name": "body_text",
            "text": _truncate(slide["body_text"], 280),
            "color": text_secondary,
        },
    ]

    # Logo — high confidence: composite the real brand logo
    if identity.logo_url and identity.logo_compositing_enabled:
        mods.append({"name": "logo", "image_url": identity.logo_url})
    elif identity.logo_url and identity.logo_confidence == "medium":
        # Medium confidence — try the URL; may be an OG marketing image
        logger.info(
            "[image_gen] medium-confidence logo for %s: %s",
            identity.product_name,
            identity.logo_url,
        )
        mods.append({"name": "logo", "image_url": identity.logo_url})
    # low / None: omit logo mod — template default is used

    return mods


def _call_bannerbear(modifications: list[dict]) -> str | None:
    """
    Call Bannerbear synchronous image creation endpoint.
    Returns the image URL or None on failure.
    """
    try:
        with httpx.Client(timeout=settings.BANNERBEAR_TIMEOUT_SECONDS) as client:
            resp = client.post(
                f"{BANNERBEAR_API_BASE}/images",
                headers={
                    "Authorization": f"Bearer {settings.BANNERBEAR_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "template": settings.BANNERBEAR_TEMPLATE_UID,
                    "modifications": modifications,
                    "synchronous": True,
                },
            )

            if resp.status_code not in (200, 201, 202):
                logger.error(
                    "[image_gen] Bannerbear error %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None

            data = resp.json()
            image_url = data.get("image_url") or data.get("image_url_png")
            if image_url:
                return image_url

            # Async fallback — poll for completion
            uid = data.get("uid")
            if uid:
                return _poll_bannerbear(client, uid)

            logger.error("[image_gen] no image_url in response: %s", data)
            return None

    except Exception as exc:
        logger.error("[image_gen] Bannerbear call failed: %s", exc)
        return None


def _poll_bannerbear(
    client: httpx.Client,
    uid: str,
    max_attempts: int = 10,
    interval: float = 2.0,
) -> str | None:
    """Poll Bannerbear for async image completion."""
    for attempt in range(max_attempts):
        try:
            resp = client.get(
                f"{BANNERBEAR_API_BASE}/images/{uid}",
                headers={"Authorization": f"Bearer {settings.BANNERBEAR_API_KEY}"},
            )
            data = resp.json()
            status = data.get("status")

            if status == "completed":
                return data.get("image_url") or data.get("image_url_png")
            if status == "failed":
                logger.error("[image_gen] Bannerbear image failed: %s", data)
                return None

            logger.info("[image_gen] polling attempt %d: %s", attempt + 1, status)
            time.sleep(interval)

        except Exception as exc:
            logger.error("[image_gen] poll error: %s", exc)
            return None

    logger.error("[image_gen] polling timed out after %d attempts", max_attempts)
    return None


# ---------------------------------------------------------------------------
# Public run()
# ---------------------------------------------------------------------------

def run(
    formatted: FormattedContent,
    identity: BrandIdentity,
    visual: dict | None = None,
) -> dict:
    """
    Generate hero background (optional) and Bannerbear slides (optional).

    Returns dict with:
      image_urls, slide_count, template_uid, generation_enabled, error — Bannerbear
      background_hero_url, hero_generation_enabled, hero_error — text-to-image hero
    """
    if settings.MOCK_MODE:
        return _mock_result()

    hero = _hero_fields(visual)

    if not settings.IMAGE_GENERATION_ENABLED:
        logger.info("[image_gen] IMAGE_GENERATION_ENABLED=false — skipping Bannerbear")
        return {
            "image_urls": [],
            "slide_count": 0,
            "template_uid": settings.BANNERBEAR_TEMPLATE_UID,
            "generation_enabled": False,
            "error": None,
            **hero,
        }

    if not settings.BANNERBEAR_API_KEY:
        logger.warning("[image_gen] BANNERBEAR_API_KEY not set — skipping")
        return {
            "image_urls": [],
            "slide_count": 0,
            "template_uid": settings.BANNERBEAR_TEMPLATE_UID,
            "generation_enabled": False,
            "error": "BANNERBEAR_API_KEY not configured",
            **hero,
        }

    slides = _split_into_slides(formatted)
    image_urls: list[str] = []
    errors: list[str] = []

    logger.info(
        "[image_gen] generating %d slides for %s",
        len(slides),
        identity.product_name,
    )

    for i, slide in enumerate(slides):
        mods = _build_modifications(slide, identity)
        url = _call_bannerbear(mods)

        if url:
            image_urls.append(url)
            logger.info("[image_gen] slide %d/%d: %s", i + 1, len(slides), url)
        else:
            errors.append(f"slide {i + 1} failed")
            logger.error("[image_gen] slide %d/%d failed", i + 1, len(slides))

    return {
        "image_urls": image_urls,
        "slide_count": len(slides),
        "template_uid": settings.BANNERBEAR_TEMPLATE_UID,
        "generation_enabled": True,
        "error": "; ".join(errors) if errors else None,
        **hero,
    }
