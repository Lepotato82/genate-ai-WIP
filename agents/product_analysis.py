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


def _is_placeholder(s: str) -> bool:
    """True if the string is an echoed schema placeholder like '<user outcome 1>'."""
    s = s.strip()
    return s.startswith("<") and s.endswith(">")


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
        if isinstance(item, str):
            # LLM returned plain string instead of object — coerce it
            name = item.strip()[:60]
            if name and not _is_placeholder(name):
                feature_objs.append({"name": name, "description": f"Feature of {normalized['product_name']}."})
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()[:60]
            desc = str(item.get("description") or item.get("desc") or "").strip()[:150]
            if name and not _is_placeholder(name):
                desc = desc or f"Feature of {normalized['product_name']}."
                feature_objs.append({"name": name, "description": desc})
    while len(feature_objs) < 2:
        i = len(feature_objs) + 1
        feature_objs.append(
            {
                "name": f"{normalized['product_name']} capability {i}",
                "description": f"See {normalized['product_name']} website for full feature details.",
            }
        )
    normalized["features"] = feature_objs[:10]

    _BENEFIT_PADS = [
        f"Faster execution across {normalized['product_name']} workflows",
        f"Reduced manual overhead for {normalized['product_name']} users",
    ]
    benefits = normalized.get("benefits")
    if not isinstance(benefits, list):
        benefits = []
    benefits = list(dict.fromkeys(
        str(x).strip() for x in benefits
        if str(x).strip() and not _is_placeholder(str(x).strip())
    ))
    for pad in _BENEFIT_PADS:
        if len(benefits) >= 2:
            break
        if pad not in benefits:
            benefits.append(pad)
    normalized["benefits"] = benefits[:8]

    _VALID_PROOF_TYPES = {
        "stat", "customer_name", "g2_badge", "integration_count",
        "uptime_claim", "award", "user_count",
    }
    proofs = normalized.get("proof_points")
    if not isinstance(proofs, list):
        proofs = []
    proof_objs = []
    for item in proofs:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if len(text.split()) < 5 or _is_placeholder(text):
            continue
        raw_type = str(item.get("proof_type") or "").strip()
        proof_type = raw_type if raw_type in _VALID_PROOF_TYPES else "stat"
        proof_objs.append(
            {
                "text": text[:120],
                "proof_type": proof_type,
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

    _PAIN_PADS = [
        f"Manual coordination overhead before adopting {normalized['product_name']}",
        f"Lack of unified tooling for {normalized['product_name']} use cases",
    ]
    pains = normalized.get("pain_points")
    if not isinstance(pains, list):
        pains = []
    pains = list(dict.fromkeys(
        str(x).strip() for x in pains
        if str(x).strip() and not _is_placeholder(str(x).strip())
    ))
    for pad in _PAIN_PADS:
        if len(pains) >= 2:
            break
        if pad not in pains:
            pains.append(pad)
    normalized["pain_points"] = pains[:8]

    angles = normalized.get("messaging_angles")
    if not isinstance(angles, list):
        angles = []
    angles = list(dict.fromkeys(
        str(x).strip() for x in angles
        if str(x).strip() and not _is_placeholder(str(x).strip())
    ))
    if not angles:
        angles = [f"{normalized['product_name']} as a purpose-built solution for modern teams"]
    normalized["messaging_angles"] = angles[:5]

    return normalized


def run(pkg: InputPackage) -> ProductKnowledge:
    if settings.MOCK_MODE:
        return _mock_product(pkg)

    prompt = (
        "You are a product analyst. The user message contains scraped page text from a "
        "SaaS product website. Extract structured product knowledge and return ONLY a valid "
        "JSON object — no markdown, no explanation, no code fences.\n\n"
        "Required JSON structure:\n"
        "{\n"
        '  "product_name": "string",\n'
        '  "tagline": "verbatim tagline from page or null",\n'
        '  "description": "2-4 sentences describing what the product does, minimum 30 words",\n'
        '  "product_category": "one of: developer-tool (IDE, API, CI/CD, infra) | project-management (issue tracking, sprints, roadmaps) | fintech-saas (payments, banking, accounting) | hr-people (hiring, payroll, performance) | data-analytics (BI, dashboards, data pipelines) | customer-success (CRM, support, helpdesk) | marketing-content (SEO, ads, content creation) | security-compliance (auth, audit, compliance) | vertical-saas (industry-specific SaaS) | other",\n'
        '  "features": [{"name": "<feature name>", "description": "<what it does>"}],\n'
        '  "benefits": ["<user outcome 1>", "<user outcome 2>"],\n'
        '  "proof_points": [{"text": "<verbatim stat or claim>", "proof_type": "stat|customer_name|g2_badge|integration_count|uptime_claim|award|user_count", "source": "scraped_page"}],\n'
        '  "pain_points": ["<pain point 1>", "<pain point 2>"],\n'
        '  "messaging_angles": ["<angle 1>"],\n'
        '  "integrations": ["<integration name>"],\n'
        '  "target_customer": "string describing target customer or null",\n'
        '  "pricing_mentioned": false,\n'
        '  "pricing_description": null\n'
        "}\n\n"
        "Rules:\n"
        "- features, benefits, proof_points, pain_points must each have at least 2 entries if the text supports it\n"
        "- proof_points: only include what is explicitly stated on the page (stats, customer names, integration counts, uptime claims)\n"
        "- Do not invent or infer anything not stated in the text\n"
        "- Return the JSON object only — nothing before or after it"
    )
    user_message = pkg.get_primary_text()[:16000]
    import sys
    sys.stdout.buffer.write(
        (
            f"[product_analysis] sending {len(user_message.split())} words to LLM\n"
            f"[product_analysis] user message preview: {user_message[:300]!r}\n"
        ).encode("utf-8", errors="replace")
    )
    sys.stdout.buffer.flush()
    raw = chat_completion(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
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
