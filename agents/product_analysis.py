"""
Step 3: Product Analysis — LLM returns flat JSON; Python builds ProductKnowledge.
"""

from __future__ import annotations

import logging
from typing import Literal
from urllib.parse import urlparse

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.input_package import InputPackage
from schemas.product_knowledge import Feature, ProductKnowledge, ProofPoint
from agents._utils import parse_json_object, utc_now_iso

logger = logging.getLogger(__name__)

_ProductCategory = Literal[
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
]


def _mock_product(pkg: InputPackage) -> ProductKnowledge:
    pname = _host_name(pkg.url)
    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        product_name=pname,
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
            Feature(name="Brand analysis", description="Extracts visual + text signals"),
            Feature(name="Content automation", description="Generates platform copy fast"),
        ],
        benefits=["Faster campaign production", "More consistent brand voice"],
        proof_points=[
            ProofPoint(
                text="Used by over 10,000 engineering teams.",
                proof_type="user_count",
                source="scraped_page",
            )
        ],
        pain_points=["Inconsistent messaging", "Manual content creation overhead"],
        messaging_angles=["Speed with consistency"],
        integrations=["Slack", "GitHub"],
        scrape_word_count=pkg.scrape_word_count,
        user_document_filename=pkg.user_document_filename,
        data_source=pkg.data_source,
    )


def _host_name(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].capitalize() or "Product"


def _fallback_description(name: str, text: str) -> str:
    words = text.split()
    snippet = " ".join(words[:60]).strip()
    nw = len(snippet.split())
    if nw >= 20:
        candidate = snippet
    else:
        candidate = f"{name} — description unavailable from source page."
    guard = " Further detail was not present in the extracted source text."
    while len(candidate.split()) < 30:
        candidate += guard
    return candidate.strip()


def _empty_product_knowledge(pkg: InputPackage) -> ProductKnowledge:
    desc = (
        "Not enough source text was available to extract reliable product knowledge. "
        "Upload a richer product brief or ensure the target URL exposes sufficient "
        "marketing copy on the page. Genate needs concrete on-page language to "
        "ground features, benefits, and proof points accurately."
    )
    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        product_name=_host_name(pkg.url),
        product_url=pkg.url,
        tagline=None,
        description=desc,
        product_category="other",
        features=[
            Feature(
                name="Awaiting source content",
                description="Provide more text so Genate can infer real product capabilities.",
            ),
            Feature(
                name="Grounded extraction",
                description="Product facts are only filled when enough page or document text exists.",
            ),
        ],
        benefits=[
            "Clearer messaging once sufficient product copy is supplied",
            "Safer outputs grounded in real positioning text",
        ],
        proof_points=[
            ProofPoint(
                text="No proof points found on source page or user document",
                proof_type="stat",
                source="inferred",
            )
        ],
        pain_points=[
            "Sparse input prevents specific friction identification",
            "Limited copy blocks accurate SaaS positioning analysis",
        ],
        messaging_angles=["Clarity through better source material"],
        target_customer=None,
        integrations=[],
        pricing_mentioned=False,
        pricing_description=None,
        scrape_word_count=pkg.scrape_word_count,
        user_document_filename=pkg.user_document_filename,
        data_source=pkg.data_source,
    )


def _classify_proof_type(text: str) -> str:
    """Classify proof point type from text — never trust LLM."""
    text_lower = text.lower()
    if any(c.isdigit() for c in text) and any(
        w in text_lower
        for w in [
            "%",
            "x faster",
            "teams",
            "users",
            "companies",
            "customers",
            "million",
            "billion",
            "k ",
            "m ",
        ]
    ):
        if any(w in text_lower for w in ["uptime", "sla", "availability"]):
            return "uptime_claim"
        if any(w in text_lower for w in ["integration", "apps", "tools"]):
            return "integration_count"
        if any(
            w in text_lower
            for w in ["users", "teams", "companies", "customers", "developers"]
        ):
            return "user_count"
        return "stat"
    if any(w in text_lower for w in ["g2", "gartner", "forrester"]):
        return "g2_badge"
    if any(w in text_lower for w in ["award", "forbes", "product hunt", "#1", "winner"]):
        return "award"
    words = text.split()
    capitalized = sum(
        1
        for w in words
        if w
        and w[0].isupper()
        and w
        not in ("The", "A", "An", "For", "With", "Used", "By", "And", "Or")
    )
    if capitalized >= 2:
        return "customer_name"
    return "stat"


