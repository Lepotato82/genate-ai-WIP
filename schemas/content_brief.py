"""
schemas/content_brief.py
Genate — ContentBrief Schema
Produced by: Planner agent (Step 4)
Consumed by: Strategy agent (Step 5)
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

Platform = Literal["linkedin", "twitter", "instagram", "blog"]

NarrativeArc = Literal[
    "pain-agitate-solve-cta",
    "before-after-bridge-cta",
    "stat-hook-problem-solution-cta",
]

ContentPillar = Literal[
    "pain_and_problem",
    "education_and_insight",
    "product_and_solution",
    "social_proof",
    "founder_team_voice",
]

FunnelStage = Literal["tofu", "mofu", "bofu"]

ContentType = Literal[
    # linkedin
    "carousel",
    "text_post",
    "multi_image",
    "short_video",
    "poll",
    "question_post",
    "single_image",
    # twitter
    "thread",
    "single_tweet",
    # instagram
    "reel",
    "story",
    "collab_post",
    # blog
    "how_to",
    "case_study",
    "thought_leadership",
    "product_led_seo",
    "comparison",
    "listicle",
    "original_research",
    "use_case",
    "glossary",
    "checklist",
    "changelog",
]

# ---------------------------------------------------------------------------
# Platform compatibility map
# ---------------------------------------------------------------------------

PLATFORM_CONTENT_TYPES: dict[str, set[str]] = {
    "linkedin":  {"carousel", "text_post", "multi_image", "short_video",
                  "poll", "question_post", "single_image"},
    "twitter":   {"thread", "single_tweet", "poll"},
    "instagram": {"carousel", "reel", "single_image", "story", "collab_post"},
    "blog":      {"how_to", "case_study", "thought_leadership", "product_led_seo",
                  "comparison", "listicle", "original_research", "use_case",
                  "glossary", "checklist", "changelog"},
}


# ---------------------------------------------------------------------------
# Nested model
# ---------------------------------------------------------------------------

class PostingStrategy(BaseModel):
    recommended_frequency: str = Field(
        ...,
        description="How often to post this content type (benchmark-based).",
    )
    best_days: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Best days to post. Min 1, max 5.",
    )
    best_time_window: str = Field(
        ...,
        description=(
            "Best time window in IST. "
            "Note if IST-specific data is unavailable and global benchmark was used."
        ),
    )


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class ContentBrief(BaseModel):
    # Shared pipeline fields
    run_id: str = Field(..., description="UUID of the pipeline run.")
    org_id: str | None = Field(
        None,
        description="Clerk organisation ID. Null when Knowledge Layer disabled.",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")

    # Core strategy fields
    platform: Platform
    content_type: ContentType
    narrative_arc: NarrativeArc
    content_pillar: ContentPillar
    funnel_stage: FunnelStage
    content_depth: Literal["concise", "long_form"] = Field(
        "concise",
        description=(
            "Copy depth selected by the Planner. "
            "'concise' = platform-native short form (LinkedIn 150-300w, Twitter 4-6 tweets, Instagram 80-150w body). "
            "'long_form' = richer depth (LinkedIn 600-900w, Twitter 6-8 tweets, Instagram 250-400w body)."
        ),
    )
    posting_strategy: PostingStrategy

    # Conditional length/format fields
    word_count_target: int | None = Field(
        None,
        ge=1200,
        le=2500,
        description="Required when platform == 'blog'. Must be 1200–2500.",
    )
    slide_count_target: int | None = Field(
        None,
        ge=6,
        le=10,
        description="Required when content_type == 'carousel'. Must be 6–10.",
    )
    thread_length_target: int | None = Field(
        None,
        ge=4,
        le=8,
        description="Required when content_type == 'thread'. Must be 4–8.",
    )

    # Platform rules summary
    platform_rules_summary: list[str] = Field(
        ...,
        min_length=2,
        description=(
            "Structural rules from platform_rules.json that the Formatter "
            "will enforce. Min 2 entries."
        ),
    )

    # Blog-specific
    seo_keyword: str | None = Field(
        None,
        description=(
            "Required when platform == 'blog'. "
            "Must appear in first 100 words of generated post."
        ),
    )

    # Knowledge layer
    knowledge_context_used: bool = Field(
        ...,
        description="True if Knowledge Layer context influenced this ContentBrief.",
    )
    knowledge_context_summary: str | None = Field(
        None,
        description="1–2 sentence summary of applied context. Null when unused.",
    )

    # Benchmark reference
    benchmark_reference: str = Field(
        ...,
        description=(
            "The specific benchmark stat from saas_engagement_benchmarks.md "
            "that informed this content type selection."
        ),
    )

    reasoning: str = Field(
        ...,
        min_length=20,
        description=(
            "Planner justification for content_type. Must reference signals "
            "(counts, brand_tone, proof types) supplied to the Planner."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def enforce_twitter_thread(self) -> "ContentBrief":
        """Twitter platform requires content_type='thread'. Mandatory constraint."""
        if self.platform == "twitter" and self.content_type != "thread":
            raise ValueError(
                "Twitter platform requires content_type='thread'. "
                "This is a mandatory constraint per pipeline design."
            )
        return self

    @model_validator(mode="after")
    def enforce_platform_compatibility(self) -> "ContentBrief":
        """Reject invalid platform / content_type combinations immediately."""
        valid = PLATFORM_CONTENT_TYPES.get(self.platform, set())
        if self.content_type not in valid:
            raise ValueError(
                f"content_type='{self.content_type}' is not valid for "
                f"platform='{self.platform}'. "
                f"Valid types: {sorted(valid)}"
            )
        return self

    @model_validator(mode="after")
    def enforce_blog_fields(self) -> "ContentBrief":
        """word_count_target and seo_keyword are required for blog, null otherwise."""
        if self.platform == "blog":
            if self.word_count_target is None:
                raise ValueError(
                    "word_count_target is required when platform='blog'. "
                    "Must be 1200–2500."
                )
            if self.seo_keyword is None:
                raise ValueError(
                    "seo_keyword is required when platform='blog'."
                )
        else:
            if self.word_count_target is not None:
                raise ValueError(
                    "word_count_target must be null for non-blog platforms."
                )
            if self.seo_keyword is not None:
                raise ValueError(
                    "seo_keyword must be null for non-blog platforms."
                )
        return self

    @model_validator(mode="after")
    def enforce_carousel_slide_count(self) -> "ContentBrief":
        """slide_count_target is required for carousel, null otherwise."""
        if self.content_type == "carousel":
            if self.slide_count_target is None:
                raise ValueError(
                    "slide_count_target is required when content_type='carousel'. "
                    "Must be 6–10."
                )
        else:
            if self.slide_count_target is not None:
                raise ValueError(
                    "slide_count_target must be null for non-carousel content types."
                )
        return self

    @model_validator(mode="after")
    def enforce_thread_length(self) -> "ContentBrief":
        """thread_length_target is required for thread, null otherwise."""
        if self.content_type == "thread":
            if self.thread_length_target is None:
                raise ValueError(
                    "thread_length_target is required when content_type='thread'. "
                    "Must be 4–8."
                )
        else:
            if self.thread_length_target is not None:
                raise ValueError(
                    "thread_length_target must be null for non-thread content types."
                )
        return self

    @model_validator(mode="after")
    def enforce_knowledge_context_summary(self) -> "ContentBrief":
        """knowledge_context_summary must be null when knowledge_context_used=False."""
        if not self.knowledge_context_used and self.knowledge_context_summary is not None:
            raise ValueError(
                "knowledge_context_summary must be null when "
                "knowledge_context_used=False."
            )
        return self
