"""
schemas/product_knowledge.py
Genate — ProductKnowledge Schema

Produced by: Product Analysis agent (Step 3)
Consumed by: Planner (Step 4), Strategy (Step 5), Copywriting (Step 6)
"""

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class Feature(BaseModel):
    name: str = Field(..., max_length=60, description="Feature name. Max 60 chars.")
    description: str = Field(
        ...,
        max_length=150,
        description="What the feature does (mechanism, not benefit). Max 150 chars.",
    )


class ProofPoint(BaseModel):
    text: str = Field(
        ...,
        description="Verbatim from source. Min 5 words, max 120 chars.",
    )
    proof_type: Literal[
        "stat",
        "customer_name",
        "g2_badge",
        "integration_count",
        "uptime_claim",
        "award",
        "user_count",
    ]
    source: Literal["scraped_page", "user_document", "inferred"]

    @field_validator("text")
    @classmethod
    def text_constraints(cls, v: str) -> str:
        words = len(v.split())
        if words < 5:
            raise ValueError(
                f"ProofPoint.text must be at least 5 words, got {words}: '{v}'"
            )
        if len(v) > 120:
            raise ValueError(
                f"ProofPoint.text must be at most 120 chars, got {len(v)}: '{v[:50]}...'"
            )
        return v


# Gap-filler singleton — used when no real proof points can be found.
_GAP_FILLER_PROOF_POINT = ProofPoint(
    text="No proof points found on source page or user document",
    proof_type="stat",
    source="inferred",
)


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------


class ProductKnowledge(BaseModel):
    # ── Shared pipeline fields ────────────────────────────────────────
    run_id: str = Field(..., description="UUID of the pipeline run.")
    org_id: str | None = Field(
        None, description="Clerk organisation ID. Null when Knowledge Layer disabled."
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")

    # ── Product identity ──────────────────────────────────────────────
    product_name: str
    product_url: str = Field(..., description="URL of the product page.")
    tagline: str | None = Field(
        None, description="Verbatim tagline from page. Never generated."
    )
    description: str = Field(
        ..., description="2–4 sentence product description. Min 30 words."
    )
    product_category: Literal[
        "developer-tool",
        "project-management",
        "fintech-saas",
        "hr-people",
        "data-analytics",
        "customer-success",
        "marketing-content",
        "security-compliance",
        "vertical-saas",
        "other",
    ]

    # ── Extracted knowledge ───────────────────────────────────────────
    features: list[Feature] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="What the product does (mechanisms). Min 2, max 10.",
    )
    benefits: list[str] = Field(
        ...,
        min_length=2,
        max_length=8,
        description="Outcomes for the user. Min 2, max 8.",
    )
    proof_points: list[ProofPoint] = Field(
        ...,
        min_length=1,
        description=(
            "Only explicitly stated evidence. Min 1 "
            "(gap-filler applied automatically if none found)."
        ),
    )
    pain_points: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Specific observable frictions. May be empty when the model omits them.",
    )
    messaging_angles: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Positioning angles; may be empty for downstream to infer.",
    )

    # ── Optional enrichment ───────────────────────────────────────────
    target_customer: str | None = None
    integrations: list[str] = Field(
        default_factory=list,
        description="Integration names. Always list[str] — not list[dict].",
    )

    # ── Pricing signals ───────────────────────────────────────────────
    pricing_mentioned: bool = False
    pricing_description: str | None = None

    # ── Data provenance ───────────────────────────────────────────────
    scrape_word_count: int = 0
    user_document_filename: str | None = None
    data_source: Literal[
        "scraped_only",
        "user_document_only",
        "scraped_and_user_document",
    ] = "scraped_only"

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("description")
    @classmethod
    def description_min_words(cls, v: str) -> str:
        words = len(v.split())
        if words < 30:
            raise ValueError(
                f"description must be at least 30 words, got {words}."
            )
        return v

    @field_validator("integrations", mode="before")
    @classmethod
    def coerce_integrations(cls, v: object) -> list[str]:
        """Defensively coerce list[dict] → list[str].
        LLMs sometimes return objects instead of plain strings.
        """
        if not isinstance(v, list):
            return []
        result: list[str] = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # Prefer common string-key candidates
                for key in ("name", "title", "label", "value", "id"):
                    if key in item and isinstance(item[key], str):
                        result.append(item[key])
                        break
                else:
                    # Fallback: first string value found
                    for val in item.values():
                        if isinstance(val, str):
                            result.append(val)
                            break
        return result

    @model_validator(mode="after")
    def apply_proof_point_gap_filler(self) -> "ProductKnowledge":
        """If no valid proof points survived, insert the standard gap-filler entry."""
        if not self.proof_points:
            self.proof_points = [_GAP_FILLER_PROOF_POINT]
        return self
