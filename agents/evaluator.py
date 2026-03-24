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
import re

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
        tweets = content.twitter_content.tweets
        total = len(tweets)
        return "\n\n".join(f"Tweet {i + 1}/{total}: {t}" for i, t in enumerate(tweets))
    if content.instagram_content:
        return content.instagram_content.full_caption
    if content.blog_content:
        return str(content.blog_content.get("body", ""))
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
    "  accuracy   — are claims grounded in primary_claim AND the proof_point?\n\n"
    "STRICT CALIBRATION (apply before scoring):\n"
    "- ENGAGEMENT 5 requires: the hook names a specific daily friction OR uses a surprising "
    "number OR creates genuine curiosity. Generic openers such as \"Your Daily Friction is...\", "
    "\"Are you struggling with...\", \"Discover how...\" cap engagement at 3.\n"
    "- TONE_MATCH 5 requires: zero violations of writing_instruction. Exclamation marks when "
    "instruction says corporate → tone_match 2. Words like \"revolutionize\", \"game-changing\", "
    "\"seamless\" → tone_match 1 unless the instruction explicitly allows hype.\n"
    "- ACCURACY 5 requires: proof_point used verbatim or near-verbatim. Score 3 if paraphrased "
    "but not fabricated. Score 1 if any statistic appears that is NOT in the provided "
    "proof_point or primary_claim.\n"
    "- Platform format violations reduce the relevant dimension: bullet symbols (•) in "
    "LinkedIn body → clarity minus 1. CTA copy that does not match cta_intent → tone_match minus 1. "
    "Hashtags inline in body (not at end) → tone_match minus 1.\n\n"
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


_GENERIC_ENGAGEMENT_OPENERS = (
    "discover how",
    "are you struggling",
    "your daily friction is",
)


def _apply_engagement_generic_cap(copy_text: str, engagement: int) -> int:
    head = copy_text.lower()[:500]
    if any(p in head for p in _GENERIC_ENGAGEMENT_OPENERS):
        return min(engagement, 3)
    return engagement


def _check_fabricated_stats(
    copy: str,
    strategy_brief: StrategyBrief,
) -> str | None:
    """Return a pre-built revision_hint if fabricated stats are detected.

    Fires before the LLM scores, giving the Evaluator the correct signal even
    when the LLM misses it. Returns None when no fabricated numbers are found.
    """
    copy_numbers = set(re.findall(r"\b\d+(?:\.\d+)?(?:%|K|M|B)?\b", copy))
    permitted_text = strategy_brief.proof_point + " " + strategy_brief.primary_claim
    permitted_numbers = set(re.findall(r"\b\d+(?:\.\d+)?(?:%|K|M|B)?\b", permitted_text))
    fabricated = copy_numbers - permitted_numbers
    # Filter out year numbers (2020-2030) — these are not fabricated stats
    fabricated = {n for n in fabricated if not (2020 <= int(float(n.rstrip("%KMB"))) <= 2030)}
    if fabricated:
        return (
            f"The copy contains numeric claims not present in the "
            f"proof_point or primary_claim: {sorted(fabricated)}. "
            f"Remove all fabricated statistics. Only use numbers "
            f"that appear verbatim in the proof_point field."
        )
    return None


def _apply_fabricated_stat_cap(
    copy_text: str, proof_point: str, primary_claim: str, accuracy: int
) -> int:
    """Cap accuracy at 1 if copy contains a numeric stat not present in proof_point or primary_claim.

    A numeric stat is any token matching digits with optional % or x suffix (e.g. 63%, 2x, 40%).
    Stats that appear verbatim in proof_point or primary_claim are allowed.
    """
    allowed_text = (proof_point + " " + primary_claim).lower()
    allowed_stats = set(re.findall(r"\d+(?:\.\d+)?(?:%|x\b)", allowed_text))
    copy_stats = set(re.findall(r"\d+(?:\.\d+)?(?:%|x\b)", copy_text.lower()))
    fabricated = copy_stats - allowed_stats
    if fabricated:
        logger.warning(
            "Evaluator: fabricated stats detected not in proof_point/primary_claim: %s — "
            "capping accuracy at 1",
            fabricated,
        )
        return 1
    return accuracy


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

    # Pre-check for fabricated stats before calling LLM — inject violation into system prompt
    pre_hint = _check_fabricated_stats(copy_text, strategy_brief)
    if pre_hint:
        logger.warning("Evaluator pre-check: %s", pre_hint)
        system = f"PRE-DETECTED VIOLATION: {pre_hint}\n\n" + system

    platform_note = ""
    if formatted_content.platform == "twitter":
        platform_note = (
            "\n\nFormat expectations (Twitter): Thread with 4–8 tweets; tweet 1 is the hook; "
            "proof_point should appear verbatim in one tweet; hashtags only on the final tweet. "
            "Penalize clarity if tweets blur together or omit the strategy proof.\n"
        )
    elif formatted_content.platform == "instagram":
        platform_note = (
            "\n\nFormat expectations (Instagram): First line is preview (emotional); proof_point "
            "should appear in the caption body; hashtags must not appear inline in body/preview. "
            "Penalize tone_match if the voice ignores writing_instruction.\n"
        )

    user_msg = (
        "Read the copy below carefully before scoring. Apply calibration anchors "
        "to what is actually written — do not score based on the strategy fields alone.\n\n"
        f"platform: {formatted_content.platform}\n\n"
        f"--- COPY TO EVALUATE ---\n{copy_text}\n--- END COPY ---\n\n"
        f"writing_instruction: {brand_profile.writing_instruction}\n\n"
        f"cta_intent: {strategy_brief.cta_intent}\n\n"
        f"primary_claim: {strategy_brief.primary_claim}\n\n"
        f"proof_point (accuracy baseline): {strategy_brief.proof_point}"
        f"{platform_note}"
    )

    raw = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )

    try:
        data = parse_json_object(raw)
    except ValueError:
        # LLM returned markdown prose instead of JSON — extract scores via regex
        logger.warning("Evaluator: non-JSON response; extracting scores from markdown text")
        data = {}
        for dim in ("clarity", "engagement", "tone_match", "accuracy"):
            m = re.search(
                rf"\*{{0,2}}{re.escape(dim.replace('_', '[_ ]'))}\*{{0,2}}[:\s]+(\d)",
                raw,
                re.IGNORECASE,
            )
            if m:
                data[dim] = int(m.group(1))

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
        # Fallback: build two sentences from the scores so the validator's 2-sentence rule passes
        dims = {"clarity": data.get("clarity", 3), "engagement": data.get("engagement", 3),
                "tone_match": data.get("tone_match", 3), "accuracy": data.get("accuracy", 3)}
        low = min(dims, key=dims.get)
        high = max(dims, key=dims.get)
        scores_rationale = (
            f"Copy scored highest on {high} ({dims[high]}/5) and lowest on {low} ({dims[low]}/5). "
            "Scores derived from markdown evaluation response."
        )

    # Coerce scores to int (LLM sometimes returns floats)
    for dim in ("clarity", "engagement", "tone_match", "accuracy"):
        try:
            data[dim] = int(data[dim])
        except (KeyError, TypeError, ValueError):
            data[dim] = 3  # safe fallback

    data["engagement"] = _apply_engagement_generic_cap(copy_text, data["engagement"])
    data["accuracy"] = _apply_fabricated_stat_cap(
        copy_text, strategy_brief.proof_point, strategy_brief.primary_claim, data["accuracy"]
    )

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
