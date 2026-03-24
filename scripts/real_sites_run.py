"""
Real-mode run: input_processor + ui_analyzer + product_analysis for fixed URLs.
Writes JSON under test_data/ in the repo root.

Usage (from repo root):
  uv run python scripts/real_sites_run.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import input_processor, product_analysis, ui_analyzer
from config import settings

SITES = [
    "https://lemonhealth.ai",
    "https://linear.app",
]

OUT_REL = Path("test_data") / "real_sites_lemon_linear.json"


def main() -> None:
    settings.MOCK_MODE = False

    payload: dict = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "mock_mode": False,
        "llm_provider": settings.LLM_PROVIDER,
        "sites": [],
    }

    for url in SITES:
        print(f"Starting: {url}")
        run_id = str(uuid4())
        scrape_error: str | None = None
        input_pkg = None
        brand = None
        product = None

        try:
            input_pkg = input_processor.run(url=url, run_id=run_id)
        except Exception as exc:  # pragma: no cover
            scrape_error = f"input_processor: {exc}"

        if input_pkg is not None:
            scrape_error = input_pkg.scrape_error or scrape_error
            try:
                brand = ui_analyzer.run(input_pkg)
            except Exception as exc:  # pragma: no cover
                scrape_error = (scrape_error + " | " if scrape_error else "") + f"ui_analyzer: {exc}"
            try:
                product = product_analysis.run(input_pkg)
            except Exception as exc:  # pragma: no cover
                scrape_error = (scrape_error + " | " if scrape_error else "") + f"product_analysis: {exc}"

        ip_json = {
            "run_id": run_id,
            "url": url,
            "scrape_word_count": input_pkg.scrape_word_count if input_pkg else 0,
            "css_token_count": len(input_pkg.css_tokens) if input_pkg else 0,
            "css_tokens": input_pkg.css_tokens if input_pkg else {},
            "has_screenshot": bool(input_pkg and input_pkg.screenshot_bytes),
            "has_og_image": bool(input_pkg and input_pkg.og_image_bytes),
            "scrape_error": scrape_error,
            "scraped_text_preview": (input_pkg.scraped_text[:800] if input_pkg else ""),
            "primary_text_preview": (input_pkg.get_primary_text()[:800] if input_pkg else ""),
        }

        payload["sites"].append(
            {
                "url": url,
                "input_package": ip_json,
                "brand_profile": brand.model_dump(mode="json") if brand else None,
                "product_knowledge": product.model_dump(mode="json") if product else None,
            }
        )

    out_path = ROOT / OUT_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
