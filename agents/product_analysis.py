"""
Step 3: Product Analysis.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from schemas.input_package import InputPackage
from schemas.product_knowledge import ProductKnowledge
from agents._utils import parse_json_object, utc_now_iso


def _mock_product(pkg: InputPackage) -> ProductKnowledge:
    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        product_name="Genate Target Product",
        product_url=pkg.url,
        tagline="Built for SaaS growth teams.",
        description=(
            "This product helps SaaS teams create consistent marketing assets using "
            "structured workflows, reusable brand context, and fast execution loops. "
            "Teams can analyze brand signals, build strategy briefs, and generate "
            "content that stays aligned with proof points and positioning."
        ),
        product_category="marketing-content",
        features=[
            {"name": "Brand analysis", "description": "Extracts visual + text signals"},
            {"name": "Content automation", "description": "Generates platform copy fast"},
        ],
        benefits=["Faster campaign production", "More consistent brand voice"],
        proof_points=[
            {
                "text": "Used by over 10,000 engineering teams.",
                "proof_type": "user_count",
                "source": "scraped_page",
            }
        ],
        pain_points=["Inconsistent messaging", "Manual content creation overhead"],
        messaging_angles=["Speed with consistency"],
        integrations=["Slack", "GitHub"],
        scrape_word_count=pkg.scrape_word_count,
        data_source=pkg.data_source,
    )


def run(pkg: InputPackage) -> ProductKnowledge:
    if settings.MOCK_MODE:
        return _mock_product(pkg)

    prompt = (
        "Extract structured product knowledge. Return JSON only with ProductKnowledge "
        "fields excluding run_id/org_id/created_at."
    )
    raw = chat_completion(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": pkg.get_primary_text()[:16000]},
        ]
    )
    data = parse_json_object(raw)
    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        scrape_word_count=pkg.scrape_word_count,
        data_source=pkg.data_source,
        product_url=pkg.url,
        **data,
    )
