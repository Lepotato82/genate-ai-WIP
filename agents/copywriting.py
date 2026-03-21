"""
Step 6: Copywriting.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from prompts.loader import load_prompt
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief


def _mock_copy(content_brief: ContentBrief, strategy: StrategyBrief) -> str:
    if content_brief.platform == "twitter":
        return (
            "1/ Your team is spending too long converting product truth into social copy.\n\n"
            "2/ The result is delayed launches and weak hooks.\n\n"
            "3/ Genate structures strategy first, then generates grounded messaging.\n\n"
            f"4/ Proof: {strategy.proof_point}\n\n"
            "5/ Read more and adapt this workflow for your next campaign. #saas"
        )
    return (
        "Most SaaS teams do not struggle with ideas.\n\n"
        "They struggle with turning product truth into platform-native copy quickly.\n\n"
        "Genate bridges that gap with strategy-first generation grounded in real proof points.\n\n"
        f"{strategy.proof_point}\n\n"
        "Learn more and see how your team can ship faster.\n\n"
        "#saas #marketing #content"
    )


def run(content_brief: ContentBrief, strategy: StrategyBrief, brand_profile: BrandProfile) -> str:
    if settings.MOCK_MODE:
        return _mock_copy(content_brief, strategy)

    prompt = load_prompt("copywriting_v1")
    user_payload = {
        "platform": content_brief.platform,
        "narrative_arc": strategy.narrative_arc,
        "lead_pain_point": strategy.lead_pain_point,
        "primary_claim": strategy.primary_claim,
        "proof_point": strategy.proof_point,
        "cta_intent": strategy.cta_intent,
        "writing_instruction": brand_profile.writing_instruction,
    }
    return chat_completion(
        [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": str(user_payload)},
        ]
    ).strip()
