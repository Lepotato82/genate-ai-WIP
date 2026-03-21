"""
schemas/brand_profile.py
Genate — BrandProfile Schema

Produced by: UI Analyzer agent (Step 2)
Consumed by: Copywriting agent (Step 6), Visual Gen agent (Step 7)
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BrandProfile(BaseModel):
    # ── Shared pipeline fields ────────────────────────────────────────
    run_id: str = Field(..., description="UUID of the pipeline run.")
    org_id: str | None = Field(
        None, description="Clerk organisation ID. Null when Knowledge Layer disabled."
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")

    # ── Design classification ─────────────────────────────────────────
    design_category: Literal[
        "developer-tool",
        "minimal-saas",
        "bold-enterprise",
        "consumer-friendly",
        "data-dense",
    ] = Field(..., description="Visual design classification of the product.")

    # ── Colour palette ────────────────────────────────────────────────
    primary_color: str = Field(
        ..., description="Primary brand colour as hex (e.g. #5e6ad2)."
    )
    secondary_color: str | None = Field(
        None, description="Secondary brand colour as hex."
    )
    background_color: str | None = Field(
        None, description="Primary background colour as hex."
    )

    # ── Typography ────────────────────────────────────────────────────
    font_family: str | None = Field(None, description="Primary font family name.")
    font_weights: list[float] = Field(
        default_factory=list,
        description=(
            "Font weights in use. MUST be floats — CSS variable fonts use "
            "fractional values like 510.0 and 590.0."
        ),
    )

    # ── Spacing and shape ─────────────────────────────────────────────
    border_radius: str | None = Field(
        None, description="Primary border radius value (e.g. '6px')."
    )
    spacing_unit: str | None = Field(
        None, description="Base spacing unit (e.g. '4px')."
    )

    # ── Tone ──────────────────────────────────────────────────────────
    tone: Literal["technical", "playful", "corporate", "minimal", "bold"] = Field(
        ..., description="Brand tone classification."
    )

    # ── Copywriting injection ─────────────────────────────────────────
    writing_instruction: str = Field(
        ...,
        description=(
            "Minimum 15 words. Injected verbatim into the Copywriting agent system "
            "prompt. Must reference specific visual signals observed in the brand."
        ),
    )

    # ── Raw CSS token data ────────────────────────────────────────────
    css_tokens: dict[str, str] = Field(
        default_factory=dict,
        description="CSS custom properties extracted from :root.",
    )

    # ── Quality signal ────────────────────────────────────────────────
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in the brand classification (0.0–1.0).",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("writing_instruction")
    @classmethod
    def writing_instruction_min_words(cls, v: str) -> str:
        word_count = len(v.split())
        if word_count < 15:
            raise ValueError(
                f"writing_instruction must be at least 15 words, got {word_count}. "
                "It must reference specific visual signals observed in the brand."
            )
        return v
