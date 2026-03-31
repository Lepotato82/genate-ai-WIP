"""Tests for agents/research_agent.py — Research Augmentation Step 3.5."""

from __future__ import annotations

import pytest

from agents import research_agent
from agents.research_agent import (
    _build_queries,
    _classify_credibility,
    _extract_stat_from_result,
    _normalize_proof_type,
    _normalize_url,
)
from config import settings
from schemas.research_proof_point import ResearchProofPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_product(**kwargs):
    """Return a minimal ProductKnowledge-like object for testing."""
    from schemas.product_knowledge import ProductKnowledge, ProofPoint
    defaults = dict(
        run_id="test-run",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        product_name="TestProduct",
        product_url="https://example.com",
        description=(
            "A SaaS tool for marketing teams that improves search visibility "
            "and helps brands track their AI search presence across platforms. "
            "Built for B2B companies who need proof their content is working."
        ),
        product_category="marketing-content",
        features=[
            {"name": "AI tracking", "description": "Tracks brand mentions in AI results"},
            {"name": "Analytics", "description": "Provides visibility metrics"},
        ],
        benefits=["Save time", "Improve visibility"],
        proof_points=[
            ProofPoint(text="206% share of voice improvement", proof_type="stat", source="scraped_page"),
        ],
        pain_points=["Teams spend hours manually checking AI search results"],
        messaging_angles=["AI search visibility for SaaS"],
        target_customer="Marketing managers at B2B SaaS companies",
    )
    defaults.update(kwargs)
    return ProductKnowledge(**defaults)


@pytest.fixture(autouse=True)
def _restore_settings():
    old_mock = settings.MOCK_MODE
    old_enabled = settings.RESEARCH_AUGMENTATION_ENABLED
    old_key = settings.TAVILY_API_KEY
    yield
    settings.MOCK_MODE = old_mock
    settings.RESEARCH_AUGMENTATION_ENABLED = old_enabled
    settings.TAVILY_API_KEY = old_key


# ---------------------------------------------------------------------------
# run() — gating
# ---------------------------------------------------------------------------

def test_run_returns_empty_when_disabled():
    settings.MOCK_MODE = False
    settings.RESEARCH_AUGMENTATION_ENABLED = False
    product = _make_product()
    result = research_agent.run(product)
    assert result == []


def test_run_returns_empty_when_api_key_missing():
    settings.MOCK_MODE = False
    settings.RESEARCH_AUGMENTATION_ENABLED = True
    settings.TAVILY_API_KEY = ""
    product = _make_product()
    result = research_agent.run(product)
    assert result == []


def test_run_returns_mock_result_in_mock_mode():
    settings.MOCK_MODE = True
    product = _make_product()
    result = research_agent.run(product)
    assert len(result) == 1
    assert isinstance(result[0], ResearchProofPoint)
    assert result[0].credibility_tier == "tier_1"
    assert result[0].source_url.startswith("http")


# ---------------------------------------------------------------------------
# _build_queries
# ---------------------------------------------------------------------------

def test_build_queries_returns_three_from_full_product():
    product = _make_product()
    queries = _build_queries(product)
    assert len(queries) == 3


def test_build_queries_returns_queries_when_pain_points_empty():
    product = _make_product(pain_points=[])
    queries = _build_queries(product)
    assert len(queries) >= 2
    assert all(isinstance(q, str) and len(q) > 0 for q in queries)


def test_build_queries_deduplicates():
    # Force identical pain_points and target_customer to collide
    product = _make_product(
        pain_points=["marketing-content"],
        target_customer="marketing-content",
        product_category="marketing-content",
    )
    queries = _build_queries(product)
    assert len(queries) == len(set(queries))


# ---------------------------------------------------------------------------
# _classify_credibility
# ---------------------------------------------------------------------------

def test_classify_credibility_tier_1_gartner():
    assert _classify_credibility("https://gartner.com/report", "Gartner") == "tier_1"


def test_classify_credibility_tier_1_mckinsey():
    assert _classify_credibility("https://mckinsey.com/insights", "McKinsey") == "tier_1"


def test_classify_credibility_tier_2_hubspot():
    assert _classify_credibility("https://hubspot.com/research", "HubSpot") == "tier_2"


def test_classify_credibility_tier_3_unknown():
    assert _classify_credibility("https://some-unknown-blog.io/post", "Random Blog") == "tier_3"


# ---------------------------------------------------------------------------
# _extract_stat_from_result
# ---------------------------------------------------------------------------

