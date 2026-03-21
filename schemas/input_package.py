"""
schemas/input_package.py
Genate — InputPackage

Internal struct produced by: Input Processor agent (Step 1)
Consumed by: UI Analyzer (Step 2) and Product Analysis (Step 3)

NOT a Pydantic output schema. NOT persisted. NOT returned from the API.
"""

from typing import Literal

from pydantic import BaseModel, Field


class InputPackage(BaseModel):
    # Core request identifiers
    url: str
    run_id: str = Field(..., description="UUID set by pipeline.py at run start.")
    org_id: str | None = Field(None, description="Clerk organisation ID.")

    # Scraped content
    scraped_text: str = Field(default="", description="Rendered text from Playwright.")
    css_tokens: dict[str, str] = Field(
        default_factory=dict,
        description="CSS custom properties from getComputedStyle() on :root.",
    )

    # Visual assets
    screenshot_bytes: bytes | None = None
    og_image_bytes: bytes | None = None
    og_image_url: str | None = None

    # User uploads (highest priority)
    user_image: bytes | None = None
    user_document: str | None = None

    # Provenance and diagnostics
    scrape_error: str | None = None
    scrape_word_count: int = Field(
        default=0, description="Word count of scraped_text."
    )

    model_config = {"arbitrary_types_allowed": True}

    # ------------------------------------------------------------------
    # Priority accessors
    # ------------------------------------------------------------------

    def get_primary_image(self) -> bytes | None:
        """Return the best available image.
        Priority: user_image > og_image_bytes > screenshot_bytes
        """
        if self.user_image is not None:
            return self.user_image
        if self.og_image_bytes is not None:
            return self.og_image_bytes
        if self.screenshot_bytes is not None:
            return self.screenshot_bytes
        return None

    def get_primary_text(self) -> str:
        """Return the best available text.
        Priority: user_document (non-blank) > scraped_text
        """
        if self.user_document and self.user_document.strip():
            return self.user_document
        return self.scraped_text

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def has_visual(self) -> bool:
        """True if any image is available."""
        return self.get_primary_image() is not None

    @property
    def has_text(self) -> bool:
        """True if any non-blank text is available."""
        return len(self.get_primary_text().strip()) > 0

    @property
    def data_source(self) -> Literal[
        "user_document_only", "scraped_and_user_document", "scraped_only"
    ]:
        """Classify the data origin for downstream provenance tracking."""
        has_doc = bool(self.user_document and self.user_document.strip())
        has_scraped = bool(self.scraped_text and self.scraped_text.strip())

        if has_doc and not has_scraped:
            return "user_document_only"
        if has_doc and has_scraped:
            return "scraped_and_user_document"
        return "scraped_only"
