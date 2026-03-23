"""
Step 9: Evaluator.

Scores formatted content on four dimensions (clarity, engagement, tone_match,
accuracy) and gates the retry loop. `passes` and `overall_score` are ALWAYS
computed by EvaluatorOutput Pydantic validators — never trusted from LLM output.

When passes=False the Evaluator also produces a targeted revision_hint that
is passed back to the Formatter for a rewrite attempt (max 2 retries).
"""

from __future__ import annotations

import logging

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.evaluator_output import EvaluatorOutput
from schemas.formatted_content import FormattedContent
from schemas.strategy_brief import StrategyBrief
from agents._utils import parse_json_object, utc_now_iso

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    formatted_content: FormattedContent,
    retry_count: int,
) -> EvaluatorOutput:
    return EvaluatorOutput(
        run_id=formatted_content.run_id,
        org_id=formatted_content.org_id,
        created_at=utc_now_iso(),
        platform=formatted_content.platform,
        clarity=4,
        engagement=4,
        tone_match=4,
        accuracy=4,
        revision_hint=None,  # passes=True so revision_hint must be null
        scores_rationale=(
            "The hook names a specific daily friction that resonates with engineers. "
            "The proof point is grounded in the primary claim without fabrication."
        ),
        retry_count=retry_count,
    )


# ---------------------------------------------------------------------------
# System prompt (loaded from YAML if exists, otherwise inline)
# ---------------------------------------------------------------------------

_INLINE_SYSTEM = (
    "You are the Evaluator agent for Genate, a SaaS content pipeline.\n\n"
    "Score the provided marketing copy on four quality dimensions (1-5, integer only):\n"
    "  clarity    — is the copy easy to understand on a single read?\n"
    "  engagement — does the hook stop the scroll or force continued reading?\n"
    "  tone_match — does the copy execute the writing_instruction exactly?\n"
    "  accuracy   — are all claims grounded in the primary_claim provided?\n\n"
    "PASS RULE: passes = true ONLY when ALL FOUR scores are >= 3.\n\n"
    "Return ONLY valid JSON. When ALL scores >= 3:\n"
    "{\n"
    '  "clarity": <int 1-5>, "clarity_reason": "<one sentence>",\n'
    '  "engagement": <int 1-5>, "engagement_reason": "<one sentence>",\n'
    '  "tone_match": <int 1-5>, "tone_match_reason": "<one sentence>",\n'
    '  "accuracy": <int 1-5>, "accuracy_reason": "<one sentence>"\n'
    "}\n\n"
    "When ANY score < 3, also include:\n"
    '  "revision_hint": "<one specific, actionable sentence targeting the lowest score>"\n\n'
    "DO NOT include 'passes' or 'overall_score' — these are computed by the system."
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    formatted_content: FormattedContent,
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    retry_count: int = 0,
) -> EvaluatorOutput:
    if settings.MOCK_MODE:
        return _mock(formatted_content, retry_count)

    # Load prompt from YAML if it exists
    try:
        prompt = load_prompt("evaluator_v1")
        system = prompt.system_prompt
    except FileNotFoundError:
        system = _INLINE_SYSTEM

    copy_text = _extract_copy(formatted_content)

    user_msg = (
        f"platform: {formatted_content.platform}\n\n"
        f"copy:\n{copy_text}\n\n"
        f"writing_instruction: {brand_profile.writing_instruction}\n\n"
        f"primary_claim: {strategy_brief.primary_claim}\n\n"
        f"proof_point (accuracy baseline): {strategy_brief.proof_point}"
    )

    raw = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )

    data = parse_json_object(raw)

    # CRITICAL: strip computed fields — never trust from LLM
    data.pop("passes", None)
    data.pop("overall_score", None)
    data.pop("lowest_dimension", None)

    # Build scores_rationale from individual reason fields
    rationale_parts = [
        data.pop("clarity_reason", ""),
        data.pop("engagement_reason", ""),
        data.pop("tone_match_reason", ""),
        data.pop("accuracy_reason", ""),
    ]
    scores_rationale = " ".join(p for p in rationale_parts if p).strip()
    if not scores_rationale:
        scores_rationale = "Copy evaluated on all four dimensions."

    # Coerce scores to int (LLM sometimes returns floats)
    for dim in ("clarity", "engagement", "tone_match", "accuracy"):
        try:
            data[dim] = int(data[dim])
        except (KeyError, TypeError, ValueError):
            data[dim] = 3  # safe fallback

    # Determine if copy passes (all scores >= 3)
    will_pass = all(data.get(d, 3) >= 3 for d in ("clarity", "engagement", "tone_match", "accuracy"))

    # If LLM returned a revision_hint but copy passes, strip it
    if will_pass:
        data.pop("revision_hint", None)

    # If copy fails and LLM didn't return a revision_hint, build a fallback
    if not will_pass and not data.get("revision_hint"):
        low_dim = min(
            ["accuracy", "tone_match", "engagement", "clarity"],
            key=lambda d: data.get(d, 3),
        )
        data["revision_hint"] = (
            f"Rewrite the copy to improve the {low_dim} dimension — ensure every "
            "sentence directly supports the primary claim without introducing "
            "fabricated statistics or claims not present in the provided proof point."
        )

    return EvaluatorOutput(
        run_id=formatted_content.run_id,
        org_id=formatted_content.org_id,
        created_at=utc_now_iso(),
        platform=formatted_content.platform,
        scores_rationale=scores_rationale,
        retry_count=retry_count,
        **{k: v for k, v in data.items() if k in (
            "clarity", "engagement", "tone_match", "accuracy", "revision_hint"
        )},
    )
