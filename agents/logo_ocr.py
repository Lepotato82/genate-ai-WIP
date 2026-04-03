"""
Optional local OCR for logo wordmarks — soft signal for CLIP re-ranking.

Uses pytesseract when installed and the tesseract binary is on PATH.
If unavailable, all functions no-op safely (empty text, zero match score).
"""

from __future__ import annotations

import io
import logging
import re
from difflib import SequenceMatcher

from PIL import Image

logger = logging.getLogger(__name__)


def ocr_dependencies_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text_png(png_bytes: bytes) -> str:
    """Run OCR on PNG bytes; return empty string on failure or missing deps."""
    if not png_bytes.startswith(b"\x89PNG"):
        return ""
    try:
        import pytesseract
    except ImportError:
        return ""
    try:
        img = Image.open(io.BytesIO(png_bytes))
    except Exception as exc:
        logger.debug("logo_ocr: PIL decode failed: %s", exc)
        return ""
    try:
        text = pytesseract.image_to_string(img, timeout=30)
        return (text or "").strip()
    except Exception as exc:
        logger.debug("logo_ocr: tesseract failed: %s", exc)
        return ""


def name_match_score(product_name: str, ocr_text: str) -> float:
    """
    0.0–1.0 fuzzy match between inferred product name and OCR text.
    Used as a soft bonus for CLIP logits, not a hard gate.
    """
    p = re.sub(r"[^\w\s]", "", (product_name or "").lower()).strip()
    o = re.sub(r"[^\w\s]", "", (ocr_text or "").lower()).strip()
    if not p or not o:
        return 0.0
    if p in o or o in p:
        return 1.0
    return float(SequenceMatcher(None, p, o).ratio())
