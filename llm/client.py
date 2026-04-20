# /llm/client.py — the ONLY place that knows which provider is in use.
# No agent should import any LLM provider SDK directly.

import logging
import time

from config import settings

logger = logging.getLogger(__name__)

_RATE_LIMIT_RETRIES = 4        # max attempts before giving up
_RATE_LIMIT_BACKOFF = 2.0      # seconds for first wait; doubles each retry


def _ollama_openai_base_url() -> str:
    """Ollama's OpenAI-compatible API is mounted at /v1."""
    base = (settings.OLLAMA_BASE_URL or "http://localhost:11434").rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def get_text_client():
    """Returns the configured text LLM client. Swap provider here only."""
    timeout = settings.LLM_REQUEST_TIMEOUT
    if settings.LLM_PROVIDER == "groq":
        from groq import Groq
        return Groq(api_key=settings.GROQ_API_KEY, timeout=timeout)
    elif settings.LLM_PROVIDER == "openai":
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout)
    elif settings.LLM_PROVIDER == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=timeout)
    elif settings.LLM_PROVIDER == "ollama":
        # OpenAI-compatible client pointed at local Ollama instance
        from openai import OpenAI
        return OpenAI(base_url=_ollama_openai_base_url(), api_key="ollama", timeout=timeout)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")


def get_vision_client():
    """Returns the configured vision LLM client. Swap provider here only."""
    timeout = settings.LLM_REQUEST_TIMEOUT
    if settings.LLM_VISION_PROVIDER == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=timeout)
    elif settings.LLM_VISION_PROVIDER == "groq":
        from groq import Groq
        return Groq(api_key=settings.GROQ_API_KEY, timeout=timeout)
    elif settings.LLM_VISION_PROVIDER == "openai":
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout)
    elif settings.LLM_VISION_PROVIDER == "ollama":
        from openai import OpenAI
        return OpenAI(base_url=_ollama_openai_base_url(), api_key="ollama", timeout=timeout)
    else:
        raise ValueError(f"Unknown LLM_VISION_PROVIDER: {settings.LLM_VISION_PROVIDER}")


def _is_rate_limit(exc: Exception) -> bool:
    """Return True if the exception is a provider 429 / rate-limit error."""
    name = type(exc).__name__
    if "RateLimit" in name:
        return True
    # openai / groq both set a status_code attribute on HTTP errors
    code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return code == 429


def _default_text_model() -> str:
    if settings.LLM_PROVIDER == "ollama":
        return settings.OLLAMA_TEXT_MODEL
    return settings.LLM_TEXT_MODEL


def chat_completion(messages: list[dict], model: str = None, **kwargs) -> str:
    """
    Unified interface for all text agents.
    Returns the response text as a string.
    Handles provider-specific differences internally.
    Retries automatically on rate-limit (429) errors with exponential backoff.
    """
    client = get_text_client()
    if settings.LLM_PROVIDER == "ollama":
        model = model or settings.OLLAMA_TEXT_MODEL
        kwargs.setdefault("max_tokens", 2048)
    else:
        model = model or settings.LLM_TEXT_MODEL

    wait = _RATE_LIMIT_BACKOFF
    for attempt in range(_RATE_LIMIT_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs,
            )
            return response.choices[0].message.content
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < _RATE_LIMIT_RETRIES - 1:
                logger.warning("[llm] rate limit hit, waiting %.1fs (attempt %d/%d)",
                               wait, attempt + 1, _RATE_LIMIT_RETRIES)
                time.sleep(wait)
                wait = min(wait * 2, 30)
                client = get_text_client()  # fresh client in case of state issues
            else:
                raise


def vision_completion(
    messages: list[dict],
    model: str = None,
    image_data: bytes | None = None,
    **kwargs,
) -> str:
    """
    Unified interface for the UI Analyzer (vision agents only).
    Returns the response text as a string.

    For Anthropic: injects image using Anthropic's source.type=base64 format.
    For Groq / OpenAI / Ollama: injects image as a base64 data URL in
    the OpenAI image_url content block format.
    Both paths handle image_data=None gracefully (text-only call).
    """
    import base64

    client = get_vision_client()
    if settings.LLM_VISION_PROVIDER == "ollama":
        model = model or settings.OLLAMA_VISION_MODEL
        kwargs.setdefault("max_tokens", 2048)
    else:
        model = model or settings.LLM_VISION_MODEL

    if settings.LLM_VISION_PROVIDER == "anthropic":
        # ── Anthropic path ────────────────────────────────────────────────
        if image_data is not None:
            b64 = base64.b64encode(image_data).decode("utf-8")
            anthropic_messages = []
            for msg in messages:
                if msg["role"] == "user" and msg is messages[-1]:
                    anthropic_messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": msg["content"]},
                        ],
                    })
                else:
                    anthropic_messages.append(msg)
        else:
            anthropic_messages = messages

        system_prompt = None
        filtered = []
        for msg in anthropic_messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                filtered.append(msg)

        create_kwargs = dict(model=model, messages=filtered, max_tokens=4096, **kwargs)
        if system_prompt:
            create_kwargs["system"] = system_prompt

        response = client.messages.create(**create_kwargs)
        return response.content[0].text

    else:
        # ── OpenAI-compatible path (groq, openai, ollama) ─────────────────
        # Inject image as a base64 data URL in the last user message
        if image_data is not None:
            b64 = base64.b64encode(image_data).decode("utf-8")
            oai_messages = []
            for msg in messages:
                if msg["role"] == "user" and msg is messages[-1]:
                    text = msg["content"] if isinstance(msg["content"], str) else ""
                    oai_messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}",
                                },
                            },
                            {"type": "text", "text": text},
                        ],
                    })
                else:
                    oai_messages.append(msg)
        else:
            oai_messages = messages

        wait = _RATE_LIMIT_BACKOFF
        for attempt in range(_RATE_LIMIT_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=oai_messages,
                    **kwargs,
                )
                return response.choices[0].message.content
            except Exception as exc:
                if _is_rate_limit(exc) and attempt < _RATE_LIMIT_RETRIES - 1:
                    logger.warning("[llm/vision] rate limit hit, waiting %.1fs (attempt %d/%d)",
                                   wait, attempt + 1, _RATE_LIMIT_RETRIES)
                    time.sleep(wait)
                    wait = min(wait * 2, 30)
                    client = get_vision_client()
                else:
                    raise
