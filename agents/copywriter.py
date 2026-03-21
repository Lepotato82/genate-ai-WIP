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
        return _mock_linkedin_post(strategy_brief)

    spec = load_prompt("copywriting_v1")
    system = (
        f"Brand voice instruction (non-negotiable):\n{brand_profile.writing_instruction}\n\n"
        f"{spec.system_prompt}"
    )
    user_msg = (
        f"platform: {content_brief.platform}\n"
        f"narrative_arc: {content_brief.narrative_arc}\n"
        f"lead_pain_point: {strategy_brief.lead_pain_point}\n"
        f"primary_claim: {strategy_brief.primary_claim}\n"
        f"proof_point: {strategy_brief.proof_point}\n"
        f"cta_intent: {strategy_brief.cta_intent}\n"
        f"writing_instruction: {brand_profile.writing_instruction}\n"
        f"hook_direction: {strategy_brief.hook_direction}\n\n"
        "Write the copy. Return only the copy text. No JSON.\n"
        "No preamble. No explanation."
    )
    return chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
    ).strip()
