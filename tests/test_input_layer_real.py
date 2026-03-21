from __future__ import annotations

import importlib.util

import pytest

from agents import input_processor, product_analysis, ui_analyzer
from config import settings


REAL_URLS = [
    "https://linear.app",
    "https://www.chargebee.com",
    "https://razorpay.com",
]


def _has_required_keys() -> bool:
    has_vision = bool(settings.ANTHROPIC_API_KEY) or bool(settings.OPENAI_API_KEY)
    has_text = bool(settings.GROQ_API_KEY) or bool(settings.OPENAI_API_KEY)
    return has_vision and has_text


def _provider_sdk_available() -> bool:
    provider_to_module = {
        "groq": "groq",
        "openai": "openai",
        "anthropic": "anthropic",
        "ollama": "openai",
    }
    text_mod = provider_to_module.get(settings.LLM_PROVIDER, "")
    vision_mod = provider_to_module.get(settings.LLM_VISION_PROVIDER, "")
    return bool(importlib.util.find_spec(text_mod)) and bool(
        importlib.util.find_spec(vision_mod)
    )


@pytest.mark.integration
def test_real_input_layer_smoke_suite():
    if not _has_required_keys():
        pytest.skip(
            "Skipping real input-layer tests: missing required LLM keys for "
            "ui_analyzer/product_analysis."
        )
    if not _provider_sdk_available():
        pytest.skip(
            "Skipping real input-layer tests: active provider SDKs are not installed "
            "for current LLM_PROVIDER / LLM_VISION_PROVIDER."
        )

    old_mock = settings.MOCK_MODE
    settings.MOCK_MODE = False

    try:
        summaries: list[str] = []

        for idx, url in enumerate(REAL_URLS, start=1):
            run_id = f"real-input-{idx}"
            warnings: list[str] = []

            pkg = input_processor.run(url=url, run_id=run_id)
            if len(pkg.css_tokens) < 5:
                warnings.append("low_css_token_count")
            if len(pkg.scraped_text) < 300:
                warnings.append("short_scraped_text")
            if pkg.og_image_bytes is None:
                warnings.append("missing_og_image")

            profile = ui_analyzer.run(pkg)
            knowledge = product_analysis.run(pkg)

            assert profile.run_id == run_id
            assert knowledge.run_id == run_id
            assert profile.design_category in {
                "developer-tool",
                "minimal-saas",
                "bold-enterprise",
                "consumer-friendly",
                "data-dense",
            }
            assert len(knowledge.features) >= 2
            assert len(knowledge.proof_points) >= 1

            status = "WARN" if warnings else "PASS"
            summaries.append(f"{status} {url} warnings={warnings}")

        for line in summaries:
            print(line)
    finally:
        settings.MOCK_MODE = old_mock