def test_extract_stat_returns_none_for_short_content():
    product = _make_product()
    result = {"content": "Too short.", "url": "https://example.com", "title": "Test"}
    assert _extract_stat_from_result(result, product) is None


def test_extract_stat_returns_none_when_llm_returns_null_stat(monkeypatch):
    """LLM returns a null stat — agent should return None."""
    settings.MOCK_MODE = False

    def _fake_chat(_messages, **_kw):
        return '{"stat": null, "source_name": "Test", "publication_year": 2024, "relevance_reason": "test", "proof_type": "industry_stat"}'

    monkeypatch.setattr(research_agent, "chat_completion", _fake_chat)
    monkeypatch.setattr(research_agent, "parse_json_object",
                        lambda raw: {"stat": None, "source_name": "Test",
                                     "publication_year": 2024, "relevance_reason": "test",
                                     "proof_type": "industry_stat"})

    product = _make_product()
    result = {
        "content": "x " * 60,
        "url": "https://example.com",
        "title": "Test",
    }
    assert _extract_stat_from_result(result, product) is None


def test_extract_stat_validation_rejects_fabricated_stat(monkeypatch):
    """Stat words not found in source content → fabrication prevention → None."""
    settings.MOCK_MODE = False

    fabricated = "99% of enterprise teams fail to measure ROI"
    content = "This article discusses general productivity trends in software."

    monkeypatch.setattr(research_agent, "chat_completion", lambda *a, **kw: "{}")
    monkeypatch.setattr(research_agent, "parse_json_object",
                        lambda raw: {
                            "stat": fabricated,
                            "source_name": "Test",
                            "publication_year": 2024,
                            "relevance_reason": "test",
                            "proof_type": "industry_stat",
                        })

    product = _make_product()
    result = {"content": content, "url": "https://example.com", "title": "Test"}
    assert _extract_stat_from_result(result, product) is None


# ---------------------------------------------------------------------------
# ResearchProofPoint schema validators
# ---------------------------------------------------------------------------

def test_research_proof_point_rejects_short_text():
    with pytest.raises(Exception):
        ResearchProofPoint(
            text="short",
            source_name="Test",
            source_url="https://example.com",
            relevance_reason="test",
            proof_type="industry_stat",
        )


def test_research_proof_point_rejects_url_without_scheme():
    with pytest.raises(Exception):
        ResearchProofPoint(
            text="67% of B2B buyers consult AI before contacting a vendor.",
            source_name="Test",
            source_url="example.com/no-scheme",
            relevance_reason="test",
            proof_type="industry_stat",
        )


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

def test_research_proof_points_key_in_pipeline_output():
    settings.MOCK_MODE = True
    from pipeline import _run_entry
    result = _run_entry("https://example.com", "linkedin", "test-run-rpp", None)
    assert "research_proof_points" in result
    assert isinstance(result["research_proof_points"], list)


def test_source_content_snippet_not_in_pipeline_output():
    settings.MOCK_MODE = True
    from pipeline import _run_entry
    result = _run_entry("https://example.com", "linkedin", "test-run-snip", None)
    rpp = result["research_proof_points"]
    for point in rpp:
        assert "source_content_snippet" not in point


def test_research_proof_points_sorted_tier_1_first():
    points = [
        ResearchProofPoint(
            text="Tier 3 stat from a blog with some content.",
            source_name="Random Blog",
            source_url="https://randomblog.io",
            relevance_reason="test",
            proof_type="news_stat",
            credibility_tier="tier_3",
        ),
        ResearchProofPoint(
            text="Gartner found 67% of B2B buyers consult AI first.",
            source_name="Gartner",
            source_url="https://gartner.com",
            relevance_reason="test",
            proof_type="report",
            credibility_tier="tier_1",
        ),
        ResearchProofPoint(
            text="HubSpot survey found 45% of teams lack visibility tools.",
            source_name="HubSpot",
            source_url="https://hubspot.com",
            relevance_reason="test",
            proof_type="survey_finding",
            credibility_tier="tier_2",
        ),
    ]
    sorted_points = sorted(points, key=lambda p: p.credibility_tier)
    assert sorted_points[0].credibility_tier == "tier_1"
    assert sorted_points[1].credibility_tier == "tier_2"
    assert sorted_points[2].credibility_tier == "tier_3"


# ---------------------------------------------------------------------------
# _normalize_proof_type
# ---------------------------------------------------------------------------

