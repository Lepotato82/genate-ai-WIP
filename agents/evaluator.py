"""
Step 9: Evaluator.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from prompts.loader import load_prompt
from schemas.brand_profile import BrandProfile
from schemas.formatted_content import FormattedContent
from schemas.strategy_brief import StrategyBrief
from schemas.evaluator_output import EvaluatorOutput
from agents._utils import parse_json_object, utc_now_iso


def _extract_copy(content: FormattedContent) -> str:
    if content.linkedin_content:
        return content.linkedin_content.full_post
    if content.twitter_content:
        return "\n\n".join(content.twitter_content.tweets)
    if content.instagram_content:
        return content.instagram_content.full_caption
    if content.blog_content:
        return content.blog_content.body
    return ""


def _mock(content: FormattedContent) -> EvaluatorOutput:
    return EvaluatorOutput(
        run_id=content.run_id,
        org_id=content.org_id,
        created_at=utc_now_iso(),
        platform=content.platform,
        clarity=4,
        engagement=4,
        tone_match=4,
        accuracy=4,
        revision_hint=None,
        scores_rationale="The content is clear and easy to follow. The hook is strong and claims stay grounded.",
        retry_count=content.retry_count,
    )


def run(content: FormattedContent, strategy: StrategyBrief, brand: BrandProfile) -> EvaluatorOutput:
    if settings.MOCK_MODE:
        return _mock(content)

    prompt = load_prompt("evaluator_v1")
    payload = {
        "platform": content.platform,
        "copy": _extract_copy(content),
        "writing_instruction": brand.writing_instruction,
        "primary_claim": strategy.primary_claim,
    }
    raw = chat_completion(
        [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": str(payload)},
        ]
    )
    data = parse_json_object(raw)
    rationale = " ".join(
        [
            data.get("clarity_reason", ""),
            data.get("engagement_reason", ""),
            data.get("tone_match_reason", ""),
            data.get("accuracy_reason", ""),
        ]
    ).strip()
    return EvaluatorOutput(
        run_id=content.run_id,
        org_id=content.org_id,
        created_at=utc_now_iso(),
        platform=content.platform,
        clarity=data["clarity"],
        engagement=data["engagement"],
        tone_match=data["tone_match"],
        accuracy=data["accuracy"],
        revision_hint=data.get("revision_hint"),
        scores_rationale=rationale,
        retry_count=content.retry_count,
    )