def _parse_features(raw: list) -> list[Feature]:
    """Convert list of strings to Feature objects."""
    features: list[Feature] = []
    for item in raw:
        if isinstance(item, dict):
            features.append(
                Feature(
                    name=str(item.get("name", item))[:60],
                    description=str(item.get("description", item))[:150],
                )
            )
        elif isinstance(item, str):
            if ":" in item and len(item.split(":", 1)[0]) < 60:
                name, desc = item.split(":", 1)
                features.append(
                    Feature(
                        name=name.strip()[:60],
                        description=desc.strip()[:150],
                    )
                )
            else:
                features.append(
                    Feature(
                        name=item[:60],
                        description=item[:150],
                    )
                )
    return features


def _parse_proof_points(raw: list, source: str) -> list[ProofPoint]:
    """Convert list of strings to ProofPoint objects.

    Drops junk under 3 words. Keeps only rows with at least 5 words (Pydantic).
    """
    proof_points: list[ProofPoint] = []
    for item in raw:
        text = item if isinstance(item, str) else str(item)
        text = text.strip()
        n = len(text.split())
        if n < 3:
            continue
        if n < 5:
            continue
        proof_points.append(
            ProofPoint(
                text=text[:120],
                proof_type=_classify_proof_type(text),
                source=source,
            )
        )
    return proof_points


def _proof_source(pkg: InputPackage) -> Literal["scraped_page", "user_document"]:
    if pkg.data_source == "user_document_only":
        return "user_document"
    return "scraped_page"


def _map_product_category(raw: object) -> _ProductCategory:
    s = str(raw or "").lower()
    if "project" in s:
        return "project-management"
    if any(x in s for x in ("developer", "dev", "tool")):
        return "developer-tool"
    if any(x in s for x in ("finance", "fintech", "payment")):
        return "fintech-saas"
    if any(x in s for x in ("hr", "people", "recruit")):
        return "hr-people"
    if any(x in s for x in ("data", "analytics", "bi")):
        return "data-analytics"
    if any(x in s for x in ("customer", "support", "success")):
        return "customer-success"
    if any(x in s for x in ("market", "content", "seo")):
        return "marketing-content"
    if any(x in s for x in ("security", "compliance")):
        return "security-compliance"
    if "vertical-saas" in s or "vertical saas" in s or (
        "vertical" in s and "saas" in s
    ):
        return "vertical-saas"
    return "other"


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        t = x.strip()
        if not t:
            continue
        k = t.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def _dedupe_features(features: list[Feature]) -> list[Feature]:
    seen: set[str] = set()
    out: list[Feature] = []
    for f in features:
        k = f.name.strip().casefold()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


def _dedupe_proof_points(points: list[ProofPoint]) -> list[ProofPoint]:
    seen: set[str] = set()
    out: list[ProofPoint] = []
    for p in points:
        k = p.text.strip().casefold()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def _normalize_integrations_list(raw: object) -> list[str]:
    """Match ProductKnowledge.integrations coercion, then dedupe."""
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            for key in ("name", "title", "label", "value", "id"):
                if key in item and isinstance(item[key], str) and item[key].strip():
                    result.append(item[key].strip())
                    break
            else:
                for val in item.values():
                    if isinstance(val, str) and val.strip():
                        result.append(val.strip())
                        break
    return _dedupe_strings(result)


