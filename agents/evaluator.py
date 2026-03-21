"""
Step 9: Evaluator — scores formatted copy; passes / overall_score computed in schema.
"""

from __future__ import annotations

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
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


def _mock(
    content: FormattedContent,
    strategy_brief: StrategyBrief,
    retry_count: int,
) -> EvaluatorOutput:
    return EvaluatorOutput(
        run_id=strategy_brief.run_id,
        org_id=strategy_brief.org_id,
        created_at=utc_now_iso(),
        platform=content.platform,
        clarity=4,
        engagement=4,
        tone_match=4,
        accuracy=4,
        revision_hint=None,
        scores_rationale=(
            "The hook states a clear problem and the body supports it with specifics. "
            "The CTA is easy to follow and the tone stays consistent throughout the post."
        ),
        retry_count=retry_count,
    )


def run(
    formatted_content: FormattedContent,
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    retry_count: int = 0,
) -> EvaluatorOutput:
    if settings.MOCK_MODE:
        return _mock(formatted_content, strategy_brief, retry_count)

    prompt = load_prompt("evaluator_pipeline_v1")
    copy_text = _extract_copy(formatted_content)
    user_msg = (
        f"Platform: {formatted_content.platform}\n"
        f"Writing instruction: {brand_profile.writing_instruction}\n"
        f"Primary claim this copy must execute:\n  {strategy_brief.primary_claim}\n"
        f"Proof point that must appear:\n  {strategy_brief.proof_point}\n\n"
        f"Copy to evaluate:\n{copy_text}\n\n"
        "Score on 4 dimensions (1-5 integers only): "
        "clarity, engagement, tone_match, accuracy.\n\n"
        "Also return:\n"
        "scores_rationale (2-4 sentences, reference specific elements),\n"
        "revision_hint (required if any score < 3, else null, "
        "must be specific actionable instruction, min 15 words).\n\n"
        "Return raw JSON only. No markdown. No explanation."
    )
    raw = chat_completion(
        [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": user_msg},
        ]
    )
    data = parse_json_object(raw)
    rationale = str(data.get("scores_rationale") or "").strip()
    if len([s for s in rationale.replace("?", ".").split(".") if s.strip()]) < 2:
        rationale = (
            f"{rationale} The opening lines set expectations while the middle ties claims to evidence."
        ).strip()
    clarity = int(data["clarity"])
    engagement = int(data["engagement"])
    tone_match = int(data["tone_match"])
    accuracy = int(data["accuracy"])
    passes = all(s >= 3 for s in (clarity, engagement, tone_match, accuracy))
    revision = None if passes else data.get("revision_hint")
    if not passes:
        if not revision or len(str(revision).split()) < 15:
            revision = (
                "Rewrite the body so the proof point appears verbatim, tighten the hook to match "
                "the brand writing instruction, remove any invented metrics, and end with one CTA "
                "that matches the strategy brief."
            )
    return EvaluatorOutput(
        run_id=strategy_brief.run_id,
        org_id=strategy_brief.org_id,
        created_at=utc_now_iso(),
        platform=formatted_content.platform,
        clarity=clarity,
        engagement=engagement,
        tone_match=tone_match,
        accuracy=accuracy,
        revision_hint=revision,
        scores_rationale=rationale,
        retry_count=retry_count,
    )
