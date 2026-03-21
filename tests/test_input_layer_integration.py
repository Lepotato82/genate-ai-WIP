import json

import pytest

from agents import input_processor, product_analysis, ui_analyzer
from config import settings
from schemas.input_package import InputPackage


@pytest.fixture(autouse=True)
def _restore_mock_mode():
    old = settings.MOCK_MODE
    yield
    settings.MOCK_MODE = old


def test_input_processor_mock_contract_and_priority_fields():
    settings.MOCK_MODE = True
    user_image = b"user-image"
    user_document = "This is user-provided canonical text."

    pkg = input_processor.run(
        url="https://linear.app",
        run_id="mock-run-1",
        user_image=user_image,
        user_document=user_document,
    )

    assert pkg.url == "https://linear.app"
    assert pkg.run_id == "mock-run-1"
    assert len(pkg.scraped_text) > 100
    assert len(pkg.css_tokens) > 0
    assert pkg.scrape_error is None
    assert pkg.get_primary_image() == user_image
    assert pkg.get_primary_text() == user_document
    assert pkg.data_source == "scraped_and_user_document"


def test_input_processor_real_mode_never_crashes_on_scrape_failure(monkeypatch):
    settings.MOCK_MODE = False

    def _fake_scrape(_url: str, _timeout: int, _max_retries: int):
        return {
            "scraped_text": "",
            "css_tokens": {},
            "screenshot_bytes": None,
            "og_image_url": None,
            "og_image_bytes": None,
            "scrape_error": "forced scrape failure",
        }

    monkeypatch.setattr(input_processor, "_scrape_with_retry", _fake_scrape)

    pkg = input_processor.run(
        url="https://example.com",
        run_id="real-fail-1",
        user_document="fallback doc content",
        user_image=b"fallback-image",
    )

    assert isinstance(pkg, InputPackage)
    assert pkg.scrape_error == "forced scrape failure"
    assert pkg.scraped_text == ""
    assert pkg.css_tokens == {}
    assert pkg.get_primary_text() == "fallback doc content"
    assert pkg.get_primary_image() == b"fallback-image"


def test_ui_analyzer_mock_contract():
    settings.MOCK_MODE = True
    pkg = input_processor.run(url="https://linear.app", run_id="mock-run-2")
    profile = ui_analyzer.run(pkg)

    assert profile.run_id == "mock-run-2"
    assert profile.design_category in {
        "developer-tool",
        "minimal-saas",
        "bold-enterprise",
        "consumer-friendly",
        "data-dense",
    }
    assert profile.tone in {"technical", "playful", "corporate", "minimal", "bold"}
    assert len(profile.writing_instruction.split()) >= 15
    assert 0.0 <= profile.confidence <= 1.0
    assert profile.css_tokens == pkg.css_tokens


def test_ui_analyzer_real_mode_parsing_path(monkeypatch):
    settings.MOCK_MODE = False
    pkg = input_processor._mock_input_package(  # test helper usage
        url="https://linear.app",
        run_id="parse-ui-1",
        org_id=None,
        user_image=None,
        user_document=None,
    )

    fake_json = json.dumps(
        {
            "design_category": "developer-tool",
            "primary_color": "#5e6ad2",
            "secondary_color": "#7170ff",
            "background_color": "#ffffff",
            "font_family": "Inter",
            "font_weights": [400.0, 510.0, 590.0],
            "border_radius": "6px",
            "spacing_unit": "4px",
            "tone": "technical",
            "writing_instruction": (
                "Write in a direct technical SaaS tone, reference concrete visual "
                "signals, prioritize specificity, and avoid all generic claims."
            ),
            "confidence": 0.86,
        }
    )
    monkeypatch.setattr(ui_analyzer, "vision_completion", lambda *_a, **_k: fake_json)

    profile = ui_analyzer.run(pkg)
    assert profile.run_id == "parse-ui-1"
    assert profile.design_category == "developer-tool"
    assert profile.primary_color == "#5e6ad2"
    assert profile.css_tokens == pkg.css_tokens


def test_product_analysis_mock_contract():
    settings.MOCK_MODE = True
    pkg = input_processor.run(url="https://linear.app", run_id="mock-run-3")
    knowledge = product_analysis.run(pkg)

    assert knowledge.run_id == "mock-run-3"
    assert knowledge.product_url == "https://linear.app"
    assert len(knowledge.features) >= 2
    assert len(knowledge.benefits) >= 2
    assert len(knowledge.proof_points) >= 1
    assert len(knowledge.pain_points) >= 2
    assert len(knowledge.messaging_angles) >= 1


def test_product_analysis_real_mode_parsing_and_coercion(monkeypatch):
    settings.MOCK_MODE = False
    pkg = input_processor._mock_input_package(
        url="https://linear.app",
        run_id="parse-pa-1",
        org_id=None,
        user_image=None,
        user_document="User supplied source text",
    )

    fake_json = json.dumps(
        {
            "product_name": "Linear",
            "product_url": "https://linear.app",
            "tagline": "Issue tracking for modern software teams",
            "description": (
                "Linear helps software teams plan, track, and execute product work "
                "with faster workflows, clearer prioritization, and fewer bottlenecks "
                "across sprint planning, issue management, release coordination, and "
                "cross-team project visibility in complex engineering organizations."
            ),
            "product_category": "developer-tool",
            "features": [
                {"name": "Issue tracking", "description": "Track work with structured workflows"},
                {"name": "Roadmaps", "description": "Plan releases and priorities"},
            ],
            "benefits": ["Faster execution", "Clearer team alignment"],
            "proof_points": [
                {
                    "text": "Used by over 10,000 engineering teams.",
                    "proof_type": "user_count",
                    "source": "scraped_page",
                }
            ],
            "pain_points": ["Slow sprint coordination", "Fragmented backlog visibility"],
            "messaging_angles": ["Speed with structure"],
            "integrations": [{"name": "GitHub"}, "Slack"],
        }
    )
    monkeypatch.setattr(product_analysis, "chat_completion", lambda *_a, **_k: fake_json)

    knowledge = product_analysis.run(pkg)
    assert knowledge.run_id == "parse-pa-1"
    assert knowledge.product_name == "Linear"
    assert knowledge.integrations == ["GitHub", "Slack"]
    assert knowledge.data_source == "scraped_and_user_document"