def test_normalize_proof_type_valid_passthrough():
    assert _normalize_proof_type("industry_stat") == "industry_stat"
    assert _normalize_proof_type("survey_finding") == "survey_finding"
    assert _normalize_proof_type("academic") == "academic"
    assert _normalize_proof_type("report") == "report"
    assert _normalize_proof_type("news_stat") == "news_stat"


def test_normalize_proof_type_known_alias():
    assert _normalize_proof_type("research_finding") == "survey_finding"
    assert _normalize_proof_type("study") == "academic"
    assert _normalize_proof_type("whitepaper") == "report"


def test_normalize_proof_type_unknown_defaults_to_industry_stat():
    assert _normalize_proof_type("something_weird") == "industry_stat"
    assert _normalize_proof_type(None) == "industry_stat"
    assert _normalize_proof_type("") == "industry_stat"


# ---------------------------------------------------------------------------
# _normalize_url — tracking param stripping for dedup
# ---------------------------------------------------------------------------

def test_normalize_url_strips_srsltid():
    url = "https://statista.com/topics/871/online-shopping/?srsltid=AfmBOoq2C7A0"
    assert _normalize_url(url) == "https://statista.com/topics/871/online-shopping"


def test_normalize_url_strips_utm_source():
    url = "https://example.com/article?utm_source=google&utm_medium=cpc"
    assert _normalize_url(url) == "https://example.com/article"


def test_normalize_url_leaves_path_intact():
    url = "https://gartner.com/research/ai-search-trends/report-2025"
    assert _normalize_url(url) == "https://gartner.com/research/ai-search-trends/report-2025"


def test_normalize_url_no_query_params_unchanged():
    url = "https://forrester.com/blogs/ai-visibility"
    assert _normalize_url(url) == "https://forrester.com/blogs/ai-visibility"


def test_normalize_url_deduplicates_statista_tracking_variants():
    """Two Statista URLs differing only in srsltid → same normalized URL → deduplicated."""
    url_a = "https://statista.com/topics/871/?srsltid=AfmBOoq2C7A0"
    url_b = "https://statista.com/topics/871/?srsltid=AfmBOooa2Pr6tX08"
    assert _normalize_url(url_a) == _normalize_url(url_b)


# ---------------------------------------------------------------------------
# _build_queries — category overrides
# ---------------------------------------------------------------------------

def _make_product_for_category(category: str) -> "ProductKnowledge":
    from schemas.product_knowledge import ProductKnowledge, Feature, ProofPoint
    return ProductKnowledge(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        product_name="TestCo",
        product_url="https://example.com",
        tagline="Test tagline",
        description=(
            "TestCo is a software product that helps teams solve complex daily problems "
            "efficiently with modern workflows and intelligent automation capabilities "
            "designed for enterprise and mid-market teams operating at scale globally."
        ),
        product_category=category,
        features=[
            Feature(name="Feature A", description="Does the main thing well."),
            Feature(name="Feature B", description="Handles the secondary case."),
        ],
        benefits=["Saves time", "Reduces cost"],
        proof_points=[
            ProofPoint(
                text="Teams report measurable improvements after implementation.",
                proof_type="stat",
                source="scraped_page",
            )
        ],
        pain_points=["Manual processes are slow", "No visibility into metrics"],
        messaging_angles=["Speed", "Insight"],
        target_customer="B2B teams",
        icp_description="Mid-market software companies",
    )


def test_build_queries_uses_category_override_for_marketing_content():
    product = _make_product_for_category("marketing-content")
    queries = _build_queries(product)
    assert any("generative engine optimization" in q for q in queries)


def test_build_queries_uses_category_override_for_developer_tool():
    product = _make_product_for_category("developer-tool")
    queries = _build_queries(product)
    assert any("developer productivity" in q for q in queries)


def test_build_queries_marketing_content_returns_ai_search_specific_queries():
    """Queries for marketing-content must mention AI/chatbot/brand visibility."""
    product = _make_product_for_category("marketing-content")
    queries = _build_queries(product)
    combined = " ".join(queries).lower()
    assert "brand" in combined or "ai" in combined or "chatbot" in combined


def test_build_queries_falls_back_to_generic_for_unmapped_category():
    """other category (not in overrides) → generic fallback query construction."""
    product = _make_product_for_category("other")
    queries = _build_queries(product)
    # Generic fallback: pain point or category term appears in query
    combined = " ".join(queries).lower()
    assert "other" in combined or "manual" in combined or "b2b" in combined
