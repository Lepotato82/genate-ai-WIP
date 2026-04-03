"""
Text-to-image providers for hero / background layers (not LLM — HTTP only).

Pollinations: zero API key. Fal: uses settings.FAL_API_KEY.
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


def fetch_hero_image(prompt: str) -> tuple[str | None, str | None]:
    """
    Dispatch by HERO_IMAGE_PROVIDER. Returns (image_url, error_message).
    """
    provider = (settings.HERO_IMAGE_PROVIDER or "none").strip().lower()
    if provider in ("none", ""):
        return None, None
    if provider == "pollinations":
        return fetch_pollinations(prompt)
    if provider == "fal":
        return fetch_fal(prompt)
    return None, f"unknown HERO_IMAGE_PROVIDER: {provider!r}"
