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

    # ─── Image Generation ─────────────────────────────────────────────────
    FAL_API_KEY: str = ""
    BANNERBEAR_API_KEY: str = ""
    BANNERBEAR_TEMPLATE_UID: str = ""
    BANNERBEAR_TIMEOUT_SECONDS: int = 30
    IMAGE_GENERATION_ENABLED: bool = False
    IDEOGRAM_API_KEY: str = ""

    # ─── Video Generation ─────────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = ""
    HEYGEN_API_KEY: str = ""

    # ─── Scraping ─────────────────────────────────────────────────────────
    BROWSERLESS_API_KEY: str = ""
    BRIGHTDATA_PROXY_URL: str = ""
    SCRAPE_TIMEOUT_SECONDS: int = 15
    SCRAPE_MAX_RETRIES: int = 2

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
