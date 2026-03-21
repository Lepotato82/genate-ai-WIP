# /llm/client.py — the ONLY place that knows which provider is in use.
# No agent should import any LLM provider SDK directly.

from config import settings


def get_text_client():
    """Returns the configured text LLM client. Swap provider here only."""
    if settings.LLM_PROVIDER == "groq":
        from groq import Groq
        return Groq(api_key=settings.GROQ_API_KEY)
    elif settings.LLM_PROVIDER == "openai":
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    elif settings.LLM_PROVIDER == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    elif settings.LLM_PROVIDER == "ollama":
        # OpenAI-compatible client pointed at local Ollama instance
        from openai import OpenAI
        return OpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")


def get_vision_client():
    """Returns the configured vision LLM client. Swap provider here only."""
    if settings.LLM_VISION_PROVIDER == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    elif settings.LLM_VISION_PROVIDER == "groq":
        from groq import Groq
        return Groq(api_key=settings.GROQ_API_KEY)
    elif settings.LLM_VISION_PROVIDER == "openai":
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    elif settings.LLM_VISION_PROVIDER == "ollama":
        from openai import OpenAI
        return OpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")
    else:
        raise ValueError(f"Unknown LLM_VISION_PROVIDER: {settings.LLM_VISION_PROVIDER}")


def chat_completion(messages: list[dict], model: str = None, **kwargs) -> str:
    """
    Unified interface for all text agents.
    Returns the response text as a string.
    Handles provider-specific differences internally.
    """
    client = get_text_client()
    model = model or settings.LLM_TEXT_MODEL
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content


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

        response = client.chat.completions.create(
            model=model,
            messages=oai_messages,
            **kwargs,
        )
        return response.choices[0].message.content
