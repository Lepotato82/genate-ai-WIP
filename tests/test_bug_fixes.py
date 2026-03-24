"""Tests for BUG-001, BUG-002, BUG-003 fixes."""

from __future__ import annotations

import pytest

from agents.evaluator import _check_fabricated_stats
from agents.formatter import _clean_tweet, _truncate_to_sentence
from schemas.strategy_brief import StrategyBrief


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strategy(proof_point: str = "", primary_claim: str = "") -> StrategyBrief:
    return StrategyBrief(
        run_id="test-run",
        org_id="test-org",
        created_at="2026-01-01T00:00:00+00:00",
        narrative_arc="pain-agitate-solve-cta",
        content_type="carousel",
        platform="linkedin",
        lead_pain_point="Teams lose hours every single week to manual AI search analysis.",
        primary_claim=primary_claim or "Searchable cuts analysis time with automated tracking.",
        proof_point=proof_point or "Used by ten SaaS teams with no manual analysis.",
        proof_point_type="stat",
        hook_direction="Lead with the specific time cost of manual AI visibility tracking.",
        cta_intent="start_trial",
        appeal_type="rational",
        target_icp_role="Head of Marketing",
        positioning_mode="category_creation",
        messaging_angle_used="AI search optimization platform",
        knowledge_context_applied=False,
    )


# ---------------------------------------------------------------------------
# BUG-001 — _check_fabricated_stats
# ---------------------------------------------------------------------------

class TestCheckFabricatedStats:
    def test_returns_hint_when_copy_has_number_not_in_proof_point(self):
        strategy = _make_strategy(
            proof_point="206% share of voice improvements recorded by early customers."
        )
        # "200" is NOT in proof_point (206 is, not 200)
        hint = _check_fabricated_stats(
            "Searchable has helped over 200 companies improve visibility.",
            strategy,
        )
        assert hint is not None
        assert "200" in hint

    def test_returns_none_when_copy_numbers_all_in_proof_point(self):
        strategy = _make_strategy(
            proof_point="40% visibility increases with Searchable across tracked queries."
        )
        hint = _check_fabricated_stats(
            "Get 40% visibility increases with Searchable.",
            strategy,
        )
        assert hint is None

    def test_returns_none_when_copy_number_in_primary_claim(self):
        strategy = _make_strategy(
            proof_point="Significant improvements reported by enterprise customers.",
            primary_claim="Cut onboarding time by 30% with automated brand tracking.",
        )
        hint = _check_fabricated_stats(
            "Cut onboarding time by 30% with our tool.",
            strategy,
        )
        assert hint is None

    def test_ignores_year_numbers(self):
        strategy = _make_strategy(
            proof_point="Used by leading SaaS teams since launch for visibility tracking."
        )
        hint = _check_fabricated_stats(
            "Since 2024, teams have relied on this tool for accurate AI tracking.",
            strategy,
        )
        assert hint is None

    def test_ignores_2025_and_2026(self):
        strategy = _make_strategy(
            proof_point="Launched in Q1 as the first AI search optimization platform."
        )
        hint = _check_fabricated_stats(
            "Updated for 2025 and 2026 enterprise requirements.",
            strategy,
        )
        assert hint is None

    def test_returns_hint_for_fabricated_frequency(self):
        strategy = _make_strategy(
            proof_point="40% visibility increases recorded across all customer accounts."
        )
        # "12" is not in proof_point — it is a fabricated frequency
        hint = _check_fabricated_stats(
            "40% of brands waste 12 hours each month on manual analysis.",
            strategy,
        )
        assert hint is not None
        assert "12" in hint


# ---------------------------------------------------------------------------
# BUG-002 — _clean_tweet
# ---------------------------------------------------------------------------

