"""
Step 3: Product Analysis — LLM returns flat JSON; Python builds ProductKnowledge.
"""

from __future__ import annotations

import logging
import re
import sys
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_PROOF_TYPES = frozenset({
    "stat", "customer_name", "g2_badge", "integration_count",
    "uptime_claim", "award", "user_count",
})

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "developer-tool",
        ["developer", "dev", "api", "ide", "ci/cd", "infra", "infrastructure",
         "deploy", "pipeline", "code", "engineering", "sdk", "cli"],
    ),
    (
        "project-management",
        ["project", "portfolio", "roadmap", "sprint", "kanban", "milestone",
         "issue", "task", "agile", "scrum", "backlog"],
    ),
    (
        "fintech-saas",
        ["fintech", "payment", "banking", "accounting", "finance", "billing",
         "invoice", "ledger", "transaction"],
    ),
    (
        "hr-people",
        ["hr", "people", "recruit", "hiring", "hire", "payroll", "performance",
         "employee", "talent", "workforce", "onboard"],
    ),
    (
        "data-analytics",
        ["analytics", "bi", "dashboard", "intelligence", "visualization",
         "insight", "warehouse", "chart", "report", "metric"],
    ),
    (
        "customer-success",
        ["customer", "support", "success", "helpdesk", "crm", "service",
         "ticket", "client", "retention"],
    ),
    (
        "marketing-content",
        ["marketing", "content", "seo", "growth", "campaign", "email",
         "copywriting", "brand", "ads", "lead"],
    ),
    (
        "security-compliance",
        ["security", "compliance", "audit", "gdpr", "soc", "auth", "identity",
         "access", "permission", "encryption"],
    ),
    (
        "vertical-saas",
        ["vertical", "clinic", "hospital", "legal", "retail", "restaurant",
         "real estate", "construction", "healthcare", "field service"],
    ),
]

_RE_UPTIME = re.compile(r"\buptime\b|\bsla\b", re.I)
_RE_G2 = re.compile(
    r"\bg2\b|gartner|forrester|capterra|getapp|peer\s+insights|magic\s+quadrant",
    re.I,
)
_RE_AWARD = re.compile(
    r"\baward\b|\bwinner\b|cloud\s*100|forbes|inc\s*500|top\s*\d+|named\s+in\b",
    re.I,
)
_RE_COUNT = re.compile(r"\b\d[\d,]*(?:\+|k|m|M|million|thousand|billion)?\b")
_RE_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_RE_INTEGRATION_KW = re.compile(r"\bintegrations?\b|\bconnectors?\b", re.I)
_RE_USER_KW = re.compile(
    r"\busers?\b|\bteams?\b|\bcompan(?:y|ies)\b|\bcustomers?\b|\bclients?\b|\borganization\b",
    re.I,
)

_PROPER_NOUN_STOP = frozenset({
    "Named", "Rated", "Trusted", "Used", "Powered", "Built", "Made", "Based",
    "They", "You", "Your", "We", "Our", "The", "A", "An", "And", "Or", "But",
    "In", "On", "At", "For", "With", "From", "To", "Of", "Is", "Are", "Was",
    "Were", "It", "Its", "By", "Both", "All", "Has", "Have", "Had",
    "This", "That", "These", "Those",
})


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _classify_proof_type(text: str) -> str:
    """Classify a proof-point string into a valid proof_type literal."""
    if _RE_UPTIME.search(text):
        return "uptime_claim"
    if _RE_G2.search(text):
        return "g2_badge"
    if _RE_AWARD.search(text):
        return "award"
    has_count = bool(_RE_COUNT.search(text) or _RE_PERCENT.search(text))
    if not has_count:
        proper = re.findall(r"\b[A-Z][a-z]{1,30}\b", text)
        proper = [p for p in proper if p not in _PROPER_NOUN_STOP]
        if len(proper) >= 2:
            return "customer_name"
    if has_count and _RE_INTEGRATION_KW.search(text):
        return "integration_count"
    if has_count and _RE_USER_KW.search(text):
        return "user_count"
    return "stat"


def _map_product_category(raw: str) -> str:
    """Map raw LLM category text to a valid _ProductCategory literal via keyword scoring."""
    text = raw.lower().strip()
    # Exact match first
    for cat, _ in _CATEGORY_KEYWORDS:
        if text == cat:
            return cat
    best_cat = "other"
    best_score = 0
    for cat, keywords in _CATEGORY_KEYWORDS:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _is_placeholder(s: str) -> bool:
    """True if the string is an echoed schema placeholder like '<user outcome 1>'."""
    s = s.strip()
    return s.startswith("<") and s.endswith(">")


def _parse_features(items: list) -> list[Feature]:
    """Parse a raw list (strings or dicts) into Feature objects."""
    out: list[Feature] = []
    for item in items:
        if isinstance(item, str):
            name = item.strip()[:60]
            if not name or _is_placeholder(name):
                continue
            if ":" in name:
                parts = name.split(":", 1)
                fname = parts[0].strip()[:60]
                fdesc = parts[1].strip()[:150]
                if not fname:
                    fname = name
                    fdesc = name
            else:
                fname = name
                fdesc = name  # no colon → description == name
            out.append(Feature(name=fname, description=fdesc))
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()[:60]
            desc = str(item.get("description") or item.get("desc") or "").strip()[:150]
            if not name or _is_placeholder(name):
                continue
            if not desc:
                desc = f"Feature: {name}."
            out.append(Feature(name=name, description=desc))
    return out


