"""
Step 5: Strategy.

Decides what to say before any copy is written. Selects the specific pain
point, primary claim, proof point, CTA, and hook direction. Returns a
StrategyBrief consumed by the Copywriting agent.
"""

from __future__ import annotations

import logging
import sys
import time

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief, _NO_PROOF_FALLBACK
from agents._utils import parse_json_object, utc_now_iso

logger = logging.getLogger(__name__)


def _progress(msg: str) -> None:
    """Write a progress line straight to stdout so it appears during long LLM calls."""
    try:
        sys.stdout.buffer.write(f"[strategy] {msg}\n".encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        logger.info("[strategy] %s", msg)


_NO_PROOF_FALLBACK = "No verified proof points available for this product"


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    content_brief: ContentBrief,
    product_knowledge: ProductKnowledge,
    brand_profile: BrandProfile,
) -> StrategyBrief:
    if product_knowledge.proof_points:
        proof = product_knowledge.proof_points[0]
        proof_text = proof.text
        proof_type = proof.proof_type
    else:
        proof_text = _NO_PROOF_FALLBACK
        proof_type = "stat"

    messaging_angle = (
        product_knowledge.messaging_angles[0]
        if product_knowledge.messaging_angles
        else "Speed with brand consistency"
    )

    out = StrategyBrief(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        lead_pain_point=(
            "Product and engineering leads still lose hours each week reconciling issue state, "
            "roadmap updates, and sprint commitments across tools that were never designed to stay in sync."
        ),
        primary_claim=(
            "Genate helps SaaS teams generate grounded, brand-aligned content quickly."
        ),
        proof_point=proof_text,
        proof_point_type=proof_type,  # type: ignore[arg-type]
        cta_intent="learn_more",
        appeal_type="rational",
        narrative_arc=content_brief.narrative_arc,
        target_icp_role="Growth marketing manager at a SaaS company",
        differentiator=(
            "Unlike generic AI writing tools, Genate ties every content decision to "
            "extracted brand signals and validated proof points from the product page."
        ),
        hook_direction=(
            "Open by naming a repeated daily friction and its time cost before "
            "any product or company mention."
        ),
        positioning_mode="category_creation",
        messaging_angle_used=messaging_angle,
        knowledge_context_applied=False,
    )

    # Cross-schema validation — log warnings but do not crash
    try:
        out.validate_against_product_knowledge(product_knowledge)
    except ValueError as exc:
        logger.warning("Strategy mock: product_knowledge validation warning: %s", exc)

    try:
        out.validate_against_content_brief(content_brief)
    except ValueError as exc:
        logger.warning("Strategy mock: content_brief validation warning: %s", exc)

    return out


# ---------------------------------------------------------------------------
# System prompt (loaded from YAML — required; RuntimeError if missing)
# ---------------------------------------------------------------------------

