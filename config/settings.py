from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_ignore_empty=True,
    )

    # ─── Core ─────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    MOCK_MODE: bool = True

    # ─── LLM Routing ──────────────────────────────────────────────────────
    LLM_PROVIDER: str = "groq"              # groq | openai | anthropic | ollama
    LLM_VISION_PROVIDER: str = "anthropic"  # anthropic | ollama | openai
    LLM_TEXT_MODEL: str = "llama-3.2-90b-text-preview"   # Groq/OpenAI model name
    LLM_VISION_MODEL: str = "claude-haiku-4-5"           # Anthropic model name
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"  # must include /v1 for OpenAI SDK compat
    LLM_REQUEST_TIMEOUT: int = 90   # seconds — HTTP timeout per LLM call (prevents indefinite hangs)
    OLLAMA_TEXT_MODEL: str = "llama3.2:latest"    # Ollama model name for text agents
    OLLAMA_VISION_MODEL: str = "llava:latest"     # Ollama model name for vision (UI Analyzer)

    # ─── LLM API Keys ─────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # ─── Supabase ─────────────────────────────────────────────────────────
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""

    # ─── Qdrant ───────────────────────────────────────────────────────────
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_PREFIX: str = "genate"

    # ─── Auth (Clerk) ─────────────────────────────────────────────────────
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""

    # ─── Knowledge Layer ──────────────────────────────────────────────────
    KNOWLEDGE_LAYER_ENABLED: bool = False
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # ─── Research Augmentation ───────────────────────────────────────────
    RESEARCH_AUGMENTATION_ENABLED: bool = False
    TAVILY_API_KEY: str = ""
    TAVILY_MAX_RESULTS: int = 3       # results per query
    TAVILY_MAX_PROOF_POINTS: int = 5  # max stored across all queries

    # ─── Image Generation ─────────────────────────────────────────────────
    FAL_API_KEY: str = ""
    # Sync text-to-image (hero background). Uses FAL_API_KEY when HERO_IMAGE_PROVIDER=fal.
    FAL_HERO_MODEL_PATH: str = "fal-ai/flux/schnell"
    BANNERBEAR_API_KEY: str = ""
    BANNERBEAR_TEMPLATE_UID: str = ""
    BANNERBEAR_TIMEOUT_SECONDS: int = 30
    # Bannerbear carousel slides (flattened templates).
    IMAGE_GENERATION_ENABLED: bool = False
    # Text-to-image hero layer (Pollinations, Fal, etc.) — independent of Bannerbear.
    HERO_IMAGE_ENABLED: bool = False
    # pollinations | fal | none
    HERO_IMAGE_PROVIDER: str = "pollinations"
    POLLINATIONS_TIMEOUT_SECONDS: int = 240  # Pollinations often needs 60–180s+ to return image bytes
    POLLINATIONS_WIDTH: int = 0   # 0 = omit (API default)
    POLLINATIONS_HEIGHT: int = 0
    POLLINATIONS_MODEL: str = ""  # optional model query param for Pollinations
    IDEOGRAM_API_KEY: str = ""

    # Stock photo provider for hero images (consumer-friendly brands)
    # Pexels: free 200 req/hr, 20K/month, commercial use OK. Needs PEXELS_API_KEY.
    PEXELS_API_KEY: str = ""
    PEXELS_RESULTS_PER_QUERY: int = 5  # fetch N candidates, pick first usable

    # ─── Compositor (Pillow, fully local — no external API) ───────────────
    # Produces branded PNG images from brand colors + logo + copy text.
    # True by default: no credentials required, zero cost.
    COMPOSITOR_ENABLED: bool = True
    # Apply brand-color duotone to hero photos in photo_overlay / editorial_photo.
    # Desaturates the photo then tints with the brand primary — matches Lemon Health-style posts.
    COMPOSITOR_DUOTONE_ENABLED: bool = True
    # Halftone dot overlay on hero photos — editorial/risograph print feel.
    COMPOSITOR_PHOTO_TEXTURE_ENABLED: bool = True
    # Background removal on hero photos for cutout compositing (requires rembg).
    COMPOSITOR_CUTOUT_ENABLED: bool = True
    # Paste curated decorative illustrations (botanicals, geometric motifs) onto
    # opted-in layouts. Ships with assets/decorations/; no network calls.
    COMPOSITOR_DECORATIONS_ENABLED: bool = True

    # ─── Video Generation ─────────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = ""
    HEYGEN_API_KEY: str = ""

    # ─── Scraping ─────────────────────────────────────────────────────────
    BROWSERLESS_API_KEY: str = ""
    BRIGHTDATA_PROXY_URL: str = ""
    SCRAPE_TIMEOUT_SECONDS: int = 15
    SCRAPE_MAX_RETRIES: int = 2

    # ─── Logo extraction (local CLIP ViT — input_processor) ───────────────
    LOGO_CLIP_ENABLED: bool = True
    LOGO_CLIP_MIN_BOX_PX: int = 24
    LOGO_CLIP_MAX_BOX_W: int = 400
    LOGO_CLIP_MAX_BOX_H: int = 300
    LOGO_CLIP_MAX_ASPECT_RATIO: float = 6.0
    LOGO_BG_REMOVAL_ENABLED: bool = False
    LOGO_OCR_ENABLED: bool = False
    LOGO_OCR_LOGIT_BONUS: float = 0.15
    # og:image only — 0 disables. Use to skip hero-sized marketing images as "logos".
    LOGO_OG_IMAGE_MAX_BYTES: int = 500_000
    LOGO_OG_IMAGE_MAX_EDGE_PX: int = 0

    # ─── Observability ────────────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    SENTRY_DSN: str = ""

    # ─── Payments ─────────────────────────────────────────────────────────
    LEMONSQUEEZY_API_KEY: str = ""

    # ─── Email ────────────────────────────────────────────────────────────
    RESEND_API_KEY: str = ""

    # ─── Redis / Celery ───────────────────────────────────────────────────
    REDIS_URL: str = ""


settings = Settings()
