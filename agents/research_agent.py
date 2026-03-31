"""
Research Agent — Step 3.5 (sequential after Product Analysis).

Searches Tavily for third-party industry research relevant to
the brand's product category and pain points. Extracts real
statistics from fetched content. Returns ResearchProofPoint
objects to augment ProductKnowledge.

CRITICAL: This agent extracts statistics from real sources.
It never generates or invents statistics. The LLM reads
fetched content and identifies existing stats — it does not
create new claims. Every stat is validated against the source
snippet before being stored.

Gated by RESEARCH_AUGMENTATION_ENABLED=false.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from agents._utils import parse_json_object
from config import settings
from llm.client import chat_completion
from schemas.product_knowledge import ProductKnowledge
from schemas.research_proof_point import ResearchProofPoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source credibility classification
# ---------------------------------------------------------------------------

_TIER_1_SOURCES = [
    "gartner", "forrester", "mckinsey", "deloitte", "accenture",
    "pwc", "bain", "bcg", "harvard", "mit", "stanford",
    "nature", "science", "arxiv", "pubmed", "ieee",
]

_TIER_2_SOURCES = [
    "hubspot", "salesforce", "linkedin", "statista", "emarketer",
    "idc", "nielsen", "pew", "gallup", "edelman",
    "techcrunch", "venturebeat", "wired", "mit technology review",
]


def _classify_credibility(source_url: str, source_name: str) -> str:
    combined = (source_url + source_name).lower()
    if any(s in combined for s in _TIER_1_SOURCES):
        return "tier_1"
    if any(s in combined for s in _TIER_2_SOURCES):
        return "tier_2"
    return "tier_3"


# ---------------------------------------------------------------------------
# URL normalisation for deduplication
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """
    Strip query params and fragments before deduplication.
    Prevents Tavily tracking params (srsltid=, utm_source=, etc.)
    from causing the same page to be processed twice.

    https://statista.com/topics/871/?srsltid=abc → https://statista.com/topics/871
    """
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return url


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------

# Category-specific query overrides — sharper than generic fallback.
# Keys must match values returned by product_analysis.product_category.
_CATEGORY_QUERY_OVERRIDES: dict[str, list[str]] = {
    "marketing-content": [
        "generative engine optimization brand visibility statistics 2025",
        "AI chatbot brand citations research Gartner Forrester 2025",
        "AI search engine brand discovery marketing research report",
    ],
    "data-analytics": [
        "business intelligence data analytics adoption statistics 2025",
        "data driven decision making enterprise research Gartner 2025",
        "analytics platform ROI statistics survey report",
    ],
    "developer-tool": [
        "developer productivity tools adoption statistics 2025",
        "software development workflow research report",
        "engineering team tooling survey GitHub Stack Overflow 2025",
    ],
    "fintech-saas": [
        "SaaS billing subscription management statistics 2025",
        "payment failure recovery dunning research report",
        "subscription revenue churn statistics Recurly Baremetrics",
    ],
    "hr-tech": [
        "HR software adoption statistics 2025 Gartner",
        "employee experience platform research report",
        "workforce management automation survey",
    ],
    "customer-support": [
        "customer support automation statistics 2025",
        "CRM adoption enterprise research Salesforce Gartner",
        "customer experience ROI statistics report",
    ],
}


def _build_queries(product: ProductKnowledge) -> list[str]:
    """
    Build up to 3 targeted Tavily search queries from ProductKnowledge.

    Q1 — Category-level industry stat: what is the market doing?
    Q2 — Pain point validation: research proving the pain is real.
    Q3 — Buyer behaviour: how do buyers in this space behave?
    """
    category = (product.product_category or "SaaS").lower().strip()

    # Use category-specific overrides when available — much sharper than generic
    if category in _CATEGORY_QUERY_OVERRIDES:
        return _CATEGORY_QUERY_OVERRIDES[category]

    # Generic fallback
    pain = product.pain_points[0] if product.pain_points else ""
    target = product.target_customer or "B2B software teams"

    queries = [
        f"{category} market statistics trends research 2024 2025",
        (
            f"{pain[:60]} industry data research report"
            if pain
            else f"{category} challenges problems survey 2024"
        ),
        f"{target} {category} adoption statistics research",
    ]

    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            deduped.append(q)

    return deduped


# ---------------------------------------------------------------------------
# Tavily search
# ---------------------------------------------------------------------------

def _search_tavily(query: str) -> list[dict]:
    """Run a Tavily search. Returns empty list on any failure."""
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=settings.TAVILY_MAX_RESULTS,
            include_raw_content=False,
        )
        results = response.get("results", [])
        logger.info("[research_agent] query '%s' → %d results", query[:50], len(results))
        return results
    except Exception as exc:
        logger.error("[research_agent] Tavily search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Stat extraction from a single result
# ---------------------------------------------------------------------------

_VALID_PROOF_TYPES = {"industry_stat", "survey_finding", "academic", "report", "news_stat"}
_PROOF_TYPE_MAP = {
    "research_finding": "survey_finding",
    "research_stat": "industry_stat",
    "study": "academic",
    "whitepaper": "report",
    "blog": "news_stat",
    "article": "news_stat",
    "data": "industry_stat",
    "finding": "survey_finding",
}


def _normalize_proof_type(raw: str | None) -> str:
    if not raw:
        return "industry_stat"
    v = raw.lower().strip()
    if v in _VALID_PROOF_TYPES:
        return v
    return _PROOF_TYPE_MAP.get(v, "industry_stat")


_EXTRACTION_SYSTEM = """You extract statistics from research content.

