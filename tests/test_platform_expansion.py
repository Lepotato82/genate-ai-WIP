"""Platform expansion: LinkedIn / Twitter / Instagram planner, formatter, pipeline, evaluator."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agents import formatter, planner
from agents.evaluator import _apply_engagement_generic_cap, run as evaluator_run
from config import settings
from pipeline import run as pipeline_run
from pipeline import run_instagram, run_twitter
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.formatted_content import (
    FormattedContent,
    InstagramContent,
    LinkedInContent,
    TwitterContent,
)
from schemas.product_knowledge import Feature, ProductKnowledge, ProofPoint
from schemas.strategy_brief import StrategyBrief


@pytest.fixture(autouse=True)
def _restore_mock_mode():
    old = settings.MOCK_MODE
    yield
    settings.MOCK_MODE = old


def _writing_instruction() -> str:
    return (
        "Write in a direct technical voice with short sentences and concrete verbs "
        "observed from the UI including spacing rhythm contrast and hierarchy "
        "without corporate filler or exclamation marks in this sample instruction block."
    )


def _brand() -> BrandProfile:
    return BrandProfile(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        design_category="minimal-saas",
        primary_color="#111111",
        tone="minimal",
        writing_instruction=_writing_instruction(),
        confidence=0.85,
    )


def _product(
    *,
    n_features: int = 2,
    proof_stat: bool = False,
    proof_customer: bool = False,
) -> ProductKnowledge:
    feats = [
        Feature(name=f"Feature {i}", description="Does one thing well for the user in product.")
        for i in range(max(2, n_features))
    ]
    if proof_stat:
        proof = ProofPoint(
            text="Teams report forty percent faster review cycles after rollout today",
            proof_type="stat",
            source="scraped_page",
        )
    elif proof_customer:
        proof = ProofPoint(
            text="Acme Corp and Contoso both rely on this workflow daily here",
            proof_type="customer_name",
            source="scraped_page",
        )
    else:
        proof = ProofPoint(
            text="Recognised in the annual industry awards programme last season",
            proof_type="award",
            source="scraped_page",
        )
    desc = (
        "This product helps teams ship faster with fewer meetings and clearer ownership "
        "across engineering design and go to market without losing context in tools. "
        "It connects roadmap intent to daily execution so leaders see progress without "
        "chasing status updates in chat threads or spreadsheets every afternoon."
    )
    return ProductKnowledge(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        product_name="TestCo",
        product_url="https://example.com",
        tagline="Ship calmer",
        description=desc,
        product_category="developer-tool",
        features=feats[:10],
        benefits=["Faster shipping", "Less thrash"],
        proof_points=[proof],
        pain_points=["Context switching", "Slow reviews"],
        messaging_angles=["Speed with clarity"],
    )


def _brief_twitter() -> ContentBrief:
    return ContentBrief(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        platform="twitter",
        content_type="thread",
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="education_and_insight",
        funnel_stage="tofu",
        posting_strategy={
            "recommended_frequency": "daily",
            "best_days": ["Tuesday"],
            "best_time_window": "09:00-11:00 IST",
        },
        platform_rules_summary=["Rule one for tests.", "Rule two for tests."],
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="Benchmark for tests.",
        reasoning="Twitter thread chosen for tests with signal references feature_count=2.",
        thread_length_target=5,
    )


def _brief_ig() -> ContentBrief:
    return ContentBrief(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        platform="instagram",
        content_type="carousel",
        narrative_arc="before-after-bridge-cta",
        content_pillar="product_and_solution",
        funnel_stage="tofu",
        slide_count_target=8,
        posting_strategy={
            "recommended_frequency": "weekly",
            "best_days": ["Monday"],
            "best_time_window": "18:00 IST",
        },
        platform_rules_summary=["Instagram rule one here.", "Instagram rule two here."],
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="Instagram benchmark for tests.",
        reasoning="Carousel for tests; signals referenced in planner reasoning field.",
    )


def _strategy() -> StrategyBrief:
    return StrategyBrief(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        lead_pain_point=(
            "Slow feedback loops drain momentum every sprint when reviews stall "
            "and nobody owns the next decision on scope or priority clearly."
        ),
        primary_claim="TestCo removes friction from weekly planning cycles.",
        proof_point="Teams report forty percent faster review cycles after rollout today",
        proof_point_type="stat",
        cta_intent="learn_more",
        appeal_type="rational",
        narrative_arc="pain-agitate-solve-cta",
        target_icp_role="Engineering lead",
        differentiator=(
            "Grounded in page truth and extracted signals instead of generic AI fluff "
            "that ignores what the product page actually promises to buyers."
        ),
        hook_direction="Lead with time lost in reviews.",
        positioning_mode="category_creation",
        messaging_angle_used="Speed",
        knowledge_context_applied=False,
    )


def test_run_twitter_mock_returns_twitter_content() -> None:
    settings.MOCK_MODE = True
    out = run_twitter("https://example.com")
    fc = out["formatted_content"]
    assert fc["twitter_content"] is not None
    assert fc["linkedin_content"] is None
    assert fc["instagram_content"] is None


def test_run_instagram_mock_returns_instagram_content() -> None:
    settings.MOCK_MODE = True
    out = run_instagram("https://example.com")
    fc = out["formatted_content"]
    assert fc["instagram_content"] is not None
    assert fc["twitter_content"] is None


def test_twitter_tweet_char_counts_recomputed_not_llm() -> None:
    tweets = [
        "a" * 60 + " word boundary here for standalone tweet one idea",
        "b" * 80,
        "c" * 80,
        "d" * 80 + " final cta",
    ]
    tc = TwitterContent(
        tweets=tweets,
        tweet_char_counts=[1, 1, 1, 999],
        hashtags=["#saas"],
    )
    assert tc.tweet_char_counts == [len(t) for t in tc.tweets]
    assert all(len(t) <= 280 for t in tc.tweets)


def test_twitter_postprocess_all_under_280() -> None:
    raw = "1/ " + "x" * 400 + "\n\n2/ two\n\n3/ three\n\n4/ four"
    tw = formatter._twitter_postprocess_llm(["a"], ["#t"], raw)
    assert 4 <= len(tw.tweets) <= 8
    assert all(len(t) <= 280 for t in tw.tweets)


def test_instagram_preview_and_hashtags_and_newlines() -> None:
    pk = _product(n_features=2)
    ic = formatter._instagram_postprocess(
        "Short preview that fits.",
        "Body line one.\n\nBody line two.",
        ["#onlyone"],
        pk,
    )
    assert len(ic.preview_text) <= 125
    assert 20 <= len(ic.hashtags) <= 30
    assert "\n\n\n\n\n" in ic.full_caption


def test_instagram_schema_validates_five_newlines() -> None:
    tags = [f"#t{i}" for i in range(20)]
    cap = "prev\nbody\n\n\n\n\n" + " ".join(tags)
    InstagramContent(
        preview_text="prev",
        body="body",
        hashtags=tags,
        full_caption=cap,
    )


def test_pipeline_run_dispatches_x_to_twitter() -> None:
    with patch("pipeline.run_twitter", return_value={"ok": True}) as m:
        r = pipeline_run("https://x.com", platform="x")
        m.assert_called_once()
        assert r == {"ok": True}


def test_pipeline_run_invalid_platform() -> None:
    with pytest.raises(ValueError, match="Unsupported platform"):
        pipeline_run("https://a.com", platform="invalid")


def test_planner_linkedin_downgrades_carousel_to_text_post() -> None:
    settings.MOCK_MODE = False
    llm = json.dumps(
        {
            "content_type": "carousel",
            "narrative_arc": "pain-agitate-solve-cta",
            "content_pillar": "pain_and_problem",
            "funnel_stage": "tofu",
            "slide_count_target": 8,
            "reasoning": "x",
            "benchmark_reference": "b",
        }
    )
    with patch("agents.planner.chat_completion", return_value=llm):
        b = _brand()
        p = _product(n_features=2, proof_stat=False, proof_customer=False)
        brief = planner.run(b, p, platform="linkedin")
    assert brief.content_type == "text_post"


def test_planner_linkedin_strong_stat_prefers_single_image() -> None:
    settings.MOCK_MODE = False
    llm = json.dumps(
        {
            "content_type": "carousel",
            "narrative_arc": "pain-agitate-solve-cta",
            "content_pillar": "pain_and_problem",
            "funnel_stage": "tofu",
            "slide_count_target": 8,
            "reasoning": "x",
            "benchmark_reference": "b",
        }
    )
    with patch("agents.planner.chat_completion", return_value=llm):
        b = _brand()
        p = _product(n_features=2, proof_stat=True)
        brief = planner.run(b, p, platform="linkedin")
    assert brief.content_type == "single_image"


def test_planner_twitter_allows_single_tweet() -> None:
    """single_tweet is now a valid Twitter content type and passes through unchanged."""
    settings.MOCK_MODE = False
    llm = json.dumps(
        {
            "content_type": "single_tweet",
            "narrative_arc": "pain-agitate-solve-cta",
            "content_pillar": "pain_and_problem",
            "funnel_stage": "tofu",
            "reasoning": "concise TOFU hook for cold audience",
            "benchmark_reference": "b",
        }
    )
    with patch("agents.planner.chat_completion", return_value=llm):
        brief = planner.run(_brand(), _product(), platform="twitter")
    assert brief.content_type == "single_tweet"
    assert brief.thread_length_target is None


def test_planner_twitter_forces_thread_for_unknown_type() -> None:
    """Unknown Twitter content types are coerced to thread."""
    settings.MOCK_MODE = False
    llm = json.dumps(
        {
            "content_type": "carousel",  # invalid for Twitter
            "narrative_arc": "pain-agitate-solve-cta",
            "content_pillar": "pain_and_problem",
            "funnel_stage": "tofu",
            "thread_length_target": 5,
            "reasoning": "coercion test",
            "benchmark_reference": "b",
        }
    )
    with patch("agents.planner.chat_completion", return_value=llm):
        brief = planner.run(_brand(), _product(), platform="twitter")
    assert brief.content_type == "thread"
    assert brief.thread_length_target is not None


def test_evaluator_caps_generic_discover_hook() -> None:
    assert _apply_engagement_generic_cap("Discover how we ship faster.\n\nMore.", 5) == 3
    llm = json.dumps(
        {
            "clarity": 4,
            "engagement": 5,
            "tone_match": 4,
            "accuracy": 4,
            "clarity_reason": "Structure is readable. Sentences stay short.",
            "engagement_reason": "Hook attempts curiosity. Payoff arrives quickly.",
            "tone_match_reason": "Voice stays neutral. No hype adjectives appear.",
            "accuracy_reason": "Claims map to proof. No invented statistics appear.",
        }
    )
    settings.MOCK_MODE = False
    hook = "Discover how your team can fix the daily standup tax in one week flat."
    fc = FormattedContent(
        run_id="r",
        org_id=None,
        created_at="t",
        platform="linkedin",
        linkedin_content=LinkedInContent(
            hook=hook[:180],
            body=hook,
            hashtags=["#a", "#b", "#c"],
            full_post=f"{hook}\n\nMore\n\n#a #b #c",
        ),
    )
    with patch("agents.evaluator.chat_completion", return_value=llm):
        ev = evaluator_run(fc, _strategy(), _brand(), retry_count=0)
    assert ev.engagement <= 3
