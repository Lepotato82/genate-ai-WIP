"""
schemas/strategy_brief.py
Genate — StrategyBrief Schema
Produced by: Strategy agent (Step 5)
Consumed by: Copywriting agent (Step 6), Evaluator (Step 9), Knowledge Layer Persist
"""

from typing import Literal, TYPE_CHECKING
from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from schemas.product_knowledge import ProductKnowledge
    from schemas.content_brief import ContentBrief

# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

NarrativeArc = Literal[
    "pain-agitate-solve-cta",
    "before-after-bridge-cta",
    "stat-hook-problem-solution-cta",
]

ProofPointType = Literal[
    "stat",
    "customer_name",
    "g2_badge",
    "integration_count",
    "uptime_claim",
    "award",
    "user_count",
]

CtaIntent = Literal["start_trial", "learn_more", "book_demo", "sign_up"]

AppealType = Literal["rational", "emotional", "mixed"]

PositioningMode = Literal[
    "category_creation",
    "category_challenging",
    "category_domination",
]

# Fallback string used when no proof points are available
_NO_PROOF_FALLBACK = "No verified proof points available for this product"


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class StrategyBrief(BaseModel):
    # Shared pipeline fields
    run_id: str = Field(..., description="UUID of the pipeline run.")
    org_id: str | None = Field(
        None,
        description="Clerk organisation ID. Null when Knowledge Layer disabled.",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")

    # Core strategy fields
    lead_pain_point: str = Field(
        ...,
        description=(
            "Specific daily friction that opens the content. "
            "Must describe a concrete, observable moment of pain. Min 10 words."
        ),
    )
    primary_claim: str = Field(
        ...,
        max_length=200,
        description=(
            "Single outcome the product delivers. One sentence only. "
            "Must be verifiable from ProductKnowledge. Max 25 words."
        ),
    )
    proof_point: str = Field(
        ...,
        description=(
            "Must be copied verbatim from ProductKnowledge.proof_points[].text. "
            f"When no proof points exist, set to: '{_NO_PROOF_FALLBACK}'."
        ),
    )
    proof_point_type: ProofPointType = Field(
        ...,
        description="Must match the proof_type of the selected ProductKnowledge entry.",
    )
    cta_intent: CtaIntent
    appeal_type: AppealType
    narrative_arc: NarrativeArc = Field(
        ...,
        description="Must match ContentBrief.narrative_arc exactly.",
    )
    target_icp_role: str = Field(
        ...,
        min_length=3,
        description="Specific job title or role. Must describe a person — not a company type.",
    )
    differentiator: str | None = Field(
        None,
        description=(
            "The 'unlike X' or 'the only' angle. "
            "Min 10 words when not null. Null if no clear differentiator in source data."
        ),
    )
    hook_direction: str = Field(
        ...,
        description=(
            "One-sentence instruction to the Copywriting agent on how to open the content. "
            "Not the hook itself — the direction for writing it."
        ),
    )
    positioning_mode: PositioningMode
    messaging_angle_used: str = Field(
        ...,
        description=(
            "Must match one entry in ProductKnowledge.messaging_angles exactly."
        ),
    )
    knowledge_context_applied: bool = Field(
        ...,
        description=(
            "True if KnowledgeContext from previous approved runs influenced "
            "this strategy."
        ),
    )

    # ------------------------------------------------------------------
    # Field-level validators
    # ------------------------------------------------------------------

    @field_validator("lead_pain_point")
    @classmethod
    def validate_lead_pain_point_length(cls, v: str) -> str:
        words = v.split()
        if len(words) < 10:
            raise ValueError(
                f"lead_pain_point must be at least 10 words. "
                f"Got {len(words)}: '{v}'"
            )
        return v

    @field_validator("primary_claim")
    @classmethod
    def validate_primary_claim_single_sentence(cls, v: str) -> str:
        """
        Reject if the string contains more than one terminal punctuation
        followed by a capital letter — proxy for multiple sentences.
        """
        import re
        if re.search(r"[.!?]\s+[A-Z]", v):
            raise ValueError(
                "primary_claim must be a single sentence. "
                "Found what appears to be multiple sentences."
            )
        return v

    @field_validator("differentiator")
    @classmethod
    def validate_differentiator_length(cls, v: str | None) -> str | None:
        if v is not None:
            words = v.split()
            if len(words) < 10:
                raise ValueError(
                    f"differentiator must be at least 10 words when not null. "
                    f"Got {len(words)}: '{v}'"
                )
        return v

    # ------------------------------------------------------------------
    # Cross-schema validators
    # These are called explicitly from pipeline.py after instantiation
    # because Pydantic v2 model_validators cannot receive external objects.
    # ------------------------------------------------------------------

    def validate_against_product_knowledge(
        self,
        product_knowledge: "ProductKnowledge",
    ) -> None:
        """
        Cross-schema contract validation.
        Call this from pipeline.py after StrategyBrief is instantiated:

            strategy_brief.validate_against_product_knowledge(product_knowledge)

        Raises ValueError on any violation.
        """
        proof_texts = [p.text for p in product_knowledge.proof_points]

        # Proof point must match verbatim OR be the standard fallback
        if (
            self.proof_point != _NO_PROOF_FALLBACK
            and self.proof_point not in proof_texts
        ):
            raise ValueError(
                f"proof_point '{self.proof_point}' does not match any entry in "
                f"ProductKnowledge.proof_points. "
                f"Valid values: {proof_texts}. "
                f"Copy the proof point text verbatim."
            )

        # proof_point_type must match the matched entry's type
        if self.proof_point != _NO_PROOF_FALLBACK:
            matched = next(
                (p for p in product_knowledge.proof_points if p.text == self.proof_point),
                None,
            )
            if matched and matched.proof_type != self.proof_point_type:
                raise ValueError(
                    f"proof_point_type='{self.proof_point_type}' does not match "
                    f"the proof_type='{matched.proof_type}' of the matched "
                    f"ProductKnowledge entry."
                )

        # messaging_angle_used must match an entry when angles exist
        if product_knowledge.messaging_angles and (
            self.messaging_angle_used not in product_knowledge.messaging_angles
        ):
            raise ValueError(
                f"messaging_angle_used='{self.messaging_angle_used}' does not match "
                f"any entry in ProductKnowledge.messaging_angles. "
                f"Valid values: {product_knowledge.messaging_angles}"
            )

    def validate_against_content_brief(
        self,
        content_brief: "ContentBrief",
    ) -> None:
        """
        Cross-schema contract: narrative_arc must match ContentBrief.narrative_arc.
        Call this from pipeline.py after StrategyBrief is instantiated:

            strategy_brief.validate_against_content_brief(content_brief)

        Raises ValueError on any violation.
        """
        if self.narrative_arc != content_brief.narrative_arc:
            raise ValueError(
                f"StrategyBrief.narrative_arc='{self.narrative_arc}' does not match "
                f"ContentBrief.narrative_arc='{content_brief.narrative_arc}'. "
                f"The Strategy agent must use the arc selected by the Planner."
            )