RULES — read carefully before responding:
1. Extract ONE specific statistic, percentage, or data point from the content.
2. The stat must appear in the content — do not invent or infer anything.
3. The stat must be specific: "67% of B2B buyers" not "most buyers".
4. If no specific stat exists in the content, return null for stat.
5. Return ONLY valid JSON. No markdown. No preamble.

JSON format:
{
  "stat": "exact stat text from content, or null if none found",
  "source_name": "publication or organization name",
  "publication_year": 2024,
  "relevance_reason": "one sentence why this matters for the product",
  "proof_type": "industry_stat|survey_finding|academic|report|news_stat"
}"""


def _extract_stat_from_result(
    result: dict,
    product: ProductKnowledge,
) -> ResearchProofPoint | None:
    """
    Ask the LLM to identify one statistic in a Tavily result snippet.
    Validates the stat appears in the source before returning.
    Returns None if no qualifying stat is found.
    """
    content = result.get("content", "").strip()
    url = result.get("url", "")
    title = result.get("title", "")

    if not content or len(content) < 50:
        return None

    user_message = (
        f"Product category: {product.product_category}\n"
        f"Product pain points: {', '.join(product.pain_points[:2])}\n\n"
        f"Source title: {title}\n"
        f"Source URL: {url}\n\n"
        f"Content to extract from:\n{content[:800]}\n\n"
        "Extract one specific statistic from this content that is "
        "relevant to the product category or pain points above. "
        "Return null for stat if no specific statistic exists."
    )

    try:
        raw = chat_completion([
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {"role": "user", "content": user_message},
        ])

        data = parse_json_object(raw)
        if not data or not data.get("stat"):
            return None

        stat_text = str(data["stat"]).strip()

        # Validation: stat must be traceable to source content.
        # Short stats (< 3 words): require literal substring match.
        # Longer stats: require ≥ 3 of first 6 words present in content.
        content_lower = content.lower()
        stat_words = stat_text.lower().split()

        if len(stat_words) < 3:
            valid = stat_text.lower() in content_lower
        else:
            words_found = sum(1 for w in stat_words[:6] if w in content_lower)
            valid = words_found >= 3

        if not valid:
            logger.warning(
                "[research_agent] stat validation failed — '%s' not found in source",
                stat_text[:50],
            )
            return None

        return ResearchProofPoint(
            text=stat_text,
            source_name=data.get("source_name") or title[:50],
            source_url=url,
            publication_year=data.get("publication_year"),
            relevance_reason=data.get("relevance_reason") or "",
            proof_type=_normalize_proof_type(data.get("proof_type")),
            credibility_tier=_classify_credibility(url, title),
            source_content_snippet=content[:400],
        )

    except Exception as exc:
        logger.error("[research_agent] extraction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock_result(product: ProductKnowledge) -> list[ResearchProofPoint]:
    return [
        ResearchProofPoint(
            text="67% of B2B buyers consult AI search engines before contacting a vendor.",
            source_name="Gartner (mock)",
            source_url="https://gartner.com/mock",
            publication_year=2024,
            relevance_reason="Validates the AI search visibility pain point.",
            proof_type="report",
            credibility_tier="tier_1",
            source_content_snippet="mock content",
        )
    ]


# ---------------------------------------------------------------------------
# Public run()
# ---------------------------------------------------------------------------

def run(product: ProductKnowledge) -> list[ResearchProofPoint]:
    """
    Search for third-party research relevant to the product and extract
    real statistics. Returns a list of ResearchProofPoint objects.

    Returns empty list when:
      - MOCK_MODE=true (returns deterministic mock instead)
      - RESEARCH_AUGMENTATION_ENABLED=false
      - TAVILY_API_KEY not set
      - No qualifying stats found in search results

    Never raises — all failures return empty list.
    """
    if settings.MOCK_MODE:
        return _mock_result(product)

    if not settings.RESEARCH_AUGMENTATION_ENABLED:
        logger.info("[research_agent] RESEARCH_AUGMENTATION_ENABLED=false — skipping")
        return []

    if not settings.TAVILY_API_KEY:
        logger.warning("[research_agent] TAVILY_API_KEY not set — skipping")
        return []

    queries = _build_queries(product)
    all_points: list[ResearchProofPoint] = []
    seen_urls: set[str] = set()

    for query in queries:
        results = _search_tavily(query)

        for result in results:
            url = result.get("url", "")
            normalized = _normalize_url(url)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)

            point = _extract_stat_from_result(result, product)
            if point:
                all_points.append(point)
                logger.info(
                    "[research_agent] extracted: '%s' from %s (%s)",
                    point.text[:60],
                    point.source_name,
                    point.credibility_tier,
                )

            if len(all_points) >= settings.TAVILY_MAX_PROOF_POINTS:
                break

        if len(all_points) >= settings.TAVILY_MAX_PROOF_POINTS:
            break

    # Sort by credibility — tier_1 first
    all_points.sort(key=lambda p: p.credibility_tier)

    logger.info("[research_agent] found %d research proof points", len(all_points))
    return all_points
