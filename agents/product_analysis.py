"""
Step 3: Product Analysis.
"""

from __future__ import annotations

from urllib.parse import urlparse

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


def _host_name(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].capitalize() or "Product"


def _fallback_description(name: str, text: str) -> str:
    snippet = " ".join(text.split()[:45]).strip()
    base = (
        f"{name} is a SaaS product described on the source page. It helps teams "
        "improve execution speed, reduce operational friction, and align cross-functional "
        "work through clearer workflows and automation. "
    )
    joined = f"{base}Source summary: {snippet}"
    return joined if len(joined.split()) >= 30 else f"{joined} This platform supports day-to-day operations and measurable productivity gains."


def _normalize_product_data(data: dict, pkg: InputPackage) -> dict:
    normalized = dict(data)
    normalized.pop("run_id", None)
    normalized.pop("org_id", None)
    normalized.pop("created_at", None)
    normalized.pop("product_url", None)

    normalized["product_name"] = str(normalized.get("product_name") or _host_name(pkg.url))
    description = str(normalized.get("description") or "").strip()
    if len(description.split()) < 30:
        description = _fallback_description(normalized["product_name"], pkg.get_primary_text())
    normalized["description"] = description

    allowed_categories = {
        "developer-tool",
        "project-management",
        "fintech-saas",
        "hr-people",
        "data-analytics",
        "customer-success",
        "marketing-content",
        "security-compliance",
        "vertical-saas",
        "other",
    }
    category = str(normalized.get("product_category") or "other")
    normalized["product_category"] = category if category in allowed_categories else "other"

    features = normalized.get("features")
    if not isinstance(features, list):
        features = []
    feature_objs = []
    for item in features:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()[:60]
            desc = str(item.get("description") or "").strip()[:150]
            if name and desc:
                feature_objs.append({"name": name, "description": desc})
    while len(feature_objs) < 2:
        i = len(feature_objs) + 1
        feature_objs.append(
            {
                "name": f"Core capability {i}",
                "description": f"{normalized['product_name']} provides structured workflow support for repeated SaaS tasks.",
            }
        )
    normalized["features"] = feature_objs[:10]

    benefits = normalized.get("benefits")
    if not isinstance(benefits, list):
        benefits = []
    benefits = [str(x).strip() for x in benefits if str(x).strip()]
    while len(benefits) < 2:
        benefits.append("Faster execution across product and go-to-market teams")
    normalized["benefits"] = benefits[:8]

    proofs = normalized.get("proof_points")
    if not isinstance(proofs, list):
        proofs = []
    proof_objs = []
    for item in proofs:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if len(text.split()) < 5:
            continue
        proof_objs.append(
            {
                "text": text[:120],
                "proof_type": item.get("proof_type") or "stat",
                "source": item.get("source") or "inferred",
            }
        )
    if not proof_objs:
        proof_objs = [
            {
                "text": "No proof points found on source page or user document",
                "proof_type": "stat",
                "source": "inferred",
            }
        ]
    normalized["proof_points"] = proof_objs

    pains = normalized.get("pain_points")
    if not isinstance(pains, list):
        pains = []
    pains = [str(x).strip() for x in pains if str(x).strip()]
    while len(pains) < 2:
        pains.append("Manual processes create inconsistent outcomes and wasted execution time")
    normalized["pain_points"] = pains[:8]

    angles = normalized.get("messaging_angles")
    if not isinstance(angles, list):
        angles = []
    angles = [str(x).strip() for x in angles if str(x).strip()]
    if not angles:
        angles = ["Operational speed with consistent delivery"]
    normalized["messaging_angles"] = angles[:5]

    return normalized


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
    data = _normalize_product_data(parse_json_object(raw), pkg)
    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        scrape_word_count=pkg.scrape_word_count,
        data_source=pkg.data_source,
        product_url=pkg.url,
        **data,
    )