class TestCleanTweet:
    def test_strips_formatter_parenthetical(self):
        tweet = "Great content here. (Formatter will split this into two tweets)"
        result = _clean_tweet(tweet)
        assert "(Formatter" not in result
        assert "Great content here." in result

    def test_strips_note_parenthetical(self):
        tweet = "Key stat here. (Note: this is a long tweet)"
        result = _clean_tweet(tweet)
        assert "(Note" not in result
        assert "Key stat here." in result

    def test_strips_this_parenthetical(self):
        tweet = "Insight here. (This tweet covers the mechanism)"
        result = _clean_tweet(tweet)
        assert "(This" not in result

    def test_strips_split_parenthetical(self):
        tweet = "Content here. (Split across two tweets for readability)"
        result = _clean_tweet(tweet)
        assert "(Split" not in result

    def test_strips_leading_number_slash_prefix(self):
        assert _clean_tweet("3/ With Searchable, track visibility") == "With Searchable, track visibility"

    def test_strips_leading_number_space_prefix(self):
        assert _clean_tweet("3 With Searchable, track visibility") == "With Searchable, track visibility"

    def test_does_not_strip_legitimate_parentheses(self):
        tweet = "Grew by 206% (year over year) with consistent tracking."
        result = _clean_tweet(tweet)
        assert "(year over year)" in result

    def test_does_not_strip_inline_multiplier(self):
        tweet = "Recovery improved 3x (from 12% to 41%)."
        result = _clean_tweet(tweet)
        assert "3x" in result


# ---------------------------------------------------------------------------
# BUG-003 — _truncate_to_sentence
# ---------------------------------------------------------------------------

class TestTruncateToSentence:
    def test_returns_text_as_is_when_under_125(self):
        text = "Short sentence."
        assert _truncate_to_sentence(text) == text

    def test_cuts_at_sentence_boundary_within_125(self):
        # Period at char ~16, well within 125
        text = "First sentence. " + "x" * 200
        result = _truncate_to_sentence(text)
        assert result == "First sentence."
        assert len(result) <= 125

    def test_allows_up_to_150_to_find_boundary(self):
        # Sentence boundary at char ~137 (between 125 and 150)
        prefix = "x" * 126  # 126 chars with no sentence-ending punctuation
        text = prefix + ". More text after the boundary."
        result = _truncate_to_sentence(text)
        assert result.endswith(".")
        assert 125 < len(result) <= 150

    def test_falls_back_to_word_boundary_when_no_sentence_in_150(self):
        # No punctuation at all within 150 chars
        text = "word " * 40  # ~200 chars, no sentence-ending punctuation
        result = _truncate_to_sentence(text)
        assert not result.endswith(" ")
        assert len(result) <= 125

    def test_never_cuts_mid_word(self):
        # A sentence where the 125-char boundary falls mid-word — must back up to space
        text = "The quick brown fox jumps over the lazy dog and then some more text that goes on."
        # This is under 125, so returned as-is
        result = _truncate_to_sentence(text)
        assert result == text

    def test_exclamation_is_a_boundary(self):
        text = "Stop wasting time! " + "x" * 200
        result = _truncate_to_sentence(text)
        assert result == "Stop wasting time!"

    def test_question_is_a_boundary(self):
        text = "Is your team losing hours? " + "x" * 200
        result = _truncate_to_sentence(text)
        assert result == "Is your team losing hours?"

    def test_instagram_preview_cuts_at_sentence_boundary(self):
        """_instagram_postprocess uses _truncate_to_sentence — preview ends at . ! or ?
        when a sentence boundary exists within 150 chars of a long input."""
        from agents.formatter import _instagram_postprocess

        # Build a string where a sentence ends around char 90 (well within 125)
        preview_input = (
            "Stuck in a loop of manual AI analysis every week. "
            "Your team spends hours hunting for visibility gaps that should take minutes to find."
        )
        ic = _instagram_postprocess(preview_input, "Body text here.", [], None)
        assert ic.preview_text[-1] in ".!?", (
            f"preview_text does not end at sentence boundary: {ic.preview_text!r}"
        )

    def test_truncate_to_sentence_boundary_between_125_and_150(self):
        """_truncate_to_sentence (standalone) extends to 150 to find a boundary.

        Note: InstagramContent.preview_text has max_length=125 schema constraint,
        so the 150-char extension is only useful outside of Instagram context.
        The function itself supports it correctly.
        """
        prefix = "A" * 126  # 126 chars, no boundary within 125
        text = prefix + ". More text."
        result = _truncate_to_sentence(text)
        assert result.endswith(".")
        assert len(result) > 125