def _get_system_prompt() -> str:
    try:
        spec = load_prompt("strategy_v1")
        return spec.system_prompt
    except FileNotFoundError as exc:
        raise RuntimeError(
            "[strategy] strategy_v1.yaml not found — cannot run without prompt file"
        ) from exc


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    content_brief: ContentBrief,
    product_knowledge: ProductKnowledge,
    brand_profile: BrandProfile,
    research_proof_points: list | None = None,
) -> StrategyBrief:
    if settings.MOCK_MODE:
        return _mock(content_brief, product_knowledge, brand_profile)

    # Build numbered proof_points list for the prompt
    proof_list = "\n".join(
        f"  {i + 1}. [{p.proof_type}] {p.text}"
        for i, p in enumerate(product_knowledge.proof_points)
    )
    angle_list = "\n".join(
        f"  {i + 1}. {a}"
        for i, a in enumerate(product_knowledge.messaging_angles)
    )
    pain_list = "\n".join(
        f"  {i + 1}. {p}"
        for i, p in enumerate(product_knowledge.pain_points)
    )

    user_msg = (
        f"narrative_arc: {content_brief.narrative_arc}\n"
        f"platform: {content_brief.platform}\n"
        f"content_type: {content_brief.content_type}\n\n"
        f"pain_points:\n{pain_list}\n\n"
        f"primary_claim (derived from product description): "
        f"{product_knowledge.description[:200]}\n\n"
        f"proof_points (copy verbatim — do not paraphrase):\n{proof_list}\n\n"
        f"messaging_angles (copy verbatim):\n{angle_list}\n\n"
        f"brand_tone: {brand_profile.tone}\n"
        f"writing_instruction: {brand_profile.writing_instruction}"
    )

    if content_brief.content_type == "carousel" and research_proof_points:
        best_stat = research_proof_points[0].text
        user_msg += (
            f"\n\nCAROUSEL HOOK RULE: A research stat is available — use it as "
            f"the hook. Set hook_direction to instruct the copywriter to open "
            f'slide 1 with this stat as the headline: "{best_stat}"\n'
            f"Frame it as a question the reader hasn't considered."
        )

    _progress(
        f"calling LLM (platform={content_brief.platform}, "
        f"type={content_brief.content_type}, user_msg={len(user_msg)} chars)"
    )
    _t0 = time.time()
    raw = chat_completion(
        [
            {"role": "system", "content": _get_system_prompt()},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    _progress(f"LLM responded in {time.time() - _t0:.1f}s ({len(raw)} chars)")
    data = parse_json_object(raw)

    # Enforce narrative_arc must match content_brief — override in code, not just prompt
    data["narrative_arc"] = content_brief.narrative_arc

    # Strip computed fields if LLM included them
    data.pop("passes", None)
    data.pop("overall_score", None)

    # Coerce lead_pain_point to min 10 words
    lpp = str(data.get("lead_pain_point", "")).strip()
    if len(lpp.split()) < 10:
        data["lead_pain_point"] = (
            lpp + " — this repeated friction prevents teams from moving fast "
            "and shipping with confidence."
        )

    # Coerce primary_claim to max 200 chars and single sentence
    pc = str(data.get("primary_claim", "")).strip()
    if len(pc) > 195:
        # Truncate at last full stop or comma before 195
        cut = pc[:195]
        for sep in (".", ",", " "):
            idx = cut.rfind(sep)
            if idx > 100:
                cut = cut[:idx + 1].strip()
                break
        data["primary_claim"] = cut
    # Remove trailing sentences (multi-sentence guard)
    import re as _re
    pc2 = str(data.get("primary_claim", ""))
    first_sent = _re.split(r"(?<=[.!?])\s+[A-Z]", pc2)
    if len(first_sent) > 1:
        data["primary_claim"] = first_sent[0].strip()

    # Normalize proof_point_type — infer from matched proof_point when LLM returns null
    _VALID_PP_TYPES = {
        "stat", "customer_name", "g2_badge", "integration_count",
        "uptime_claim", "award", "user_count",
    }
    ppt = data.get("proof_point_type")
    if ppt not in _VALID_PP_TYPES:
        # Try to match from ProductKnowledge proof_points
        selected_pp = data.get("proof_point", "")
        matched_type = None
        for pp in product_knowledge.proof_points:
            if pp.text == selected_pp or pp.text in selected_pp:
                matched_type = pp.proof_type
                break
        data["proof_point_type"] = matched_type if matched_type in _VALID_PP_TYPES else "stat"

    # Null out differentiator if it's too short — validator requires >= 10 words when not null
    diff = data.get("differentiator")
    if diff is not None and len(str(diff).split()) < 10:
        data["differentiator"] = None

    # LLM may echo reserved / server-set fields — never duplicate constructor kwargs
    for _reserved in ("run_id", "org_id", "created_at", "knowledge_context_applied"):
        data.pop(_reserved, None)

    strategy_brief = StrategyBrief(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        knowledge_context_applied=False,
        **data,
    )

    # Cross-schema validation — log warnings but do NOT crash pipeline
    try:
        strategy_brief.validate_against_product_knowledge(product_knowledge)
    except ValueError as exc:
        logger.warning("Strategy: product_knowledge validation warning: %s", exc)

    try:
        strategy_brief.validate_against_content_brief(content_brief)
    except ValueError as exc:
        logger.warning("Strategy: content_brief validation warning: %s", exc)

    return strategy_brief