def _coerce_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _langfuse_log_low_scrape(pkg: InputPackage) -> None:
    if pkg.scrape_word_count >= 100:
        return
    pk, sk = settings.LANGFUSE_PUBLIC_KEY, settings.LANGFUSE_SECRET_KEY
    if not (pk and sk):
        return
    try:
        from langfuse import Langfuse

        Langfuse(public_key=pk, secret_key=sk).trace(
            name="product_analysis_low_scrape_word_count",
            metadata={
                "run_id": pkg.run_id,
                "url": pkg.url,
                "scrape_word_count": pkg.scrape_word_count,
                "data_source": pkg.data_source,
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("LangFuse logging failed", exc_info=True)


def run(input_package: InputPackage) -> ProductKnowledge:
    pkg = input_package
    if settings.MOCK_MODE:
        return _mock_product(pkg)

    text = pkg.get_primary_text()
    if len(text.strip()) < 50:
        return _empty_product_knowledge(pkg)

    doc_raw = (pkg.user_document or "").strip()
    doc_block = doc_raw[:6000] if doc_raw else "none provided"
    scraped_text = (pkg.scraped_text or "")[:6000]

    user_content = (
        "---\n"
        f"PRIMARY SOURCE (user document):\n{doc_block}\n\n"
        f"SUPPLEMENTARY SOURCE (scraped website):\n{scraped_text}\n\n"
        "Extract product information from the above.\n"
        "Return only valid JSON. No markdown. No explanation.\n"
        "---"
    )

    spec = load_prompt("product_analysis_v1")
    raw = chat_completion(
        [
            {"role": "system", "content": spec.system_prompt},
            {"role": "user", "content": user_content},
        ]
    )
    data = parse_json_object(raw)

    product_name = str(data.get("product_name") or "").strip() or _host_name(pkg.url)
    tagline = data.get("tagline")
    tagline = None if tagline is None else str(tagline).strip() or None

    description = str(data.get("description") or "").strip()
    if len(description.split()) < 30:
        description = _fallback_description(product_name, text[:6000])

    features = _parse_features(data.get("features") if isinstance(data.get("features"), list) else [])
    features = _dedupe_features(features)
    while len(features) < 2:
        i = len(features) + 1
        features.append(
            Feature(
                name=f"{product_name} capability {i}"[:60],
                description=(
                    f"{product_name} delivers structured workflows for planning, execution, "
                    "and delivery based on the source material provided."
                )[:150],
            )
        )
    features = features[:10]

    benefits_raw = data.get("benefits") if isinstance(data.get("benefits"), list) else []
    benefits = _dedupe_strings([str(x).strip() for x in benefits_raw if str(x).strip()])
    while len(benefits) < 2:
        if len(features) > len(benefits):
            f = features[len(benefits)]
            benefits.append(f"Helps teams with {f.name.lower()}")
        else:
            break
    benefits = benefits[:8]

    proof_source = _proof_source(pkg)
    proofs = _parse_proof_points(
        data.get("proof_points") if isinstance(data.get("proof_points"), list) else [],
        proof_source,
    )
    proofs = _dedupe_proof_points(proofs)
    if not proofs:
        proofs = [
            ProofPoint(
                text="No proof points found on source page or user document",
                proof_type="stat",
                source="inferred",
            )
        ]

    pains_raw = data.get("pain_points") if isinstance(data.get("pain_points"), list) else []
    pains = _dedupe_strings([str(x).strip() for x in pains_raw if str(x).strip()])
    while len(pains) < 2:
        break
    pains = pains[:8]

    angles_raw = (
        data.get("messaging_angles") if isinstance(data.get("messaging_angles"), list) else []
    )
    angles = _dedupe_strings([str(x).strip() for x in angles_raw if str(x).strip()])
    if not angles:
        angles = []
    angles = angles[:5]

    category = _map_product_category(data.get("product_category"))

    integrations_raw = (
        data.get("integrations") if isinstance(data.get("integrations"), list) else []
    )
    integrations_final = _normalize_integrations_list(integrations_raw)

    knowledge = ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        product_name=product_name,
        product_url=pkg.url,
        tagline=tagline,
        description=description,
        product_category=category,
        features=features,
        benefits=benefits,
        proof_points=proofs,
        pain_points=pains,
        messaging_angles=angles,
        target_customer=(
            None
            if data.get("target_customer") is None
            else str(data.get("target_customer") or "").strip() or None
        ),
        integrations=integrations_final,
        pricing_mentioned=_coerce_bool(data.get("pricing_mentioned")),
        pricing_description=(
            None
            if data.get("pricing_description") is None
            else str(data.get("pricing_description") or "").strip() or None
        ),
        scrape_word_count=pkg.scrape_word_count,
        user_document_filename=pkg.user_document_filename,
        data_source=pkg.data_source,
    )

    _langfuse_log_low_scrape(pkg)
    return knowledge
