"""
Tests for the 5 new content types:
  - Twitter single_tweet
  - Twitter poll
  - LinkedIn poll
  - LinkedIn question_post
  - Instagram story

Covers: schema validators, formatter parse helpers, formatter mock dispatch.
"""

from __future__ import annotations

import pytest

from agents import formatter
from agents.formatter import _parse_poll_copy, _parse_story_copy, _build_poll
from config import settings
from schemas.content_brief import ContentBrief
from schemas.formatted_content import (
    FormattedContent,
    InstagramStoryContent,
    PollContent,
    TwitterContent,
)
from schemas.strategy_brief import StrategyBrief
from schemas.brand_profile import BrandProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_mode_on(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_MODE", True)


def _strategy() -> StrategyBrief:
    return StrategyBrief(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        lead_pain_point="Engineers spend hours every day chasing deployment status updates in Slack instead of shipping code",
        primary_claim="TestCo removes deploy noise with one dashboard so engineers can ship faster.",
        proof_point="Teams cut deployment status queries by sixty percent within the first week of using the product",
        proof_point_type="stat",
        cta_intent="start_trial",
        appeal_type="rational",
        narrative_arc="pain-agitate-solve-cta",
        target_icp_role="Engineering lead",
        differentiator="Only tool that surfaces live deploy context directly inside your IDE with no extra browser tabs",
        hook_direction="Open with the specific Slack interruption pattern engineers dread during active development sprints",
        positioning_mode="category_creation",
        messaging_angle_used="Deploy visibility without the noise",
        knowledge_context_applied=False,
    )


def _brand() -> BrandProfile:
    return BrandProfile(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        design_category="minimal-saas",
        primary_color="#111111",
        tone="minimal",
        writing_instruction=(
            "Direct technical voice with short sentences and concrete verbs "
            "observed from the minimal spacing rhythm and high contrast hierarchy "
            "without corporate filler or exclamation marks."
        ),
        confidence=0.85,
    )


def _brief(platform: str, content_type: str) -> ContentBrief:
    return ContentBrief(
        run_id="run-test",
        org_id=None,
        created_at="2026-01-01T00:00:00Z",
        platform=platform,
        content_type=content_type,
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="education_and_insight",
        funnel_stage="tofu",
        posting_strategy={
            "recommended_frequency": "weekly",
            "best_days": ["Tuesday"],
            "best_time_window": "09:00-11:00 IST",
        },
        platform_rules_summary=["Keep it platform-native.", "Follow character limits strictly."],
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="Test benchmark.",
        reasoning="Content brief for test.",
    )


# ---------------------------------------------------------------------------
# PollContent schema validators
# ---------------------------------------------------------------------------

class TestPollContentSchema:
    def test_valid_poll(self):
        p = PollContent(
            question="What slows your deploys most?",
            options=["Flaky tests", "Manual approvals", "Unclear ownership", "Config drift"],
        )
        assert len(p.options) == 4

    def test_option_too_long_raises(self):
        with pytest.raises(ValueError, match="25 characters"):
            PollContent(
                question="What slows your deploys most?",
                options=["This option is far too long for a poll", "B", "C", "D"],
            )

    def test_question_too_long_raises(self):
        with pytest.raises(ValueError, match="150 characters"):
            PollContent(
                question="Q" * 151,
                options=["A", "B", "C", "D"],
            )

    def test_fewer_than_four_options_raises(self):
        with pytest.raises(ValueError):
            PollContent(
                question="What is your biggest challenge?",
                options=["A", "B", "C"],
            )

    def test_more_than_four_options_raises(self):
        with pytest.raises(ValueError):
            PollContent(
                question="What is your biggest challenge?",
                options=["A", "B", "C", "D", "E"],
            )

    def test_intro_is_optional(self):
        p = PollContent(question="Which matters most?", options=["A", "B", "C", "D"])
        assert p.intro is None

    def test_duration_linkedin(self):
        p = PollContent(
            question="How often do you deploy?",
            options=["Daily", "Weekly", "Monthly", "Rarely"],
            duration="1 week",
        )
        assert p.duration == "1 week"


# ---------------------------------------------------------------------------
# InstagramStoryContent schema validators
# ---------------------------------------------------------------------------

class TestInstagramStoryContentSchema:
    def test_valid_story(self):
        s = InstagramStoryContent(hook="Your roadmap is a lie.", cta_text="Link in bio")
        assert s.hook == "Your roadmap is a lie."

    def test_hook_too_long_raises(self):
        with pytest.raises(ValueError, match="80 characters"):
            InstagramStoryContent(hook="H" * 81, cta_text="Link in bio")

    def test_cta_too_long_raises(self):
        with pytest.raises(ValueError, match="25 characters"):
            InstagramStoryContent(hook="Fix your deploys today.", cta_text="C" * 26)

    def test_hook_max_boundary(self):
        s = InstagramStoryContent(hook="H" * 80, cta_text="Swipe up")
        assert len(s.hook) == 80


# ---------------------------------------------------------------------------
# TwitterContent accepts 1 tweet (relaxed min_length)
# ---------------------------------------------------------------------------

class TestTwitterContentSingleTweet:
    def test_one_tweet_is_valid(self):
        tc = TwitterContent(
            tweets=["Engineers lose 90 min/day to deploy pings. There's a better way. #saas"],
            tweet_char_counts=[71],
            hashtags=["#saas"],
        )
        assert len(tc.tweets) == 1

    def test_empty_tweets_raises(self):
        with pytest.raises(ValueError):
            TwitterContent(tweets=[], tweet_char_counts=[], hashtags=["#saas"])


# ---------------------------------------------------------------------------
# Formatter parse helpers
# ---------------------------------------------------------------------------

class TestParsePollCopy:
    def test_parses_all_fields(self):
        raw = (
            "INTRO: Most teams don't know their deploy cadence.\n"
            "QUESTION: What slows your deployments most?\n"
            "OPTION_1: Flaky tests\n"
            "OPTION_2: Manual approvals\n"
            "OPTION_3: Unclear ownership\n"
            "OPTION_4: Config drift\n"
        )
        parsed = _parse_poll_copy(raw)
        assert parsed["intro"] == "Most teams don't know their deploy cadence."
        assert parsed["question"] == "What slows your deployments most?"
        assert parsed["option_1"] == "Flaky tests"
        assert parsed["option_4"] == "Config drift"

    def test_case_insensitive_keys(self):
        raw = "question: How often do you deploy?\nOPTION_1: Daily\nOption_2: Weekly\noption_3: Monthly\nOPTION_4: Rarely\n"
        parsed = _parse_poll_copy(raw)
        assert parsed["question"] == "How often do you deploy?"

    def test_missing_intro_returns_no_key(self):
        raw = "QUESTION: A question?\nOPTION_1: A\nOPTION_2: B\nOPTION_3: C\nOPTION_4: D\n"
        parsed = _parse_poll_copy(raw)
        assert "intro" not in parsed


class TestParseStoryCopy:
    def test_parses_hook_and_cta(self):
        raw = "HOOK: Your roadmap is a lie. Fix it.\nCTA: Link in bio\n"
        parsed = _parse_story_copy(raw)
        assert parsed["hook"] == "Your roadmap is a lie. Fix it."
        assert parsed["cta"] == "Link in bio"

    def test_missing_cta_returns_no_key(self):
        raw = "HOOK: Your roadmap is a lie.\n"
        parsed = _parse_story_copy(raw)
        assert "hook" in parsed
        assert "cta" not in parsed


class TestBuildPoll:
    def test_builds_valid_poll_content(self):
        parsed = {
            "question": "What slows your deploys most?",
            "option_1": "Flaky tests",
            "option_2": "Manual approvals",
            "option_3": "Unclear ownership",
            "option_4": "Config drift",
        }
        poll = _build_poll(parsed, "linkedin", _strategy())
        assert isinstance(poll, PollContent)
        assert poll.question == "What slows your deploys most?"
        assert len(poll.options) == 4
        assert poll.duration == "1 week"

    def test_fallback_question_from_strategy(self):
        poll = _build_poll({}, "twitter", _strategy())
        assert poll.question  # non-empty — falls back to lead_pain_point
        assert len(poll.options) == 4
        assert poll.duration is None  # Twitter has no duration

    def test_long_option_truncated_to_25(self):
        parsed = {
            "question": "Q?",
            "option_1": "This option is way too long for any poll platform",
            "option_2": "B",
            "option_3": "C",
            "option_4": "D",
        }
        poll = _build_poll(parsed, "linkedin", _strategy())
        assert len(poll.options[0]) <= 25


# ---------------------------------------------------------------------------
# Formatter mock dispatch — new content types
# ---------------------------------------------------------------------------

class TestFormatterMockDispatch:
    RAW_POLL = (
        "INTRO: Most teams don't measure deploy interruptions.\n"
        "QUESTION: What slows your deploys most?\n"
        "OPTION_1: Flaky tests\n"
        "OPTION_2: Manual approvals\n"
        "OPTION_3: Unclear ownership\n"
        "OPTION_4: Config drift\n"
    )
    RAW_STORY = "HOOK: Deployments shouldn't hurt.\nCTA: Link in bio\n"
    RAW_SINGLE = "Engineers lose 90 min/day to deploy pings. There's a better way. #devtools"

    def test_twitter_single_tweet_dispatch(self):
        result = formatter.run(
            self.RAW_SINGLE,
            _brief("twitter", "single_tweet"),
            _strategy(),
            _brand(),
        )
        assert isinstance(result, FormattedContent)
        assert result.platform == "twitter"
        assert result.twitter_content is not None
        assert len(result.twitter_content.tweets) == 1

    def test_twitter_poll_dispatch(self):
        result = formatter.run(
            self.RAW_POLL,
            _brief("twitter", "poll"),
            _strategy(),
            _brand(),
        )
        assert isinstance(result, FormattedContent)
        assert result.platform == "twitter"
        assert result.twitter_poll_content is not None
        assert isinstance(result.twitter_poll_content, PollContent)
        assert result.twitter_content is None

    def test_linkedin_poll_dispatch(self):
        result = formatter.run(
            self.RAW_POLL,
            _brief("linkedin", "poll"),
            _strategy(),
            _brand(),
        )
        assert isinstance(result, FormattedContent)
        assert result.platform == "linkedin"
        assert result.linkedin_poll_content is not None
        assert isinstance(result.linkedin_poll_content, PollContent)
        assert result.linkedin_poll_content.duration == "1 week"
        assert result.linkedin_content is None

    def test_linkedin_question_post_uses_standard_formatter(self):
        raw = "When did your roadmap last reflect what shipped?\n\nMost teams keep two versions. #saas #product"
        result = formatter.run(
            raw,
            _brief("linkedin", "question_post"),
            _strategy(),
            _brand(),
        )
        assert isinstance(result, FormattedContent)
        assert result.platform == "linkedin"
        assert result.linkedin_content is not None

    def test_instagram_story_dispatch(self):
        result = formatter.run(
            self.RAW_STORY,
            _brief("instagram", "story"),
            _strategy(),
            _brand(),
        )
        assert isinstance(result, FormattedContent)
        assert result.platform == "instagram"
        assert result.instagram_story_content is not None
        assert isinstance(result.instagram_story_content, InstagramStoryContent)
        assert result.instagram_content is None

    def test_instagram_story_hook_max_80(self):
        result = formatter.run(
            self.RAW_STORY,
            _brief("instagram", "story"),
            _strategy(),
            _brand(),
        )
        assert len(result.instagram_story_content.hook) <= 80

    def test_twitter_thread_still_works(self):
        raw = "1/ Deploy queues kill momentum.\n2/ Teams lose 90 min/day in Slack pings.\n3/ One dashboard changes that.\n4/ Start your free trial today. #saas"
        brief = ContentBrief(
            run_id="run-test",
            org_id=None,
            created_at="2026-01-01T00:00:00Z",
            platform="twitter",
            content_type="thread",
            narrative_arc="pain-agitate-solve-cta",
            content_pillar="education_and_insight",
            funnel_stage="tofu",
            posting_strategy={
                "recommended_frequency": "weekly",
                "best_days": ["Tuesday"],
                "best_time_window": "09:00-11:00 IST",
            },
            platform_rules_summary=["Keep it platform-native.", "Follow character limits strictly."],
            knowledge_context_used=False,
            knowledge_context_summary=None,
            benchmark_reference="Test benchmark.",
            reasoning="Content brief for test.",
            thread_length_target=4,
        )
        result = formatter.run(raw, brief, _strategy(), _brand())
        assert result.twitter_content is not None
        assert len(result.twitter_content.tweets) >= 1
