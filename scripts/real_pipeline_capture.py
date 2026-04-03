"""
Run the full Genate pipeline (no Bannerbear) against real URLs; write JSON + logo to test_data/.

Usage (from repo root, with API keys in env / .env):
  uv run python scripts/real_pipeline_capture.py
  uv run python scripts/real_pipeline_capture.py https://searchable.com

Forces MOCK_MODE=false and IMAGE_GENERATION_ENABLED=false before importing settings.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths + env — before config import
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["MOCK_MODE"] = "false"
os.environ["IMAGE_GENERATION_ENABLED"] = "false"

from agents import (  # noqa: E402
    copywriter,
    evaluator,
    formatter,
    image_gen,
    input_processor,
    planner,
    product_analysis,
    research_agent,
    strategy,
    ui_analyzer,
    visual_gen,
)
from config import settings  # noqa: E402
from pipeline import MAX_EVAL_RETRIES, build_brand_identity, _norm_platform  # noqa: E402

DEFAULT_URLS = [
    "https://lemonhealth.ai",
    "https://searchable.com",
]


def _host_key(url: str) -> str:
    netloc = urlparse(url).netloc or "unknown"
    return netloc.replace(":", "_")


def _input_package_jsonable(pkg):
    d = pkg.model_dump(
        exclude={
            "screenshot_bytes",
            "logo_bytes",
            "og_image_bytes",
            "user_image",
        }
    )
    d["screenshot_bytes_len"] = len(pkg.screenshot_bytes or b"")
    d["logo_bytes_len"] = len(pkg.logo_bytes or b"")
    d["og_image_bytes_len"] = len(pkg.og_image_bytes or b"")
    d["user_image_len"] = len(pkg.user_image or b"")
    return d


def run_one(url: str, out_dir: Path) -> dict:
    """Mirror pipeline._run_entry: one scrape, full agents, image_gen disabled via settings."""
    rid = str(uuid.uuid4())
    plat = _norm_platform("linkedin")

    pkg = input_processor.run(url=url, run_id=rid, org_id=None)
    brand = ui_analyzer.run(pkg)
    product = product_analysis.run(pkg)

    research_points = research_agent.run(product)
    product.research_proof_points = research_points

    brand_identity = build_brand_identity(pkg, brand, product)
    brief = planner.run(brand, product, platform=plat)
    strategy_brief = strategy.run(brief, product, brand)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_copy = pool.submit(
            copywriter.run,
            strategy_brief,
            brief,
            brand,
            research_proof_points=product.research_proof_points or [],
        )
        f_visual = pool.submit(
            visual_gen.run,
            strategy_brief,
            brand,
            brief,
            brand_identity,
        )
        raw_copy = f_copy.result()
        visual_out = f_visual.result()
    formatted = formatter.run(
        raw_copy,
        brief,
        strategy_brief,
        brand,
        revision_hint=None,
        retry_count=0,
        product_knowledge=product,
    )
    images = image_gen.run(formatted, brand_identity, visual=visual_out)

    evaluation = None
    for attempt in range(MAX_EVAL_RETRIES + 1):
        evaluation = evaluator.run(formatted, strategy_brief, brand, retry_count=attempt)
        if evaluation.passes or attempt == MAX_EVAL_RETRIES:
            break
        formatted = formatter.run(
            raw_copy,
            brief,
            strategy_brief,
            brand,
            revision_hint=evaluation.revision_hint,
            retry_count=attempt + 1,
            product_knowledge=product,
        )

    assert evaluation is not None

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "run_id": rid,
        "settings": {
            "MOCK_MODE": settings.MOCK_MODE,
            "IMAGE_GENERATION_ENABLED": settings.IMAGE_GENERATION_ENABLED,
            "HERO_IMAGE_ENABLED": settings.HERO_IMAGE_ENABLED,
            "HERO_IMAGE_PROVIDER": settings.HERO_IMAGE_PROVIDER,
            "RESEARCH_AUGMENTATION_ENABLED": settings.RESEARCH_AUGMENTATION_ENABLED,
            "LLM_PROVIDER": settings.LLM_PROVIDER,
        },
        "input_package": _input_package_jsonable(pkg),
        "brand_profile": brand.model_dump(),
        "brand_identity": brand_identity.model_dump(exclude={"logo_bytes", "og_image_bytes"}),
        "product_knowledge": product.model_dump(),
        "content_brief": brief.model_dump(),
        "strategy_brief": strategy_brief.model_dump(),
        "visual": visual_out,
        "raw_copy": raw_copy,
        "formatted_content": formatted.model_dump(),
        "evaluation": evaluation.model_dump(),
        "passes": evaluation.passes,
        "overall_score": evaluation.overall_score,
        "images": images,
        "research_proof_points": [
            {
                "text": p.text,
                "source_name": p.source_name,
                "source_url": p.source_url,
                "publication_year": p.publication_year,
                "credibility_tier": p.credibility_tier,
                "proof_type": p.proof_type,
                "relevance_reason": p.relevance_reason,
            }
            for p in research_points
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    host = _host_key(url)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"pipeline_real_{host}_{ts}.json"
    logo_path = out_dir / f"logo_{host}.png"
    if pkg.logo_bytes:
        logo_path.write_bytes(pkg.logo_bytes)
    payload["_artifact_paths"] = {
        "json": str(json_path.relative_to(ROOT)),
        "logo": str(logo_path.relative_to(ROOT)) if pkg.logo_bytes else None,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


def main() -> None:
    urls = [u.strip() for u in sys.argv[1:] if u.strip()] or DEFAULT_URLS
    out_dir = ROOT / "test_data"
    for url in urls:
        print(f"=== Pipeline capture: {url}", flush=True)
        try:
            run_one(url, out_dir)
            print(f"OK: wrote under test_data/ for {_host_key(url)}", flush=True)
        except Exception as exc:
            print(f"FAIL {url}: {exc}", flush=True)
            raise


if __name__ == "__main__":
    main()