def _parse_proof_points(items: list, source: str) -> list[ProofPoint]:
    """Parse a raw list (strings or dicts) into ProofPoint objects.

    Entries with fewer than 5 words are skipped. Non-string, non-dict items
    are skipped.
    """
    out: list[ProofPoint] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            if len(text.split()) < 5 or _is_placeholder(text):
                continue
            raw_type = str(item.get("proof_type") or "").strip()
            ptype = raw_type if raw_type in _VALID_PROOF_TYPES else _classify_proof_type(text)
            src = str(item.get("source") or source).strip() or source
            out.append(ProofPoint(text=text[:120], proof_type=ptype, source=src))  # type: ignore[arg-type]
        elif isinstance(item, str):
            text = item.strip()
            if len(text.split()) < 5 or _is_placeholder(text):
                continue
            ptype = _classify_proof_type(text)
            out.append(ProofPoint(text=text[:120], proof_type=ptype, source=source))  # type: ignore[arg-type]
    return out


def _proof_source(pkg: InputPackage) -> str:
    """Return the appropriate proof source string for the given InputPackage."""
    if pkg.data_source == "user_document_only":
        return "user_document"
    return "scraped_page"


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _dedupe_strings(items: list[str]) -> list[str]:
    """Deduplicate strings (case-insensitive), preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        k = s.casefold()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _dedupe_features(features: list[Feature]) -> list[Feature]:
    """Deduplicate Feature objects by name.casefold(), preserving first-seen order."""
    seen: set[str] = set()
    out: list[Feature] = []
    for f in features:
        k = f.name.casefold()
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _dedupe_proof_points(proofs: list[ProofPoint]) -> list[ProofPoint]:
    """Deduplicate ProofPoint objects by text.casefold(), preserving first-seen order."""
    seen: set[str] = set()
    out: list[ProofPoint] = []
    for p in proofs:
        k = p.text.casefold()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _normalize_integrations_list(raw: list) -> list[str]:
    """Normalize a list of integration entries (strings or dicts) into a deduplicated string list."""
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("title") or "").strip()
        else:
            name = str(item).strip()
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    return (
        joined
        if len(joined.split()) >= 30
        else f"{joined} This platform supports day-to-day operations and measurable productivity gains."
    )


def _coerce_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ("true", "yes", "1", "y")


# ---------------------------------------------------------------------------
# Mock / fallback
# ---------------------------------------------------------------------------

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


def _short_text_fallback(pkg: InputPackage) -> ProductKnowledge:
    """Return a minimal ProductKnowledge when primary text is too short for LLM analysis."""
    name = _host_name(pkg.url)
    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        product_name=name,
        product_url=pkg.url,
        tagline=None,
        description=_fallback_description(name, ""),
        product_category="other",
        features=[
            Feature(
                name=f"{name} capability 1",
                description=f"See {name} website for full feature details.",
            ),
            Feature(
                name=f"{name} capability 2",
                description=f"See {name} website for full feature details.",
            ),
        ],
        benefits=[
            f"Faster execution across {name} workflows",
            f"Reduced manual overhead for {name} users",
        ],
        proof_points=[
            ProofPoint(
                text="No proof points found on source page or user document",
                proof_type="stat",
                source="inferred",
            )
        ],
        pain_points=[
            f"Manual coordination overhead before adopting {name}",
            f"Lack of unified tooling for {name} use cases",
        ],
        messaging_angles=[f"{name} as a purpose-built solution for modern teams"],
        scrape_word_count=pkg.scrape_word_count,
        user_document_filename=pkg.user_document_filename,
        data_source=pkg.data_source,
    )


# ---------------------------------------------------------------------------
# Data normalization
# ---------------------------------------------------------------------------

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

    raw_category = str(normalized.get("product_category") or "other")
    normalized["product_category"] = _map_product_category(raw_category)

    features_raw = normalized.get("features")
    if not isinstance(features_raw, list):
        features_raw = []
    feature_objs = _parse_features(features_raw)
    feature_objs = _dedupe_features(feature_objs)
    while len(feature_objs) < 2:
        i = len(feature_objs) + 1
        feature_objs.append(
            Feature(
                name=f"{normalized['product_name']} capability {i}",
                description=f"See {normalized['product_name']} website for full feature details.",
            )
        )
    normalized["features"] = feature_objs[:10]

    _BENEFIT_PADS = [
        f"Faster execution across {normalized['product_name']} workflows",
        f"Reduced manual overhead for {normalized['product_name']} users",
    ]
    benefits = normalized.get("benefits")
    if not isinstance(benefits, list):
        benefits = []
    benefits = [
        str(x).strip() for x in benefits
        if str(x).strip() and not _is_placeholder(str(x).strip())
    ]
    benefits = _dedupe_strings(benefits)
    for pad in _BENEFIT_PADS:
        if len(benefits) >= 2:
            break
        if pad not in benefits:
            benefits.append(pad)
    normalized["benefits"] = benefits[:8]

    proofs_raw = normalized.get("proof_points")
    if not isinstance(proofs_raw, list):
        proofs_raw = []
    source = _proof_source(pkg)
    proof_objs = _parse_proof_points(proofs_raw, source)
    proof_objs = _dedupe_proof_points(proof_objs)
    if not proof_objs:
        proof_objs = [
            ProofPoint(
                text="No proof points found on source page or user document",
                proof_type="stat",
                source="inferred",
            )
        ]
    normalized["proof_points"] = proof_objs

    _PAIN_PADS = [
        f"Manual coordination overhead before adopting {normalized['product_name']}",
        f"Lack of unified tooling for {normalized['product_name']} use cases",
    ]
    pains = normalized.get("pain_points")
    if not isinstance(pains, list):
        pains = []
    pains = [
        str(x).strip() for x in pains
        if str(x).strip() and not _is_placeholder(str(x).strip())
    ]
    pains = _dedupe_strings(pains)
    for pad in _PAIN_PADS:
        if len(pains) >= 2:
            break
        if pad not in pains:
            pains.append(pad)
    normalized["pain_points"] = pains[:8]

    angles = normalized.get("messaging_angles")
    if not isinstance(angles, list):
        angles = []
    angles = [
        str(x).strip() for x in angles
        if str(x).strip() and not _is_placeholder(str(x).strip())
    ]
    angles = _dedupe_strings(angles)
    if not angles:
        angles = [f"{normalized['product_name']} as a purpose-built solution for modern teams"]
    normalized["messaging_angles"] = angles[:5]

    return normalized


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a product analyst. The user message contains scraped page text from a "
    "SaaS product website. Extract structured product knowledge and return ONLY a valid "
    "JSON object — no markdown, no explanation, no code fences.\n\n"
    "Required JSON structure:\n"
    "{\n"
    '  "product_name": "string",\n'
    '  "tagline": "verbatim tagline from page or null",\n'
    '  "description": "2-4 sentences describing what the product does, minimum 30 words",\n'
    '  "product_category": "one of: developer-tool | project-management | fintech-saas | '
    "hr-people | data-analytics | customer-success | marketing-content | "
    'security-compliance | vertical-saas | other",\n'
    '  "features": [{"name": "<feature name>", "description": "<what it does>"}],\n'
    '  "benefits": ["<user outcome 1>", "<user outcome 2>"],\n'
    '  "proof_points": [{"text": "<verbatim stat or claim>", "proof_type": '
    '"stat|customer_name|g2_badge|integration_count|uptime_claim|award|user_count", '
    '"source": "scraped_page"}],\n'
    '  "pain_points": ["<pain point 1>", "<pain point 2>"],\n'
    '  "messaging_angles": ["<angle 1>"],\n'
    '  "integrations": ["<integration name>"],\n'
    '  "target_customer": "string describing target customer or null",\n'
    '  "pricing_mentioned": false,\n'
    '  "pricing_description": null\n'
    "}\n\n"
    "Rules:\n"
    "- features, benefits, proof_points, pain_points must each have at least 2 entries "
    "if the text supports it\n"
    "- proof_points: only include what is explicitly stated on the page (stats, customer "
    "names, integration counts, uptime claims)\n"
    "- Do not invent or infer anything not stated in the text\n"
    "- Return the JSON object only — nothing before or after it"
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pkg: InputPackage) -> ProductKnowledge:
    if settings.MOCK_MODE:
        return _mock_product(pkg)

    primary_text = pkg.get_primary_text()
    if len(primary_text.strip()) < 30:
        return _short_text_fallback(pkg)

    user_message = primary_text[:16000]
    sys.stdout.buffer.write(
        (
            f"[product_analysis] sending {len(user_message.split())} words to LLM\n"
            f"[product_analysis] user message preview: {user_message[:300]!r}\n"
        ).encode("utf-8", errors="replace")
    )
    sys.stdout.buffer.flush()

    raw = chat_completion(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )
    data = _normalize_product_data(parse_json_object(raw), pkg)

    # features and proof_points are already typed objects from _normalize_product_data
    features: list[Feature] = data["features"]
    proofs: list[ProofPoint] = data["proof_points"]

    tagline_raw = data.get("tagline")
    tagline_val = None if tagline_raw is None else (str(tagline_raw).strip() or None)

    integrations_raw = data.get("integrations") or []
    if not isinstance(integrations_raw, list):
        integrations_raw = []
    integrations_final = _normalize_integrations_list(integrations_raw)

    return ProductKnowledge(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        product_name=data["product_name"],
        product_url=pkg.url,
        tagline=tagline_val,
        description=data["description"],
        product_category=data["product_category"],  # type: ignore[arg-type]
        features=features,
        benefits=data["benefits"],
        proof_points=proofs,
        pain_points=data["pain_points"],
        messaging_angles=data["messaging_angles"],
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
