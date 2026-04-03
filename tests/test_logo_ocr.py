"""Tests for logo OCR soft matching (no tesseract binary required)."""

from __future__ import annotations

import io
import sys
from types import ModuleType

from PIL import Image

from agents import logo_ocr


def test_name_match_score_empty() -> None:
    assert logo_ocr.name_match_score("", "Acme") == 0.0
    assert logo_ocr.name_match_score("Acme", "") == 0.0


def test_name_match_score_substring() -> None:
    assert logo_ocr.name_match_score("Acme", "Acme Corp Logo") == 1.0
    assert logo_ocr.name_match_score("Acme Corp", "acme") == 1.0


def test_name_match_score_fuzzy() -> None:
    r = logo_ocr.name_match_score("Linear", "L1near")
    assert 0.0 < r < 1.0


def test_extract_text_png_non_png() -> None:
    assert logo_ocr.extract_text_png(b"notpng") == ""


def test_extract_text_png_fake_tesseract_module() -> None:
    img = Image.new("RGB", (24, 24), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()

    fake = ModuleType("pytesseract")

    def _ocr(_im, timeout=30):
        return "Acme Brand"

    fake.image_to_string = _ocr
    fake.get_tesseract_version = lambda: "5.0.0"

    old = sys.modules.pop("pytesseract", None)
    try:
        sys.modules["pytesseract"] = fake
        assert logo_ocr.extract_text_png(png) == "Acme Brand"
    finally:
        if old is not None:
            sys.modules["pytesseract"] = old
        else:
            sys.modules.pop("pytesseract", None)
