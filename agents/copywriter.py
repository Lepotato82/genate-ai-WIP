"""
Step 6: Copywriter — raw copy from strategy + brief + brand (no structural formatting).
"""

from __future__ import annotations

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief


def _product_name_hint(strategy: StrategyBrief) -> str:
    claim = (strategy.primary_claim or "").strip()
    if not claim:
        return "Linear"
    first = claim.split()[0].strip(".,'\"")
    return first if first else "Linear"


def _mock_twitter(strategy: StrategyBrief) -> str:
    return (
        "1/ Your team is spending too long converting product truth into social copy.\n\n"
        "2/ The result is delayed launches and weak hooks.\n\n"
        "3/ Genate structures strategy first, then generates grounded messaging.\n\n"
        f"4/ Proof: {strategy.proof_point}\n\n"
        "5/ Read more and adapt this workflow for your next campaign."
    )


def _mock_instagram(strategy: StrategyBrief) -> str:
    return (
        "You are one scroll away from copy that actually matches your product truth.\n\n"
        "Most teams still ship generic hooks because strategy never meets the page.\n\n"
        f"We anchor every line in proof like: {strategy.proof_point}\n\n"
        "Try a workflow where brand, claim, and CTA stay aligned end to end."
    )


def _mock_linkedin_post(strategy: StrategyBrief) -> str:
    name = _product_name_hint(strategy)
    return (
        f"Your standup keeps circling the same blocked issues because nobody trusts the board.\n\n"
        f"That is not a people problem — it is a systems problem. When issue state drifts from reality, "
        f"every roadmap conversation starts with cleanup instead of decisions.\n\n"
        f"{name} is built for teams that ship software: fast keyboard flows, clear ownership, "
        f"and a roadmap that stays tied to execution.\n\n"
        f"{strategy.proof_point}\n\n"
        f"If you are tired of translating spreadsheets into status updates, it is worth seeing how "
        f"modern product teams run their weekly planning in one place.\n\n"
        f"#productmanagement #engineering #saas"
    )


def run(
    strategy_brief: StrategyBrief,
    content_brief: ContentBrief,
    brand_profile: BrandProfile,
) -> str:
    if settings.MOCK_MODE:
        if content_brief.platform == "twitter":
            return _mock_twitter(strategy_brief)
        if content_brief.platform == "instagram":
            return _mock_instagram(strategy_brief)
        return _mock_linkedin_post(strategy_brief)

    try:
        spec = load_prompt("copywriting_v1")
        base = spec.system_prompt
    except FileNotFoundError:
        base = (
            "You are a SaaS copywriting agent. Write platform-native marketing copy "
            "that executes the given strategy exactly. Return ONLY the raw copy text — "
            "no labels, no markdown, no explanation."
        )
    system = (
        f"Brand voice instruction (non-negotiable):\n{brand_profile.writing_instruction}\n\n"
        f"{base}"
    )
    slide_hint = ""
    if content_brief.content_type == "carousel" and content_brief.slide_count_target:
        slide_hint = (
            f"\nslide_count_target: {content_brief.slide_count_target} "
            "(write a distinct slide heading + 2-3 lines per slide)"
        )
    platform_hint = ""
    if content_brief.platform == "twitter":
        platform_hint = (
            "\n\nWrite a Twitter thread. Format as numbered tweets:\n"
            "1/ [tweet text]\n"
            "2/ [tweet text]\n"
            "...\n"
            "The Formatter will split these into individual tweets.\n"
            "Tweet 1 must be a standalone hook under 280 chars.\n"
            "Execute hook_direction in tweet 1—lead with the specific friction in lead_pain_point "
            "or the angle in hook_direction, not a vague productivity opener.\n"
            "Include proof_point as one full tweet, copied verbatim (same words).\n"
            "Thread should advance narrative_arc; final tweet matches cta_intent.\n"
            "Stay on primary_claim and differentiator—do not invent a different product story."
        )
    elif content_brief.platform == "instagram":
        platform_hint = (
            "\n\nWrite Instagram caption copy. The first sentence must be a "
            "complete emotional statement under 125 chars that stops the scroll. "
            "Write for a mobile reader. Short sentences. Emotional before rational. "
            "The Formatter will add hashtags separately.\n"
            "Ground the caption in lead_pain_point and primary_claim; include proof_point "
            "verbatim in the body (same wording).\n"
            "Match writing_instruction; no hashtag lines—you will not add #tags yourself."
        )
    user_msg = (
        f"platform: {content_brief.platform}\n"
        f"narrative_arc: {strategy_brief.narrative_arc}\n"
        f"lead_pain_point: {strategy_brief.lead_pain_point}\n"
        f"primary_claim: {strategy_brief.primary_claim}\n"
        f"proof_point: {strategy_brief.proof_point}\n"
        f"cta_intent: {strategy_brief.cta_intent}\n"
        f"writing_instruction: {brand_profile.writing_instruction}\n"
        f"hook_direction: {strategy_brief.hook_direction}"
        + slide_hint
        + platform_hint
        + "\n\nWrite the copy. Return only the copy text. No JSON.\n"
        "No preamble. No explanation."
    )
    return chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
    ).strip()
