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
    "https://linear.app",
    "https://vercel.com",
    "https://railway.com",
]


def main() -> None:
    settings.MOCK_MODE = False

    payload: dict = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "sites": [],
    }

    summary_rows: list[dict] = []

    for url in SITES:
        print(f"Starting site: {url}")
        run_id = str(uuid4())

        input_pkg = None
        brand = None
        product = None
        scrape_error: str | None = None

        try:
            input_pkg = input_processor.run(url=url, run_id=run_id)
        except Exception as exc:  # pragma: no cover - safety for real runs
            scrape_error = f"input_processor error: {exc}"

        if input_pkg is not None:
            scrape_error = input_pkg.scrape_error or scrape_error
            try:
                brand = ui_analyzer.run(input_pkg)
            except Exception as exc:  # pragma: no cover - safety for real runs
                scrape_error = (scrape_error + " | " if scrape_error else "") + f"ui_analyzer error: {exc}"

            try:
                product = product_analysis.run(input_pkg)
            except Exception as exc:  # pragma: no cover - safety for real runs
                scrape_error = (scrape_error + " | " if scrape_error else "") + f"product_analysis error: {exc}"

        input_package_json = {
            "css_token_count": len(input_pkg.css_tokens) if input_pkg else 0,
            "css_tokens": input_pkg.css_tokens if input_pkg else {},
            "scrape_word_count": input_pkg.scrape_word_count if input_pkg else 0,
            "has_screenshot": bool(input_pkg and input_pkg.screenshot_bytes is not None),
            "has_og_image": bool(input_pkg and input_pkg.og_image_bytes is not None),
            "scrape_error": scrape_error,
            "scraped_text_preview": (input_pkg.scraped_text[:500] if input_pkg else ""),
        }

        payload["sites"].append(
            {
                "url": url,
                "input_package": input_package_json,
                "brand_profile": (brand.model_dump() if brand else None),
                "product_knowledge": (product.model_dump() if product else None),
            }
        )

        summary_rows.append(
            {
                "site": url.replace("https://", ""),
                "tokens": input_package_json["css_token_count"],
                "word_count": input_package_json["scrape_word_count"],
                "has_og": "YES" if input_package_json["has_og_image"] else "NO",
                "design_category": brand.design_category if brand else "ERROR",
                "tone": brand.tone if brand else "ERROR",
                "product_category": product.product_category if product else "ERROR",
                "proof_points": len(product.proof_points) if product else 0,
            }
        )

    out_path = Path("e:/genate-ai/test_data/input_layer_real_run.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("Site          | tokens | word_count | has_og | design_category    | tone      | product_category      | proof_points")
    print("------------- | ------ | ---------- | ------ | ------------------ | --------- | --------------------- | ------------")
    for row in summary_rows:
        print(
            f"{row['site']:<13} | "
            f"{row['tokens']:>6} | "
            f"{row['word_count']:>10} | "
            f"{row['has_og']:^6} | "
            f"{row['design_category']:<18} | "
            f"{row['tone']:<9} | "
            f"{row['product_category']:<21} | "
            f"{row['proof_points']:>12}"
        )

    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
