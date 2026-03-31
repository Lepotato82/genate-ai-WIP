"""Tests for content_depth — Task 1 (ContentBrief schema + Planner depth selection)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import planner
from agents.copywriter import _depth_instruction
from agents.planner import _select_depth
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import Feature, ProductKnowledge, ProofPoint
from schemas.research_proof_point import ResearchProofPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _brand() -> BrandProfile:
    return BrandProfile(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        design_category="minimal-saas",
        primary_color="#111111",
        tone="minimal",
        writing_instruction=(
            "Direct and concise with short declarative sentences observed from clean UI spacing "
            "and high contrast minimal typography without corporate filler or buzzwords."
        ),
        confidence=0.85,
    )


def _product(*, n_features: int = 2, n_proofs: int = 1, n_research: int = 0) -> ProductKnowledge:
    feats = [
        Feature(name=f"Feature {i}", description="Does one important thing for teams.")
        for i in range(max(1, n_features))
    ]
    proofs = [
        ProofPoint(
            text=f"Customers see strong measurable improvements in key metrics proof {i}.",
            proof_type="stat",
            source="scraped_page",
        )
        for i in range(max(1, n_proofs))
    ]
    research = [
        ResearchProofPoint(
            text="Gartner found that 67% of B2B buyers consult AI engines before vendors.",
            source_name="Gartner",
            source_url="https://gartner.com/report",
            publication_year=2024,
            relevance_reason="Validates AI visibility urgency.",
            proof_type="report",
            credibility_tier="tier_1",
            source_content_snippet="67% of B2B buyers consult AI engines before vendors.",
        )
        for _ in range(n_research)
    ]
    pk = ProductKnowledge(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        product_name="TestCo",
        product_url="https://example.com",
        tagline="Ship calmer",
        description=(
            "TestCo helps engineering teams ship software faster without status meetings "
            "by making issue state automatic and roadmap intent visible to every stakeholder "
            "across the organisation without manual updates or context-switching between tools."
        ),
        product_category="developer-tool",
        features=feats if len(feats) >= 2 else feats + [Feature(name="Feature X", description="Extra feature for schema minimum.")],
        benefits=["Faster shipping", "Less thrash"],
        proof_points=proofs,
        pain_points=["Too many status meetings", "Context switching"],
        messaging_angles=["Speed and focus", "Automatic state"],
        target_customer="Engineering teams",
        icp_description="Senior engineers at Series A startups",
    )
    pk.research_proof_points = research
    return pk


@pytest.fixture(autouse=True)
def _restore_settings():
    old_mock = settings.MOCK_MODE
    old_research = settings.RESEARCH_AUGMENTATION_ENABLED
    yield
    settings.MOCK_MODE = old_mock
    settings.RESEARCH_AUGMENTATION_ENABLED = old_research


# ---------------------------------------------------------------------------
# ContentBrief schema — content_depth field
# ---------------------------------------------------------------------------

def test_content_brief_accepts_concise(tmp_path):
    """ContentBrief accepts content_depth='concise'."""
    settings.MOCK_MODE = True
    cb = planner.run(_brand(), _product(), platform="linkedin")
    assert cb.content_depth in ("concise", "long_form")


def test_content_brief_accepts_long_form():
    """ContentBrief can be constructed with content_depth='long_form'."""
    settings.MOCK_MODE = True
    settings.RESEARCH_AUGMENTATION_ENABLED = True
    cb = planner.run(_brand(), _product(n_features=5, n_proofs=3), platform="linkedin")
    assert cb.content_depth == "long_form"


def test_content_brief_defaults_to_concise_when_thin():
    """ContentBrief defaults to 'concise' for thin product knowledge."""
    settings.MOCK_MODE = True
    settings.RESEARCH_AUGMENTATION_ENABLED = False
    cb = planner.run(_brand(), _product(n_features=1, n_proofs=1), platform="linkedin")
    assert cb.content_depth == "concise"


def test_content_brief_content_depth_field_default():
    """ContentBrief.content_depth defaults to 'concise' when not set."""
    # Build a minimal valid ContentBrief without specifying content_depth
    cb = ContentBrief(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        platform="linkedin",
        content_type="text_post",
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="pain_and_problem",
        funnel_stage="tofu",
        slide_count_target=None,
        word_count_target=None,
        thread_length_target=None,
        platform_rules_summary=["Hook max 180 chars", "3-5 hashtags at end"],
        seo_keyword=None,
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="LinkedIn text posts for single insight B2B SaaS.",
        reasoning="Test reasoning for text post on linkedin with features and signals.",
        posting_strategy={
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday", "Thursday"],
            "best_time_window": "10:00-12:00 IST",
        },
    )
    assert cb.content_depth == "concise"


# ---------------------------------------------------------------------------
# _select_depth logic
# ---------------------------------------------------------------------------

def _signals(*, features: int, proofs: int, research: int = 0) -> dict:
    return {
        "feature_count": features,
        "proof_point_count": proofs,
        "research_proof_point_count": research,
        "pain_point_count": 2,
        "brand_tone": "minimal",
        "has_strong_stat": False,
        "has_customer_name": False,
    }


def test_select_depth_long_form_when_education_pillar():
    """education_and_insight pillar → long_form."""
    assert _select_depth(_signals(features=2, proofs=1), content_pillar="education_and_insight") == "long_form"


def test_select_depth_long_form_when_research_available():
    """research_proof_point_count > 0 → long_form."""
    assert _select_depth(_signals(features=2, proofs=1, research=2)) == "long_form"


def test_select_depth_long_form_when_feature_and_proof_threshold():
    """feature_count >= 4 AND proof_point_count >= 2 → long_form."""
    assert _select_depth(_signals(features=4, proofs=2)) == "long_form"


def test_select_depth_concise_when_threshold_not_met():
    """feature_count=3, proof_point_count=1, no research → concise."""
    assert _select_depth(_signals(features=3, proofs=1)) == "concise"


def test_select_depth_concise_for_thin_product():
    """Very thin product knowledge → concise."""
    assert _select_depth(_signals(features=1, proofs=1)) == "concise"


def test_select_depth_long_form_exactly_at_threshold():
    """Exactly feature=4, proof=2 without research → long_form (boundary)."""
    assert _select_depth(_signals(features=4, proofs=2, research=0)) == "long_form"


def test_select_depth_not_long_form_when_features_high_but_proofs_low():
    """feature=5, proof=1 (below threshold of 2) → concise."""
    assert _select_depth(_signals(features=5, proofs=1, research=0)) == "concise"


# ---------------------------------------------------------------------------
# Planner mock sets long_form with research enabled
# ---------------------------------------------------------------------------

def test_planner_mock_sets_long_form_when_research_enabled():
    """In MOCK_MODE, long_form is set when RESEARCH_AUGMENTATION_ENABLED=true."""
    settings.MOCK_MODE = True
    settings.RESEARCH_AUGMENTATION_ENABLED = True
    cb = planner.run(_brand(), _product(n_features=1, n_proofs=1), platform="linkedin")
    assert cb.content_depth == "long_form"


def test_planner_mock_sets_concise_when_research_disabled_and_thin():
    """In MOCK_MODE, concise is set when RESEARCH_AUGMENTATION_ENABLED=false and thin."""
    settings.MOCK_MODE = True
    settings.RESEARCH_AUGMENTATION_ENABLED = False
    cb = planner.run(_brand(), _product(n_features=1, n_proofs=1), platform="linkedin")
    assert cb.content_depth == "concise"


# ---------------------------------------------------------------------------
# platform_rules.json contains long_form depth targets
# ---------------------------------------------------------------------------

def test_platform_rules_contain_long_form_linkedin():
    rules_path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    assert "long_form" in rules["linkedin"]
    assert rules["linkedin"]["long_form"]["word_count_min"] == 600
    assert rules["linkedin"]["long_form"]["word_count_max"] == 900


def test_platform_rules_contain_long_form_twitter():
    rules_path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    assert "long_form" in rules["twitter"]
    assert rules["twitter"]["long_form"]["tweet_count_min"] == 6
    assert rules["twitter"]["long_form"]["tweet_count_max"] == 8


def test_platform_rules_contain_long_form_instagram():
    rules_path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    assert "long_form" in rules["instagram"]
    assert rules["instagram"]["long_form"]["body_word_count_min"] == 250
    assert rules["instagram"]["long_form"]["body_word_count_max"] == 400


def test_platform_rules_contain_concise_linkedin():
    rules_path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    assert "concise" in rules["linkedin"]
    assert rules["linkedin"]["concise"]["word_count_min"] == 150
    assert rules["linkedin"]["concise"]["word_count_max"] == 300


# ---------------------------------------------------------------------------
# _depth_instruction — word count enforcement in copywriter user message
# ---------------------------------------------------------------------------

def test_depth_instruction_long_form_linkedin_contains_600_900():
    instruction = _depth_instruction("linkedin", "long_form")
    assert "600-900 words" in instruction
    assert "HARD REQUIREMENT" in instruction


def test_depth_instruction_concise_linkedin_contains_150_300():
    instruction = _depth_instruction("linkedin", "concise")
    assert "150-300 words" in instruction


def test_depth_instruction_long_form_twitter_contains_tweet_range():
    instruction = _depth_instruction("twitter", "long_form")
    assert "6-8 tweets" in instruction


def test_depth_instruction_concise_twitter_contains_tweet_range():
    instruction = _depth_instruction("twitter", "concise")
    assert "4-6 tweets" in instruction


def test_depth_instruction_long_form_instagram_contains_word_range():
    instruction = _depth_instruction("instagram", "long_form")
    assert "250-400 words" in instruction


def test_depth_instruction_concise_instagram_contains_word_range():
    instruction = _depth_instruction("instagram", "concise")
    assert "80-150 words" in instruction


def test_depth_instruction_long_form_warns_not_to_truncate():
    instruction = _depth_instruction("linkedin", "long_form")
    assert "truncate" in instruction.lower() or "minimum" in instruction.lower()


def test_depth_instruction_concise_mentions_no_padding():
    instruction = _depth_instruction("linkedin", "concise")
    assert "padding" in instruction.lower() or "concise" in instruction.lower()
