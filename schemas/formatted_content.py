"""
schemas/formatted_content.py
Genate — FormattedContent Schema
Produced by: Formatter agent (Step 8)
Consumed by: Evaluator (Step 9), Frontend inline editor, Knowledge Layer Persist
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

Platform = Literal["linkedin", "twitter", "instagram", "blog"]


# ---------------------------------------------------------------------------
# Platform-specific nested models
# ---------------------------------------------------------------------------

class LinkedInContent(BaseModel):
    hook: str = Field(
        ...,
        max_length=180,
        description=(
            "Standalone hook. Must work as a complete statement in ≤180 chars. "
            "This is the text visible before 'see more' on LinkedIn."
        ),
    )
    body: str = Field(..., description="Full post body excluding hook and hashtags.")
    hashtags: list[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3–5 hashtags. Placed at end only — never inline.",
    )
    full_post: str = Field(
        ...,
        description="Complete assembled post: hook + body + hashtags.",
    )

    @field_validator("hashtags")
    @classmethod
    def validate_hashtag_format(cls, v: list[str]) -> list[str]:
        for tag in v:
            if not tag.startswith("#"):
                raise ValueError(f"Hashtag '{tag}' must start with '#'.")
        return v

    @field_validator("hook")
    @classmethod
    def validate_hook_length(cls, v: str) -> str:
        if len(v) > 180:
            raise ValueError(
                f"LinkedIn hook must be ≤180 characters. Got {len(v)}."
            )
        return v


class PollContent(BaseModel):
    """Output for LinkedIn poll and Twitter poll content types."""

    intro: str | None = Field(
        None,
        max_length=200,
        description="Optional 1-2 sentence context. LinkedIn only — null for Twitter polls.",
    )
    question: str = Field(
        ...,
        max_length=150,
        description="The poll question. Max 150 chars.",
    )
    options: list[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Exactly 4 poll options. Each option max 25 characters.",
    )
    duration: str | None = Field(
        None,
        description="Poll duration (LinkedIn only): '1 day' | '3 days' | '1 week' | '2 weeks'.",
    )

    @field_validator("options")
    @classmethod
    def validate_option_lengths(cls, v: list[str]) -> list[str]:
        for i, opt in enumerate(v):
            if len(opt) > 25:
                raise ValueError(
                    f"Poll option {i + 1} exceeds 25 characters ({len(opt)} chars): '{opt}'"
                )
        return v

    @field_validator("question")
    @classmethod
    def validate_question_length(cls, v: str) -> str:
        if len(v) > 150:
            raise ValueError(f"Poll question must be ≤150 characters. Got {len(v)}.")
        return v


class InstagramStoryContent(BaseModel):
    """Output for Instagram story content type."""

    hook: str = Field(
        ...,
        max_length=80,
        description="Main text overlay on the story slide. Max 80 chars — punchy, complete thought.",
    )
    cta_text: str = Field(
        ...,
        max_length=25,
        description="Call-to-action text, e.g. 'Swipe up', 'Link in bio'. Max 25 chars.",
    )

    @field_validator("hook")
    @classmethod
    def validate_hook_length(cls, v: str) -> str:
        if len(v) > 80:
            raise ValueError(f"Story hook must be ≤80 characters. Got {len(v)}.")
        return v

    @field_validator("cta_text")
    @classmethod
    def validate_cta_length(cls, v: str) -> str:
        if len(v) > 25:
            raise ValueError(f"Story cta_text must be ≤25 characters. Got {len(v)}.")
        return v


class TwitterContent(BaseModel):
    tweets: list[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description=(
            "Tweet thread (4–8 tweets) or single tweet (1 tweet). "
            "Each tweet is a separate, self-contained idea."
        ),
    )
    tweet_char_counts: list[int] = Field(
        ...,
        description=(
            "Character count per tweet. Computed in code — never trusted from LLM. "
            "len(tweet_char_counts) must equal len(tweets)."
        ),
    )
    hashtags: list[str] = Field(
        ...,
        min_length=1,
        max_length=2,
        description="1–2 hashtags. In final tweet only — never in tweets 1 through N-1.",
    )

    @model_validator(mode="after")
    def validate_tweet_char_counts_match(self) -> "TwitterContent":
        if len(self.tweet_char_counts) != len(self.tweets):
            raise ValueError(
                f"tweet_char_counts length ({len(self.tweet_char_counts)}) must equal "
                f"tweets length ({len(self.tweets)})."
            )
        return self

    @model_validator(mode="after")
    def compute_and_validate_char_counts(self) -> "TwitterContent":
        """Recompute tweet_char_counts from tweets — never trust LLM-provided values."""
        computed = [len(t) for t in self.tweets]
        self.tweet_char_counts = computed
        for i, (tweet, count) in enumerate(zip(self.tweets, computed)):
            if count > 280:
                raise ValueError(
                    f"Tweet {i + 1} exceeds 280 characters ({count} chars): "
                    f"'{tweet[:50]}...'"
                )
        return self

    @model_validator(mode="after")
    def validate_first_tweet_standalone(self) -> "TwitterContent":
        """For threads, tweet 1 must be at least 60 chars — proxy for a standalone complete thought.
        Single tweets (len==1) are exempt from this check."""
        if len(self.tweets) > 1 and self.tweets and len(self.tweets[0]) < 60:
            raise ValueError(
                "Tweet 1 must work as a standalone statement. "
                f"Current length is only {len(self.tweets[0])} chars."
            )
        return self

    @field_validator("hashtags")
    @classmethod
    def validate_hashtag_format(cls, v: list[str]) -> list[str]:
        for tag in v:
            if not tag.startswith("#"):
                raise ValueError(f"Hashtag '{tag}' must start with '#'.")
        return v


class InstagramContent(BaseModel):
    preview_text: str = Field(
        ...,
        max_length=125,
        description=(
            "First 125 characters — must be a complete emotional statement. "
            "This is the text visible before 'more' is clicked."
        ),
    )
    body: str = Field(..., description="Full caption body after preview_text.")
    hashtags: list[str] = Field(
        ...,
        min_length=20,
        max_length=30,
        description="20–30 hashtags placed after exactly 5 blank line breaks.",
    )
    full_caption: str = Field(
        ...,
        description="Complete assembled caption: preview_text + body + 5 line breaks + hashtags.",
    )

    @field_validator("preview_text")
    @classmethod
    def validate_preview_text_length(cls, v: str) -> str:
        if len(v) > 125:
            raise ValueError(
                f"Instagram preview_text must be ≤125 characters. Got {len(v)}."
            )
        return v

    @field_validator("hashtags")
    @classmethod
    def validate_hashtag_format(cls, v: list[str]) -> list[str]:
        for tag in v:
            if not tag.startswith("#"):
                raise ValueError(f"Hashtag '{tag}' must start with '#'.")
        return v

    @model_validator(mode="after")
    def validate_full_caption_structure(self) -> "InstagramContent":
        """full_caption must contain exactly 5 consecutive newlines before hashtags."""
        if "\n\n\n\n\n" not in self.full_caption:
            raise ValueError(
                "full_caption must contain exactly 5 blank line breaks "
                "before hashtag block."
            )
        return self


class BlogContent(BaseModel):
    title: str = Field(..., description="H1 title of the blog post.")
    meta_title: str = Field(
        ...,
        min_length=50,
        max_length=60,
        description="SEO meta title. Must be 50–60 characters.",
    )
    meta_description: str = Field(
        ...,
        min_length=140,
        max_length=160,
        description="SEO meta description. Must be 140–160 characters.",
    )
    body: str = Field(
        ...,
        description=(
            "Full blog body with H1/H2 structure and [INTERNAL_LINK: topic] placeholders. "
            "Must contain SEO keyword in first 100 words."
        ),
    )
    word_count: int = Field(
        ...,
        ge=1200,
        le=2500,
        description="Word count of body. Must be 1200–2500.",
    )
    internal_link_placeholders: list[str] = Field(
        default_factory=list,
        description="All [INTERNAL_LINK: topic] placeholders found in body.",
    )
    seo_keyword: str = Field(
        ...,
        description="Primary SEO keyword. Must appear in first 100 words of body.",
    )

    @model_validator(mode="after")
    def validate_seo_keyword_placement(self) -> "BlogContent":
        """SEO keyword must appear in first 100 words of body."""
        first_100_words = " ".join(self.body.split()[:100]).lower()
        if self.seo_keyword.lower() not in first_100_words:
            raise ValueError(
                f"seo_keyword '{self.seo_keyword}' not found in first 100 words of body. "
                "Per platform rules, the keyword must appear in the first 100 words."
            )
        return self

    @model_validator(mode="after")
    def validate_word_count_matches_body(self) -> "BlogContent":
        """word_count must match actual body word count."""
        actual = len(self.body.split())
        if abs(actual - self.word_count) > 50:
            raise ValueError(
                f"word_count={self.word_count} does not match actual body word count "
                f"({actual}). Difference exceeds 50-word tolerance."
            )
        return self


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class FormattedContent(BaseModel):
    # Shared pipeline fields
    run_id: str = Field(..., description="UUID of the pipeline run.")
    org_id: str | None = Field(
        None,
        description="Clerk organisation ID. Null when Knowledge Layer disabled.",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")

    # Platform
    platform: Platform

    # Platform-specific content — exactly one must be non-null
    linkedin_content: LinkedInContent | None = None
    twitter_content: TwitterContent | None = None
    instagram_content: InstagramContent | None = None
    blog_content: BlogContent | None = None
    # Structured content types (poll, story) — replace the main field for their platform
    linkedin_poll_content: PollContent | None = None
    twitter_poll_content: PollContent | None = None
    instagram_story_content: InstagramStoryContent | None = None

    # Visual Gen outputs
    image_prompt: str | None = Field(
        None,
        description=(
            "Image generation prompt using exact brand parameters. "
            "Output of Visual Gen agent (Step 7)."
        ),
    )
    suggested_format: Literal["static", "carousel", "video", "ugc"] | None = Field(
        None,
        description="Suggested visual format from Visual Gen agent.",
    )
    video_script: str | None = Field(
        None,
        description=(
            "30–60 second video script following the narrative arc. "
            "Phase 2+ feature."
        ),
    )
    video_hook: str | None = Field(
        None,
        description="First 3 seconds of the video script.",
    )

    # Retry tracking
    retry_count: int = Field(
        default=0,
        ge=0,
        le=2,
        description="Number of Formatter retries on this run. Max 2.",
    )
    revision_hint_applied: str | None = Field(
        None,
        description=(
            "The revision_hint from EvaluatorOutput that triggered this retry. "
            "Null on first attempt."
        ),
    )

    # Approval loop — set only by POST /runs/{id}/approve, never by Formatter/Evaluator
    approved: bool = Field(
        default=False,
        description="Set to True only by POST /runs/{id}/approve endpoint.",
    )
    approved_at: str | None = Field(
        None,
        description="ISO 8601 timestamp. Must be non-null when approved=True.",
    )
    user_edited_copy: str | None = Field(
        None,
        description=(
            "The user-edited copy captured before approval. "
            "This is what gets stored in Supabase and Qdrant — not the original generated copy."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def enforce_platform_content_exclusivity(self) -> "FormattedContent":
        """Exactly one platform content field must be non-null."""
        content_fields = {
            "linkedin_content": self.linkedin_content,
            "twitter_content": self.twitter_content,
            "instagram_content": self.instagram_content,
            "blog_content": self.blog_content,
            "linkedin_poll_content": self.linkedin_poll_content,
            "twitter_poll_content": self.twitter_poll_content,
            "instagram_story_content": self.instagram_story_content,
        }
        non_null = [k for k, v in content_fields.items() if v is not None]

        if len(non_null) == 0:
            raise ValueError(
                "Exactly one platform content field must be non-null. "
                "Got zero non-null content fields."
            )
        if len(non_null) > 1:
            raise ValueError(
                f"Exactly one platform content field must be non-null. "
                f"Got {len(non_null)}: {non_null}"
            )
        return self

    @model_validator(mode="after")
    def enforce_platform_content_match(self) -> "FormattedContent":
        """The non-null content field must belong to the declared platform."""
        platform_to_fields = {
            "linkedin": ("linkedin_content", "linkedin_poll_content"),
            "twitter": ("twitter_content", "twitter_poll_content"),
            "instagram": ("instagram_content", "instagram_story_content"),
            "blog": ("blog_content",),
        }
        valid_fields = platform_to_fields[self.platform]
        has_match = any(getattr(self, f) is not None for f in valid_fields)
        if not has_match:
            raise ValueError(
                f"platform='{self.platform}' but none of {valid_fields} is set. "
                "The content field must match the platform."
            )
        return self

    @model_validator(mode="after")
    def enforce_approval_timestamp(self) -> "FormattedContent":
        """approved_at must be non-null when approved=True."""
        if self.approved and self.approved_at is None:
            raise ValueError(
                "approved_at must be set when approved=True. "
                "This field is set by POST /runs/{id}/approve."
            )
        return self

    @model_validator(mode="after")
    def enforce_retry_count_ceiling(self) -> "FormattedContent":
        """retry_count ceiling is enforced at the schema level."""
        if self.retry_count > 2:
            raise ValueError(
                f"retry_count cannot exceed 2. Got {self.retry_count}. "
                "MAX_EVAL_RETRIES=2 is a hard ceiling."
            )
        return self
