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
from urllib.parse import urlparse, urlunparse

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
    Strip query params and fragments; lowercase scheme and host for dedup.
    Prevents Tavily tracking params (srsltid=, utm_source=, etc.)
    from causing the same page to be processed twice.

    https://statista.com/topics/871/?srsltid=abc → https://statista.com/topics/871
    """
    try:
        p = urlparse(url.strip())
        scheme = (p.scheme or "http").lower()
        netloc = p.netloc.lower()
        path = (p.path or "").rstrip("/")
        return urlunparse((scheme, netloc, path, "", "", "")).rstrip("/")
    except Exception:
        return url


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------

# Category-specific query overrides — sharper than generic fallback.
# Keys must match values returned by product_analysis.product_category.
_CATEGORY_QUERY_OVERRIDES: dict[str, list[str]] = {
    "marketing-content": [
        "generative engine optimization brand visibility B2B statistics 2026",
        "AI chatbot brand citations research Gartner Forrester 2026",
        "AI search engine brand discovery B2B market research report 2026",
    ],
    "data-analytics": [
        "business intelligence data analytics B2B adoption statistics 2026",
        "data driven decision making enterprise research Gartner 2026",
        "analytics platform ROI B2B statistics market research survey 2026",
    ],
    "developer-tool": [
        "developer productivity tools B2B adoption statistics 2026",
        "software development workflow market research report 2026",
        "engineering team tooling survey GitHub Stack Overflow B2B 2026",
    ],
    "fintech-saas": [
        "SaaS billing subscription management B2B statistics 2026",
        "payment failure recovery dunning market research report",
        "subscription revenue churn statistics Recurly Baremetrics B2B survey",
    ],
    "hr-tech": [
        "HR software B2B adoption statistics 2026 Gartner",
        "employee experience platform market research report 2026",
        "workforce management automation B2B industry survey 2026",
    ],
    "customer-support": [
        "customer support automation B2B statistics 2026",
        "CRM adoption enterprise research Salesforce Gartner 2026",
        "customer experience ROI B2B market research report 2026",
    ],
    "health-wellness": [
        "consumer health app adoption wellness behavior statistics 2026 survey",
        "mobile health app engagement personal health research report 2026",
        "digital health consumer trends Pew Research CDC survey 2025 2026",
    ],
}

# Pain-first query tails — avoid defaulting every query to B2B + category.
_NEUTRAL_RESEARCH_TAIL = "statistics survey research findings report 2025 2026"
_ALT_RESEARCH_TAIL = "survey data prevalence study research report 2025 2026"


def _is_likely_b2c(product: ProductKnowledge) -> bool:
    """
    Heuristic from scraped text only (no new schema).
    When true, category anchor queries skip forced 'B2B' wording.
    """
    blob = " ".join(
        filter(
            None,
            [
                (product.target_customer or ""),
                (product.tagline or ""),
                product.description or "",
            ],
        )
    ).lower()
    hints = (
        "consumer",
        "b2c",
        "patient",
        "patients",
        "mobile app",
        "app users",
        "wellness",
        "personal health",
        "google play",
        "app store",
        "everyday user",
        "individual user",
        "end user",
        "health app",
        "fitness app",
    )
    return any(h in blob for h in hints)


def _trim_query_fragment(text: str, max_len: int = 90) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut if cut else text[:max_len]


def _pain_led_query(fragment: str, tail: str = _NEUTRAL_RESEARCH_TAIL) -> str:
    frag = _trim_query_fragment(fragment, 90)
    return f"{frag} {tail}".strip() if frag else tail


def _first_pain_query(product: ProductKnowledge) -> str:
    pains = product.pain_points or []
    if pains:
        return _pain_led_query(pains[0])
    if product.tagline:
        return _pain_led_query(product.tagline)
    desc = (product.description or "").strip()
    if desc:
        return _pain_led_query(desc[:120])
    return _pain_led_query(product.product_name)


def _second_pain_query(product: ProductKnowledge) -> str:
    pains = product.pain_points or []
    if len(pains) >= 2:
        return _pain_led_query(pains[1], _ALT_RESEARCH_TAIL)
    if len(pains) == 1:
        desc = (product.description or "").strip()
        if len(desc) > 80:
            mid = desc[40 : 40 + 120]
            return _pain_led_query(mid, _ALT_RESEARCH_TAIL)
        return _pain_led_query(pains[0], _ALT_RESEARCH_TAIL)
    if product.tagline and (product.description or "").strip():
        desc = (product.description or "").strip()
        start = min(50, max(0, len(desc) // 3))
        return _pain_led_query(desc[start : start + 100], _ALT_RESEARCH_TAIL)
    if product.benefits:
        return _pain_led_query(product.benefits[0], _ALT_RESEARCH_TAIL)
    desc = (product.description or "").strip()
    if len(desc) > 100:
        return _pain_led_query(desc[90:200], _ALT_RESEARCH_TAIL)
    return _pain_led_query(
        f"{product.product_name} user challenges",
        _ALT_RESEARCH_TAIL,
    )


def _category_anchor_query(
    product: ProductKnowledge,
    category: str,
    override_first: str | None,
) -> str:
    if override_first:
        return override_first.strip()
    cat = category or "saas"
    target = _trim_query_fragment(product.target_customer or "", 50)
    b2c = _is_likely_b2c(product)
    if b2c:
        parts = [
            f"{cat} consumer market research statistics 2026 industry report",
        ]
        if target:
            parts.append(target)
        return " ".join(parts).strip()
    parts = [f"{cat} B2B market statistics 2026 market research report"]
    if target:
        parts.append(target)
    return " ".join(parts).strip()


def _build_queries(product: ProductKnowledge) -> list[str]:
    """
    Build 3 Tavily queries: 2 pain/context-led, 1 category/industry anchor.

    Pain-first (~2/3) avoids miscategorized B2C products (e.g. wellness apps
    tagged vertical-saas) pulling only generic B2B SaaS corpus. Category
    overrides supply the third query's anchor when mapped.
    """
    category = (product.product_category or "SaaS").lower().strip()

    q1 = _first_pain_query(product)
    q2 = _second_pain_query(product)

    override_row = _CATEGORY_QUERY_OVERRIDES.get(category)
    override_first = override_row[0].strip() if override_row else None
    q3 = _category_anchor_query(product, category, override_first)

    queries = [q1, q2, q3]

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
3. The stat must be specific: "67% of B2B buyers consult AI before contacting a vendor" not "most buyers".
4. The JSON "stat" value must be the full sentence or clause copied from the content that contains
   the figure — at least 10 characters and at least 3 words. Never return only the naked number
   (e.g. reject "54%", "20", "5% and 8%" alone).
5. The stat must DIRECTLY describe user behavior, user struggle, or a measurable outcome related
   to one of the listed pain points. Being in the same broad topic area is NOT sufficient —
   the stat must speak to the specific friction or outcome named in the pain points.
6. Reject methodology and sample-size lines. Examples that must return null:
   "Base: 12,000 adults; U.S.=4,000...", "n=500", "Sample: 2,000 respondents", or any line
   that is a list of country/region sample counts. These are footnotes, not usable claims.
7. The stat must be a grammatically complete sentence or clause that starts with a capital letter.
   Fragments that begin mid-thought without a subject (e.g. "be extremely or very worried...",
   "the time spent by individuals...") must return null.
8. If no qualifying stat exists, return null for stat.
9. Return ONLY valid JSON. No markdown. No preamble.

JSON format (use null for stat when no qualifying statistic exists):
{
  "stat": "67% of B2B buyers consult AI search engines before contacting a vendor.",
  "source_name": "publication or organization name",
  "publication_year": 2024,
  "relevance_reason": "one sentence naming which specific pain point this stat directly quantifies",
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
        "Extract one specific statistic from this content that DIRECTLY quantifies one of the "
        "pain points listed above — not just a stat in the same broad topic. "
        "Return the full source sentence starting with a capital letter (min 10 chars, at least 3 words). "
        "Return null for stat if no directly relevant statistic exists, or if the content only "
        "contains methodology notes, sample size lines, or fragments without a subject."
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

        # Guard 1: reject methodology/sample-size lines (e.g. "Base: 12,000 adults; ...")
        _METHODOLOGY_PREFIXES = ("base:", "n=", "n =", "sample:", "sample size:", "respondents:")
        if stat_text.lower().startswith(_METHODOLOGY_PREFIXES):
            logger.warning("[research_agent] rejected methodology line: '%s'", stat_text[:60])
            return None

        # Guard 2: reject fragments — a usable stat must start with a capital letter
        if stat_text and stat_text[0].islower():
            logger.warning("[research_agent] rejected lowercase fragment: '%s'", stat_text[:60])
            return None

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
