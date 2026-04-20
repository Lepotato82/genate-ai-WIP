"""
Text-to-image / stock-photo providers for hero / background layers (not LLM — HTTP only).

Pollinations: zero API key, generative.
Fal: uses settings.FAL_API_KEY, generative.
Pexels: uses settings.PEXELS_API_KEY, real stock photos — best for consumer-friendly brands.
  Free tier: 200 req/hr, 20K/month, commercial use OK.
  Recommended over generative options for health/wellness/lifestyle brands.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from config import settings

logger = logging.getLogger(__name__)


def _pollinations_url(prompt: str) -> str:
    encoded = quote(prompt, safe="")
    base = f"https://image.pollinations.ai/prompt/{encoded}"
    params: dict[str, Any] = {}
    if settings.POLLINATIONS_WIDTH > 0:
        params["width"] = settings.POLLINATIONS_WIDTH
    if settings.POLLINATIONS_HEIGHT > 0:
        params["height"] = settings.POLLINATIONS_HEIGHT
    if settings.POLLINATIONS_MODEL.strip():
        params["model"] = settings.POLLINATIONS_MODEL.strip()
    if params:
        return f"{base}?{urlencode(params)}"
    return base


def fetch_pollinations(prompt: str) -> tuple[str | None, str | None]:
    """
    Validate that Pollinations returns an image, then return the final URL.
    """
    url = _pollinations_url(prompt)
    try:
        with httpx.Client(
            timeout=settings.POLLINATIONS_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
    except Exception as exc:
        logger.error("[hero_image] Pollinations request failed: %s", exc)
        return None, f"pollinations request failed: {exc}"

    if resp.status_code != 200:
        return None, f"pollinations HTTP {resp.status_code}"

    ctype = (resp.headers.get("content-type") or "").lower()
    if not ctype.startswith("image/"):
        return None, f"pollinations unexpected content-type: {ctype or 'missing'}"

    return str(resp.url), None


def _extract_fal_image_url(payload: dict[str, Any]) -> str | None:
    images = payload.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"])
    image = payload.get("image")
    if isinstance(image, dict) and image.get("url"):
        return str(image["url"])
    if isinstance(payload.get("output"), dict):
        return _extract_fal_image_url(payload["output"])
    return None


def fetch_fal(prompt: str) -> tuple[str | None, str | None]:
    if not settings.FAL_API_KEY:
        return None, "FAL_API_KEY not configured"

    path = settings.FAL_HERO_MODEL_PATH.strip().strip("/")
    endpoint = f"https://fal.run/{path}"
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                endpoint,
                headers={
                    "Authorization": f"Key {settings.FAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"prompt": prompt},
            )
    except Exception as exc:
        logger.error("[hero_image] Fal request failed: %s", exc)
        return None, f"fal request failed: {exc}"

    if resp.status_code != 200:
        return None, f"fal HTTP {resp.status_code}: {resp.text[:200]}"

    try:
        data = resp.json()
    except Exception:
        return None, "fal response is not JSON"

    image_url = _extract_fal_image_url(data)
    if not image_url:
        return None, "fal response missing image URL"

    return image_url, None


def fetch_pexels(query: str) -> tuple[str | None, str | None]:
    """
    Search Pexels for a real lifestyle/stock photo matching `query`.

    Returns the `src.large2x` URL of the best-matching square-oriented photo,
    or the first landscape photo if no square is found.

    Requires settings.PEXELS_API_KEY.  Free tier: 200 req/hr, 20K/month.
    All Pexels photos are free for commercial use (Pexels License).
    """
    if not settings.PEXELS_API_KEY:
        return None, "PEXELS_API_KEY not configured"

    params = {
        "query": query,
        "per_page": settings.PEXELS_RESULTS_PER_QUERY,
        "orientation": "square",
        "size": "large",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                "https://api.pexels.com/v1/search",
                params=params,
                headers={"Authorization": settings.PEXELS_API_KEY},
            )
    except Exception as exc:
        logger.error("[hero_image] Pexels request failed: %s", exc)
        return None, f"pexels request failed: {exc}"

    if resp.status_code != 200:
        return None, f"pexels HTTP {resp.status_code}: {resp.text[:200]}"

    try:
        data = resp.json()
    except Exception:
        return None, "pexels response is not JSON"

    photos = data.get("photos") or []
    if not photos:
        # No square results — retry without orientation constraint
        logger.info("[hero_image] Pexels: no square photos for %r, retrying without orientation", query)
        try:
            with httpx.Client(timeout=20.0) as client:
                resp2 = client.get(
                    "https://api.pexels.com/v1/search",
                    params={"query": query, "per_page": settings.PEXELS_RESULTS_PER_QUERY, "size": "large"},
                    headers={"Authorization": settings.PEXELS_API_KEY},
                )
            photos = resp2.json().get("photos") or []
        except Exception:
            pass

    if not photos:
        return None, f"pexels returned no photos for query: {query!r}"

    # Prefer photos with people / subjects (higher avg_color contrast)
    photo = photos[0]
    url = (photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large")
    if not url:
        return None, "pexels photo missing src.large2x"

    logger.info("[hero_image] Pexels photo selected: %s (photographer: %s)",
                url[:60], photo.get("photographer", "unknown"))
    return url, None


def _build_pexels_query(image_prompt: str, pain_point: str = "", design_category: str = "") -> str:
    """
    Build a Pexels search query from pipeline context.

    Pexels works best with concrete subject queries ("person running outside",
    "healthy food bowl") rather than abstract prompts. This function extracts
    the most concrete noun phrase from the image_prompt and adds context.
    """
    # Strip common generative-prompt boilerplate that Pexels can't use
    strip_phrases = [
        "flat vector", "illustration", "minimalist", "gradient background",
        "no text", "no people", "clean background", "transparent background",
        "60% negative space", "asymmetric", "corporate style",
    ]
    query = image_prompt
    for phrase in strip_phrases:
        query = query.replace(phrase, "")

    # Trim to first 60 chars and clean up
    query = " ".join(query.split())[:60].strip(", .")

    # Add design-category-appropriate subject modifiers for better results
    if design_category == "consumer-friendly":
        if not any(w in query.lower() for w in ["person", "people", "woman", "man", "health", "food"]):
            query = f"healthy lifestyle {query}"
    elif design_category == "bold-enterprise":
        if "office" not in query.lower() and "business" not in query.lower():
            query = f"business professional {query}"

    return query.strip()


def fetch_hero_image(
    prompt: str,
    pain_point: str = "",
    design_category: str = "",
) -> tuple[str | None, str | None]:
    """
    Dispatch by HERO_IMAGE_PROVIDER. Returns (image_url, error_message).

    For consumer-friendly brands, Pexels (real photography) is strongly
    preferred over generative options — set HERO_IMAGE_PROVIDER=pexels.
    """
    provider = (settings.HERO_IMAGE_PROVIDER or "none").strip().lower()
    if provider in ("none", ""):
        return None, None
    if provider == "pollinations":
        return fetch_pollinations(prompt)
    if provider == "fal":
        return fetch_fal(prompt)
    if provider == "pexels":
        query = _build_pexels_query(prompt, pain_point=pain_point, design_category=design_category)
        return fetch_pexels(query)
    return None, f"unknown HERO_IMAGE_PROVIDER: {provider!r}"
