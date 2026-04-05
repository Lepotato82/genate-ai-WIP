"""
Tests for the content_type toggle feature:
  - GenerateRequest validation (api.py)
  - planner.run() force_content_type in mock mode
  - planner.run() force_content_type in real LLM mode
  - pipeline SSE final event contains formatted_content + evaluator_output
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agents import planner
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import Feature, ProductKnowledge, ProofPoint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_mock_mode():
    old = settings.MOCK_MODE
    yield
    settings.MOCK_MODE = old


def _writing_instruction() -> str:
    return (
        "Direct technical voice with short sentences and concrete verbs "
        "observed from the minimal spacing rhythm and high contrast hierarchy "
        "without corporate filler or exclamation marks in this sample block."
    )


def _brand() -> BrandProfile:
    return BrandProfile(
        run_id="run-toggle-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        design_category="minimal-saas",
        primary_color="#111111",
        tone="minimal",
        writing_instruction=_writing_instruction(),
        confidence=0.85,
    )


def _product() -> ProductKnowledge:
    proof = ProofPoint(
        text="Teams report forty percent faster review cycles after rollout today",
        proof_type="stat",
        source="scraped_page",
    )
    desc = (
        "This product helps teams ship faster with fewer meetings and clearer ownership "
        "across engineering design and go to market without losing context in tools. "
        "It connects roadmap intent to daily execution so leaders see progress without "
        "chasing status updates in chat threads or spreadsheets every afternoon."
    )
    return ProductKnowledge(
        run_id="run-toggle-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        product_name="TestCo",
        product_url="https://example.com",
        tagline="Ship calmer",
        description=desc,
        product_category="developer-tool",
        features=[
            Feature(name="F1", description="Does one thing well for the user in product."),
            Feature(name="F2", description="Does another thing well for the user here."),
        ],
        benefits=["Faster shipping", "Less thrash"],
        proof_points=[proof],
        pain_points=["Context switching"],
        messaging_angles=["Speed with clarity"],
    )


# ---------------------------------------------------------------------------
# GenerateRequest validation
# ---------------------------------------------------------------------------

class TestGenerateRequestValidation:
    """api.py GenerateRequest validates content_type against platform."""

    def _make_request(self, **kwargs):
        from api import GenerateRequest
        return GenerateRequest(**kwargs)

    def test_no_content_type_always_valid(self):
        req = self._make_request(url="https://x.com", platform="linkedin")
        assert req.content_type is None

    def test_valid_linkedin_content_type(self):
        req = self._make_request(url="https://x.com", platform="linkedin", content_type="carousel")
        assert req.content_type == "carousel"

    def test_valid_twitter_content_type_thread(self):
        req = self._make_request(url="https://x.com", platform="twitter", content_type="thread")
        assert req.content_type == "thread"

    def test_valid_twitter_content_type_single_tweet(self):
        req = self._make_request(url="https://x.com", platform="twitter", content_type="single_tweet")
        assert req.content_type == "single_tweet"

    def test_valid_twitter_content_type_poll(self):
        req = self._make_request(url="https://x.com", platform="twitter", content_type="poll")
        assert req.content_type == "poll"

    def test_invalid_content_type_for_platform_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="not valid for platform"):
            self._make_request(url="https://x.com", platform="twitter", content_type="carousel")

    def test_linkedin_type_rejected_for_twitter(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_request(url="https://x.com", platform="twitter", content_type="text_post")

    def test_valid_instagram_story(self):
        req = self._make_request(url="https://x.com", platform="instagram", content_type="story")
        assert req.content_type == "story"

    def test_valid_blog_content_type(self):
        req = self._make_request(url="https://x.com", platform="blog", content_type="how_to")
        assert req.content_type == "how_to"


# ---------------------------------------------------------------------------
# planner.run() — mock mode force_content_type
# ---------------------------------------------------------------------------

class TestPlannerMockForceContentType:
    def test_force_linkedin_poll(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "linkedin", force_content_type="poll")
        assert brief.content_type == "poll"
        assert brief.slide_count_target is None
        assert brief.thread_length_target is None

    def test_force_linkedin_carousel_sets_slide_count(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "linkedin", force_content_type="carousel")
        assert brief.content_type == "carousel"
        assert brief.slide_count_target == 8

    def test_force_twitter_thread_sets_thread_length(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "twitter", force_content_type="thread")
        assert brief.content_type == "thread"
        assert brief.thread_length_target == 5

    def test_force_twitter_single_tweet(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "twitter", force_content_type="single_tweet")
        assert brief.content_type == "single_tweet"
        assert brief.thread_length_target is None

    def test_force_instagram_story(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "instagram", force_content_type="story")
        assert brief.content_type == "story"
        assert brief.slide_count_target is None

    def test_no_force_uses_planner_default(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "twitter")
        assert brief.content_type == "thread"

    def test_forced_brief_is_valid_content_brief(self):
        settings.MOCK_MODE = True
        brief = planner.run(_brand(), _product(), "linkedin", force_content_type="question_post")
        assert isinstance(brief, ContentBrief)
        assert brief.platform == "linkedin"


# ---------------------------------------------------------------------------
# planner.run() — real LLM mode force_content_type
# ---------------------------------------------------------------------------

class TestPlannerRealModeForceContentType:
    def _llm_response(self, content_type: str = "carousel") -> str:
        return json.dumps({
            "content_type": content_type,
            "narrative_arc": "pain-agitate-solve-cta",
            "content_pillar": "education_and_insight",
            "funnel_stage": "tofu",
            "slide_count_target": 8,
            "thread_length_target": 5,
            "reasoning": f"Selected {content_type} based on signals.",
            "benchmark_reference": "Test benchmark.",
            "posting_strategy": {
                "recommended_frequency": "3x weekly",
                "best_days": ["Tuesday"],
                "best_time_window": "10:00-12:00 IST",
            },
        })

    def test_llm_returns_carousel_force_overrides_to_text_post(self):
        settings.MOCK_MODE = False
        with patch("agents.planner.chat_completion", return_value=self._llm_response("carousel")):
            brief = planner.run(_brand(), _product(), "linkedin", force_content_type="text_post")
        assert brief.content_type == "text_post"
        assert brief.slide_count_target is None

    def test_llm_returns_thread_force_overrides_to_single_tweet(self):
        settings.MOCK_MODE = False
        with patch("agents.planner.chat_completion", return_value=self._llm_response("thread")):
            brief = planner.run(_brand(), _product(), "twitter", force_content_type="single_tweet")
        assert brief.content_type == "single_tweet"
        assert brief.thread_length_target is None

    def test_llm_path_force_carousel_sets_slide_count(self):
        settings.MOCK_MODE = False
        with patch("agents.planner.chat_completion", return_value=self._llm_response("text_post")):
            brief = planner.run(_brand(), _product(), "linkedin", force_content_type="carousel")
        assert brief.content_type == "carousel"
        assert brief.slide_count_target is not None

    def test_llm_path_no_force_respects_llm_choice(self):
        # Use award proof (has_strong_stat=False) so _apply_linkedin_post_rules won't coerce text_post
        desc = (
            "This product helps teams ship faster with fewer meetings and clearer ownership "
            "across engineering design and go to market without losing context in tools. "
            "It connects roadmap intent to daily execution so leaders see progress without "
            "chasing status updates in chat threads or spreadsheets every afternoon."
        )
        product_no_stat = ProductKnowledge(
            run_id="run-toggle-test",
            org_id=None,
            created_at="2026-01-01T00:00:00Z",
            product_name="TestCo",
            product_url="https://example.com",
            tagline="Ship calmer",
            description=desc,
            product_category="developer-tool",
            features=[
                Feature(name="F1", description="Does one thing well for the user in product."),
                Feature(name="F2", description="Does another thing well for the user here."),
            ],
            benefits=["Faster shipping", "Less thrash"],
            proof_points=[ProofPoint(
                text="Recognised in the annual industry awards programme last season",
                proof_type="award",
                source="scraped_page",
            )],
            pain_points=["Context switching"],
            messaging_angles=["Speed with clarity"],
        )
        settings.MOCK_MODE = False
        with patch("agents.planner.chat_completion", return_value=self._llm_response("text_post")):
            brief = planner.run(_brand(), product_no_stat, "linkedin")
        assert brief.content_type == "text_post"


# ---------------------------------------------------------------------------
# Pipeline SSE final event contains formatted_content + evaluator_output
# ---------------------------------------------------------------------------

class TestPipelineFinalEventPayload:
    def test_final_event_includes_formatted_content_and_evaluator(self):
        settings.MOCK_MODE = True
        from pipeline import run_stream
        events = list(run_stream(url="https://example.com", platform="linkedin"))
        final = events[-1]
        assert final["agent"] == "pipeline"
        assert final["status"] == "complete"
        assert "run_id" in final
        assert "formatted_content" in final
        assert "evaluator_output" in final
        fc = final["formatted_content"]
        assert "platform" in fc
        eo = final["evaluator_output"]
        assert "overall_score" in eo
        assert "passes" in eo

    def test_final_event_force_content_type_reflected_in_formatted(self):
        settings.MOCK_MODE = True
        from pipeline import run_stream
        events = list(run_stream(
            url="https://example.com",
            platform="twitter",
            force_content_type="single_tweet",
        ))
        final = events[-1]
        fc = final["formatted_content"]
        assert fc["platform"] == "twitter"
        assert fc["twitter_content"] is not None
        assert len(fc["twitter_content"]["tweets"]) == 1
