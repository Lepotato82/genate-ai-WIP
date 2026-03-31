"""
Tests for contract-driven pipeline rules (session fixes FIX 1–4).

  FIX 1  strategy.py / evaluator.py — YAML as single source of truth
  FIX 2  copywriter.py              — CTA validation
  FIX 3  copywriter.py              — Research enforcement
  FIX 4  ui_analyzer.py             — writing_instruction quality check
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from agents.copywriter import (
    CTA_SIGNALS,
    _validate_cta,
    _validate_research_usage,
)
from agents.ui_analyzer import _is_valid_writing_instruction
from schemas.research_proof_point import ResearchProofPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _research_point(
    text: str = "67% of B2B buyers consult AI engines before contacting a vendor",
    source_name: str = "Gartner",
    credibility_tier: str = "tier_1",
) -> ResearchProofPoint:
    return ResearchProofPoint(
        text=text,
        source_name=source_name,
        source_url="https://gartner.com/research/example",
        relevance_reason="Relevant to AI search visibility pain point.",
        proof_type="report",
        credibility_tier=credibility_tier,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# FIX 2 — _validate_cta
# ---------------------------------------------------------------------------

class TestValidateCta:
    def test_signal_in_last_20_percent_returns_true(self):
        # "start" is in the CTA_SIGNALS["start_trial"] list
        copy = "A" * 400 + " Start your free trial today."
        assert _validate_cta(copy, "start_trial") is True

    def test_empty_cta_intent_returns_true(self):
        assert _validate_cta("Some copy with no CTA at all.", "") is True

    def test_none_equivalent_intent_returns_true(self):
        # cta_intent not in CTA_SIGNALS → signals list is empty → True
        assert _validate_cta("Any copy here.", "unknown_intent") is True

    def test_signal_only_in_first_80_percent_returns_false(self):
        # "trial" appears only in the first 80%
        signal_copy = "Start your free trial today. " + "B" * 400
        assert _validate_cta(signal_copy, "start_trial") is False

    def test_missing_cta_signal_returns_false(self):
        copy = "Your brand is losing visibility. Searchable fixes that. " * 10
        assert _validate_cta(copy, "book_demo") is False

    def test_book_demo_signal_present_at_end(self):
        copy = "C" * 300 + " Book a demo to see it in action."
        assert _validate_cta(copy, "book_demo") is True

    def test_learn_more_signal_present_at_end(self):
        copy = "D" * 300 + " Discover how this works for your team."
        assert _validate_cta(copy, "learn_more") is True

    def test_sign_up_signal_present_at_end(self):
        copy = "E" * 300 + " Join 500 teams — create your account now."
        assert _validate_cta(copy, "sign_up") is True

    def test_cta_signals_dict_has_required_keys(self):
        required_keys = {"start_trial", "learn_more", "book_demo", "sign_up"}
        assert required_keys.issubset(CTA_SIGNALS.keys())

    def test_all_cta_intents_have_nonempty_signals(self):
        for intent, signals in CTA_SIGNALS.items():
            assert len(signals) > 0, f"CTA_SIGNALS[{intent!r}] is empty"


# ---------------------------------------------------------------------------
# FIX 3 — _validate_research_usage
# ---------------------------------------------------------------------------

class TestValidateResearchUsage:
    def test_empty_list_returns_true(self):
        assert _validate_research_usage("Any copy.", []) is True

    def test_none_equivalent_empty_list(self):
        # Passing no research points — should always pass
        assert _validate_research_usage("Some copy text here.", []) is True

    def test_stat_words_present_in_copy_returns_true(self):
        # "67% of B2B buyers" — first 4 words: ["67%", "of", "b2b", "buyers"]
        # At least 3 of those appear in the copy
        copy = "Gartner found that 67% of B2B buyers now consult AI before a vendor call."
        pts = [_research_point("67% of B2B buyers consult AI engines before contacting a vendor")]
        assert _validate_research_usage(copy, pts) is True

    def test_stat_not_present_in_copy_returns_false(self):
        copy = "Your brand is losing visibility in AI search results every single day."
        pts = [_research_point("67% of B2B buyers consult AI engines before contacting a vendor")]
        assert _validate_research_usage(copy, pts) is False

    def test_short_stat_literal_match(self):
        # Stat is 1-2 words — use literal substring fallback
        copy = "Teams spend more on AI monitoring than expected: 45% over budget."
        pts = [_research_point("45% over budget", source_name="HubSpot", credibility_tier="tier_2")]
        assert _validate_research_usage(copy, pts) is True

    def test_any_point_in_list_satisfies_check(self):
        # First point not found; second point found — should return True
        copy = "McKinsey found that 70% of enterprises are investing in AI search this year."
        pts = [
            _research_point("67% of B2B buyers consult AI engines", source_name="Gartner"),
            _research_point("70% of enterprises are investing in AI search", source_name="McKinsey", credibility_tier="tier_1"),
        ]
        assert _validate_research_usage(copy, pts) is True

    def test_case_insensitive_matching(self):
        copy = "GARTNER FOUND THAT 67% OF B2B BUYERS CONSULT AI BEFORE CALLING."
        pts = [_research_point("67% of B2B buyers consult AI engines before contacting a vendor")]
        assert _validate_research_usage(copy, pts) is True


# ---------------------------------------------------------------------------
# FIX 4 — _is_valid_writing_instruction
# ---------------------------------------------------------------------------

class TestIsValidWritingInstruction:
    def test_empty_string_returns_false(self):
        assert _is_valid_writing_instruction("") is False

    def test_very_short_string_returns_false(self):
        assert _is_valid_writing_instruction("ok") is False

    def test_contains_font_reference_returns_false(self):
        assert _is_valid_writing_instruction("Use Inter font for headings.") is False

    def test_contains_hex_color_returns_false(self):
        assert _is_valid_writing_instruction("Primary color #5e6ad2 accent #fff.") is False

    def test_contains_px_returns_false(self):
        assert _is_valid_writing_instruction("Spacing is 4px between elements.") is False

    def test_contains_rem_returns_false(self):
        assert _is_valid_writing_instruction("Base size 1rem body text rem units.") is False

    def test_contains_border_returns_false(self):
        assert _is_valid_writing_instruction("Use rounded border radius for cards.") is False

    def test_copy_signal_direct_returns_true(self):
        assert _is_valid_writing_instruction("Write in a direct and technical voice.") is True

    def test_copy_signal_tone_returns_true(self):
        assert _is_valid_writing_instruction("Warm and encouraging tone throughout.") is True

    def test_copy_signal_concise_returns_true(self):
        assert _is_valid_writing_instruction("Concise sentences. Lead with the outcome.") is True

    def test_copy_signal_jargon_returns_true(self):
        assert _is_valid_writing_instruction("Avoid jargon and corporate buzzwords.") is True

    def test_copy_signal_lead_returns_true(self):
        assert _is_valid_writing_instruction("Lead with the customer pain. No filler.") is True

    def test_design_beats_copy_if_design_present(self):
        # Contains both design and copy signals — design wins, returns False
        assert _is_valid_writing_instruction(
            "Direct voice but use Inter font and #fff background color."
        ) is False

    def test_real_mock_instruction_passes(self):
        instruction = (
            "Write in a direct technical SaaS voice, lead with concrete daily "
            "friction, use exact product language, and avoid generic hype claims."
        )
        assert _is_valid_writing_instruction(instruction) is True


# ---------------------------------------------------------------------------
# FIX 1 — RuntimeError when YAML missing (strategy + evaluator)
# ---------------------------------------------------------------------------

class TestYamlRequired:
    def test_strategy_raises_runtime_error_when_yaml_missing(self):
        """strategy.run() must raise RuntimeError if strategy_v1.yaml is not found."""
        from agents import strategy
        from schemas.brand_profile import BrandProfile
        from schemas.content_brief import ContentBrief
        from schemas.product_knowledge import ProductKnowledge, Feature, ProofPoint

        brand = BrandProfile(
            run_id="t", org_id="o", created_at="2026-01-01T00:00:00+00:00",
            design_category="developer-tool",
            primary_color="#5e6ad2", secondary_color="#7170ff",
            background_color="#ffffff", font_family="Inter",
            font_weights=[400.0], border_radius="6px", spacing_unit="4px",
            tone="technical",
            writing_instruction=(
                "Direct and technical voice. Lead with concrete engineer pain. "
                "Avoid hype and generic claims. Short declarative sentences only."
            ),
            css_tokens={}, confidence=0.8,
        )
        product = ProductKnowledge(
            run_id="t", org_id="o", created_at="2026-01-01T00:00:00+00:00",
            product_name="TestProduct",
            product_url="https://example.com",
            description=(
                "TestProduct helps SaaS teams generate grounded marketing content "
                "quickly using structured workflows and reusable brand context that "
                "stays aligned with proof points and positioning for consistent output across "
                "every platform and campaign."
            ),
            product_category="marketing-content",
            features=[
                Feature(name="A", description="Feature A description for testing purposes here."),
                Feature(name="B", description="Feature B description for testing purposes here."),
            ],
            benefits=["Faster output", "More consistent voice"],
            proof_points=[
                ProofPoint(text="Used by over five hundred teams globally.", proof_type="user_count", source="scraped_page")
            ],
            pain_points=["Manual work is slow", "Brand drift is common"],
            messaging_angles=["Speed with consistency"],
            scrape_word_count=500, data_source="scraped_only",
        )
        brief = ContentBrief(
            run_id="t", org_id="o", created_at="2026-01-01T00:00:00+00:00",
            platform="linkedin", content_type="text_post",
            narrative_arc="pain-agitate-solve-cta", content_pillar="pain_and_problem",
            funnel_stage="tofu", content_depth="concise",
            posting_strategy={
                "recommended_frequency": "3x weekly",
                "best_days": ["Tuesday", "Thursday"],
                "best_time_window": "10:00-12:00 IST",
            },
            platform_rules_summary=["Hook must be standalone", "Hashtags at end only"],
            benchmark_reference="SaaS engagement benchmarks.",
            reasoning="text_post for single sharp idea with minimal features.",
            knowledge_context_used=False,
        )

        with patch("agents.strategy.load_prompt", side_effect=FileNotFoundError("not found")):
            with pytest.raises(RuntimeError, match="strategy_v1.yaml not found"):
                strategy.run(brief, product, brand)

    def test_evaluator_raises_runtime_error_when_yaml_missing(self):
        """evaluator.run() must raise RuntimeError if evaluator_v1.yaml is not found."""
        from agents import evaluator
        from schemas.brand_profile import BrandProfile
        from schemas.formatted_content import FormattedContent, LinkedInContent
        from schemas.strategy_brief import StrategyBrief

        brand = BrandProfile(
            run_id="t", org_id="o", created_at="2026-01-01T00:00:00+00:00",
            design_category="developer-tool",
            primary_color="#5e6ad2", secondary_color="#7170ff",
            background_color="#ffffff", font_family="Inter",
            font_weights=[400.0], border_radius="6px", spacing_unit="4px",
            tone="technical",
            writing_instruction=(
                "Direct and technical tone. Lead with concrete engineer pain. "
                "Avoid hype and corporate language. Short declarative sentences."
            ),
            css_tokens={}, confidence=0.8,
        )
        strategy_brief = StrategyBrief(
            run_id="t", org_id="o", created_at="2026-01-01T00:00:00+00:00",
            narrative_arc="pain-agitate-solve-cta",
            lead_pain_point="Teams lose hours every week to manual AI search analysis.",
            primary_claim="Searchable cuts analysis time with automated tracking.",
            proof_point="Used by ten SaaS teams with no manual analysis.",
            proof_point_type="stat",
            hook_direction="Lead with the specific time cost of manual AI visibility tracking.",
            cta_intent="start_trial",
            appeal_type="rational",
            target_icp_role="Head of Marketing",
            positioning_mode="category_creation",
            messaging_angle_used="AI search optimization platform",
            knowledge_context_applied=False,
        )
        formatted = FormattedContent(
            run_id="t", org_id="o", created_at="2026-01-01T00:00:00+00:00",
            platform="linkedin",
            linkedin_content=LinkedInContent(
                hook="Your brand is invisible in AI search.",
                body="Searchable shows you exactly where you stand and how to fix it.",
                full_post=(
                    "Your brand is invisible in AI search.\n\n"
                    "Searchable shows you exactly where you stand and how to fix it.\n\n"
                    "Start your free trial today.\n\n#saas #ai #search"
                ),
                hashtags=["#saas", "#ai", "#search"],
                word_count=20,
            ),
        )

        with patch("agents.evaluator.load_prompt", side_effect=FileNotFoundError("not found")):
            with pytest.raises(RuntimeError, match="evaluator_v1.yaml not found"):
                evaluator.run(formatted, strategy_brief, brand)
