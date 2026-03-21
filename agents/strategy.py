"""
Step 5: Strategy — StrategyBrief from content brief + product + brand.
"""

from __future__ import annotations

import json
import re

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief, _NO_PROOF_FALLBACK
from agents._utils import parse_json_object, utc_now_iso

_GAP_TEXT = "No proof points found on source page or user document"


def _real_proof_entries(pk: ProductKnowledge) -> list:
    return [p for p in pk.proof_points if p.text.strip() != _GAP_TEXT]


def _enforce_strategy(
    data: dict,
    content_brief: ContentBrief,
    product_knowledge: ProductKnowledge,
) -> dict:
    d = dict(data)
    d["narrative_arc"] = content_brief.narrative_arc

    real = _real_proof_entries(product_knowledge)
    texts = [p.text for p in real]

    if not real:
        d["proof_point"] = _NO_PROOF_FALLBACK
        d.setdefault("proof_point_type", "stat")
    else:
        if d.get("proof_point") not in texts:
            d["proof_point"] = real[0].text
        matched = next((p for p in real if p.text == d["proof_point"]), real[0])
        if matched.proof_type != d.get("proof_point_type"):
            d["proof_point_type"] = matched.proof_type

    angles = product_knowledge.messaging_angles
    if angles:
        if d.get("messaging_angle_used") not in angles:
            d["messaging_angle_used"] = angles[0]
    else:
        d["messaging_angle_used"] = (
            d.get("messaging_angle_used")
            or f"{product_knowledge.product_name} value for modern product teams"
        )

    icp = str(d.get("target_icp_role") or "").strip()
    if len(icp.split()) < 3:
        d["target_icp_role"] = "Senior engineering manager leading product delivery"

    pain = str(d.get("lead_pain_point") or "").strip()
    if len(pain.split()) < 10:
        d["lead_pain_point"] = (
            "Product and engineering teams still waste hours each week reconciling issue status, "
            "roadmap shifts, and stakeholder questions because their tools drift from ground truth."
        )

    claim = str(d.get("primary_claim") or "").strip()
    if re.search(r"[.!?]\s+[A-Z]", claim):
        claim = re.split(r"(?<=[.!?])\s+", claim)[0].strip()
    cw = claim.split()
    if len(cw) > 25:
        claim = " ".join(cw[:25]).rstrip(",;:") + "."
    d["primary_claim"] = claim

    diff = d.get("differentiator")
    if diff is not None and len(str(diff).split()) < 10:
        d["differentiator"] = None

    d["knowledge_context_applied"] = False
    return d


def _mock(content_brief: ContentBrief, pk: ProductKnowledge, brand: BrandProfile) -> StrategyBrief:
    real = _real_proof_entries(pk)
    if real:
        proof = real[0]
        proof_point = proof.text
        proof_point_type = proof.proof_type
    else:
        proof_point = _NO_PROOF_FALLBACK
        proof_point_type = "stat"
    angle = (
        pk.messaging_angles[0]
        if pk.messaging_angles
        else f"{pk.product_name} streamlines delivery for product and engineering teams"
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
            f"{pk.product_name} gives teams a fast issue tracker and roadmap that stays aligned "
            f"with how builders actually ship."
        ),
        proof_point=proof_point,
        proof_point_type=proof_point_type,
        cta_intent="learn_more",
        appeal_type="rational",
        narrative_arc=content_brief.narrative_arc,
        target_icp_role="Senior product engineering manager",
        differentiator=(
            "Unlike heavyweight enterprise suites that bury work in configuration, this product "
            "prioritizes speed, keyboard workflows, and a focused surface for shipping."
        ),
        hook_direction="Open with the weekly ritual of cleaning up statuses and duplicate tickets before leadership asks for a readout.",
        positioning_mode="category_challenging",
        messaging_angle_used=angle,
        knowledge_context_applied=False,
    )
    out.validate_against_product_knowledge(pk)
    out.validate_against_content_brief(content_brief)
    return out


def run(
    content_brief: ContentBrief,
    product_knowledge: ProductKnowledge,
    brand_profile: BrandProfile,
) -> StrategyBrief:
    if settings.MOCK_MODE:
        return _mock(content_brief, product_knowledge, brand_profile)

    spec = load_prompt("strategy_v1")
    user_msg = (
        f"content_brief.platform={content_brief.platform}\n"
        f"content_brief.narrative_arc={content_brief.narrative_arc}\n"
        f"content_brief.content_pillar={content_brief.content_pillar}\n\n"
        f"product_knowledge.pain_points:\n{json.dumps(product_knowledge.pain_points, indent=2)}\n\n"
        f"product_knowledge.messaging_angles:\n{json.dumps(product_knowledge.messaging_angles, indent=2)}\n\n"
        f"product_knowledge.proof_points:\n"
        f"{json.dumps([p.model_dump() for p in product_knowledge.proof_points], indent=2, default=str)}\n\n"
        f"product_knowledge.features:\n"
        f"{json.dumps([f.model_dump() for f in product_knowledge.features], indent=2, default=str)}\n\n"
        f"brand_profile.tone: {brand_profile.tone}\n"
        f"brand_profile.writing_instruction:\n{brand_profile.writing_instruction}\n\n"
        "Return only JSON as specified."
    )
    raw = chat_completion(
        [
            {"role": "system", "content": spec.system_prompt},
            {"role": "user", "content": user_msg},
        ]
    )
    data = parse_json_object(raw)
    data = _enforce_strategy(data, content_brief, product_knowledge)
    keys = (
        "lead_pain_point",
        "primary_claim",
        "proof_point",
        "proof_point_type",
        "cta_intent",
        "appeal_type",
        "narrative_arc",
        "target_icp_role",
        "differentiator",
        "hook_direction",
        "positioning_mode",
        "messaging_angle_used",
        "knowledge_context_applied",
    )
    payload = {k: data[k] for k in keys if k in data}
    strategy = StrategyBrief(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        **payload,
    )
    strategy.validate_against_product_knowledge(product_knowledge)
    strategy.validate_against_content_brief(content_brief)
    return strategy
