"""
schemas/evaluator_output.py
Genate — EvaluatorOutput Schema
Produced by: Evaluator agent (Step 9)
Consumed by: Formatter (Step 8 — on retry), pipeline.py (pass/fail gate), Frontend

Critical constraints:
  - `passes` is COMPUTED by model_validator — never set by the LLM
  - `overall_score` is COMPUTED by model_validator — never set by the LLM
  - `revision_hint` is required when passes=False, null when passes=True
  - `lowest_dimension` is required when passes=False, null when passes=True
  - retry_count ceiling is 2 — enforced here and in pipeline.py
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

Platform = Literal["linkedin", "twitter", "instagram", "blog"]

ScoreDimension = Literal["clarity", "engagement", "tone_match", "accuracy"]

# Priority order for lowest_dimension tiebreaking (highest priority first)
_DIMENSION_PRIORITY: list[str] = ["accuracy", "tone_match", "engagement", "clarity"]


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class EvaluatorOutput(BaseModel):
    # Shared pipeline fields
    run_id: str = Field(..., description="UUID of the pipeline run.")
    org_id: str | None = Field(
        None,
        description="Clerk organisation ID. Null when Knowledge Layer disabled.",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")

    # Platform
    platform: Platform = Field(
        ...,
        description="Passed through from FormattedContent.platform.",
    )

    # Scores — LLM outputs these four only
    clarity: int = Field(..., ge=1, le=5, description="Clarity score 1–5.")
    engagement: int = Field(..., ge=1, le=5, description="Engagement score 1–5.")
    tone_match: int = Field(..., ge=1, le=5, description="Tone match score 1–5.")
    accuracy: int = Field(..., ge=1, le=5, description="Accuracy score 1–5.")

    # Computed — never set by the LLM
    overall_score: float = Field(
        default=0.0,
        description=(
            "Computed: (clarity + engagement + tone_match + accuracy) / 4.0, "
            "rounded to 2 decimal places. Never set by the LLM."
        ),
    )
    passes: bool = Field(
        default=False,
        description=(
            "Computed: True only when ALL FOUR scores >= 3. "
            "Never set by the LLM."
        ),
    )

    # Conditional fields
    revision_hint: str | None = Field(
        None,
        description=(
            "Required when passes=False. Specific, actionable rewrite instruction. "
            "Min 15 words, max 100 words. Targets lowest_dimension. "
            "Null when passes=True."
        ),
    )
    lowest_dimension: ScoreDimension | None = Field(
        None,
        description=(
            "The dimension with the lowest score. Required when passes=False. "
            "Tiebreak priority: accuracy > tone_match > engagement > clarity. "
            "Null when passes=True."
        ),
    )

    # Rationale
    scores_rationale: str = Field(
        ...,
        description=(
            "2–4 sentences referencing specific elements of the content. "
            "Logged to LangFuse and used for dataset collection."
        ),
    )

    # Retry tracking
    retry_count: int = Field(
        ...,
        ge=0,
        le=2,
        description=(
            "The retry count at the time of this evaluation. "
            "0 on first evaluation. MAX_EVAL_RETRIES=2."
        ),
    )

    # ------------------------------------------------------------------
    # Field-level validators — run before model validators
    # ------------------------------------------------------------------

    @field_validator("clarity", "engagement", "tone_match", "accuracy", mode="before")
    @classmethod
    def validate_score_is_integer(cls, v: object) -> int:
        """Reject floats — scores must be integers."""
        if isinstance(v, float) and not v.is_integer():
            raise ValueError(
                f"Score must be an integer 1–5. Got float: {v}"
            )
        return int(v)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Model validators — run after all fields are set
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def compute_passes_and_score(self) -> "EvaluatorOutput":
        """
        Compute passes and overall_score from the four dimension scores.
        These values are NEVER trusted from LLM output.
        """
        self.passes = (
            self.clarity >= 3
            and self.engagement >= 3
            and self.tone_match >= 3
            and self.accuracy >= 3
        )
        self.overall_score = round(
            (self.clarity + self.engagement + self.tone_match + self.accuracy) / 4.0,
            2,
        )
        return self

    @model_validator(mode="after")
    def compute_lowest_dimension(self) -> "EvaluatorOutput":
        """
        Compute lowest_dimension from scores.
        Tiebreak priority: accuracy > tone_match > engagement > clarity.
        Only set when passes=False.
        """
        if not self.passes:
            scores = {
                "accuracy": self.accuracy,
                "tone_match": self.tone_match,
                "engagement": self.engagement,
                "clarity": self.clarity,
            }
            min_score = min(scores.values())
            # Among all dimensions tied at the minimum, pick highest priority
            for dim in _DIMENSION_PRIORITY:
                if scores[dim] == min_score:
                    self.lowest_dimension = dim  # type: ignore[assignment]
                    break
        else:
            self.lowest_dimension = None
        return self

    @model_validator(mode="after")
    def enforce_revision_hint_mutual_exclusivity(self) -> "EvaluatorOutput":
        """
        revision_hint must be null when passes=True.
        revision_hint must be non-null (≥15 words) when passes=False.
        """
        if self.passes:
            if self.revision_hint is not None:
                raise ValueError(
                    "revision_hint must be null when passes=True."
                )
        else:
            if self.revision_hint is None:
                raise ValueError(
                    "revision_hint is required when passes=False. "
                    "Must be a specific, actionable rewrite instruction."
                )
            words = self.revision_hint.split()
            if len(words) < 15:
                raise ValueError(
                    f"revision_hint must be at least 15 words. "
                    f"Got {len(words)}: '{self.revision_hint}'"
                )
            if len(words) > 100:
                raise ValueError(
                    f"revision_hint must be at most 100 words. "
                    f"Got {len(words)}. Keep it concise and actionable."
                )
        return self

    @model_validator(mode="after")
    def enforce_scores_rationale_sentences(self) -> "EvaluatorOutput":
        """scores_rationale must contain at least 2 sentences."""
        import re
        sentences = re.split(r"[.!?]+", self.scores_rationale.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) < 2:
            raise ValueError(
                "scores_rationale must contain at least 2 sentences. "
                "It must reference specific elements of the content — not generic observations."
            )
        return self

    @model_validator(mode="after")
    def enforce_retry_count_ceiling(self) -> "EvaluatorOutput":
        """retry_count ceiling is 2 — hard ceiling from context doc."""
        if self.retry_count > 2:
            raise ValueError(
                f"retry_count cannot exceed 2. Got {self.retry_count}. "
                "MAX_EVAL_RETRIES=2 is a hard ceiling."
            )
        return self
