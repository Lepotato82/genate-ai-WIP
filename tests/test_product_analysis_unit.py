"""Unit tests for agents/product_analysis.py (25+ cases)."""

from __future__ import annotations

import json
from typing import get_args

import pytest

from agents import product_analysis
from config import settings
from schemas.input_package import InputPackage
from schemas.product_knowledge import ProofPoint
from schemas.strategy_brief import ProofPointType


@pytest.fixture(autouse=True)
def _restore_mock_mode():
    old = settings.MOCK_MODE
    yield
    settings.MOCK_MODE = old


def _pkg(
    *,
    run_id: str = "run-x",
    url: str = "https://acme.dev",
    user_document: str | None = None,
    scraped_text: str = "",
) -> InputPackage:
    return InputPackage(
        url=url,
        run_id=run_id,
        scraped_text=scraped_text,
        user_document=user_document,
        scrape_word_count=len(scraped_text.split()),
    )


def test_classify_uptime_claim() -> None:
    t = "99.99% uptime SLA for all teams and customers worldwide"
    assert product_analysis._classify_proof_type(t) == "uptime_claim"


def test_classify_integration_count() -> None:
    # Outer gate needs a digit plus a volume signal (e.g. "teams") before subtype rules run.
    t = "500+ integrations with apps and tools trusted by teams in our directory"
    assert product_analysis._classify_proof_type(t) == "integration_count"


def test_classify_user_count() -> None:
    t = "Trusted by 10 million users and 50k companies globally today"
    assert product_analysis._classify_proof_type(t) == "user_count"


def test_classify_stat_numeric_without_user_keywords() -> None:
    t = "API latency improved 40% year over year in benchmarks"
    assert product_analysis._classify_proof_type(t) == "stat"


def test_classify_g2_badge() -> None:
    assert product_analysis._classify_proof_type("Rated best on G2 for winter grid") == "g2_badge"


def test_classify_gartner() -> None:
    assert product_analysis._classify_proof_type("Named in Gartner MQ report") == "g2_badge"


def test_classify_award() -> None:
    assert product_analysis._classify_proof_type("Forbes Cloud 100 winner this year") == "award"


def test_classify_customer_name_two_proper_nouns() -> None:
    t = "Stripe and Notion rely on this platform for daily operations"
    assert product_analysis._classify_proof_type(t) == "customer_name"


def test_parse_features_plain_string_uses_slice_for_name_and_desc() -> None:
    feats = product_analysis._parse_features(["ShortNameHere"])
    assert feats[0].name == "ShortNameHere"
    assert feats[0].description == "ShortNameHere"


def test_parse_features_colon_splits_name_description() -> None:
    feats = product_analysis._parse_features(["Sync: Keeps data aligned across systems"])
    assert feats[0].name == "Sync"
    assert "aligned" in feats[0].description


def test_parse_features_dict_name_description() -> None:
    feats = product_analysis._parse_features(
        [{"name": "API", "description": "REST endpoints for automation"}]
    )
    assert feats[0].name == "API"
    assert "REST" in feats[0].description


def test_parse_proof_points_skips_two_word_junk() -> None:
    pts = product_analysis._parse_proof_points(["hello world", "x"], "scraped_page")
    assert pts == []


def test_parse_proof_points_skips_three_words_below_schema_minimum() -> None:
    pts = product_analysis._parse_proof_points(["one two three"], "scraped_page")
    assert pts == []


def test_parse_proof_points_skips_four_words() -> None:
    pts = product_analysis._parse_proof_points(["one two three four"], "scraped_page")
    assert pts == []


def test_parse_proof_points_keeps_five_words() -> None:
    pts = product_analysis._parse_proof_points(
        ["We serve ten thousand teams globally every day"],
        "scraped_page",
    )
    assert len(pts) == 1
    assert isinstance(pts[0], ProofPoint)


def test_parse_proof_points_non_string_coerced() -> None:
    pts = product_analysis._parse_proof_points([12345], "scraped_page")
    assert pts == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("project portfolio suite", "project-management"),
        ("developer dev experience tool", "developer-tool"),
        ("fintech payment rails", "fintech-saas"),
        ("hr people recruiting suite", "hr-people"),
        ("data analytics bi dashboards", "data-analytics"),
        ("customer support success team", "customer-success"),
        ("marketing content seo growth", "marketing-content"),
        ("security compliance audits", "security-compliance"),
        ("vertical saas for clinics", "vertical-saas"),
        ("random pizza shop", "other"),
        ("wellness health app for personal health tracking", "health-wellness"),
        ("mental health therapy meditation app", "health-wellness"),
        ("sleep tracking nutrition fitness app", "health-wellness"),
    ],
)
def test_map_product_category_all_literals(raw: str, expected: str) -> None:
    assert product_analysis._map_product_category(raw) == expected


def test_map_product_category_health_wins_over_vertical_saas() -> None:
    """A consumer health/wellness app must not be swallowed by vertical-saas."""
    result = product_analysis._map_product_category(
        "wellness health app personal health tracking consumer healthcare"
    )
    assert result == "health-wellness"


def test_proof_source_user_document_only() -> None:
    pkg = _pkg(user_document="x" * 60, scraped_text="")
    assert pkg.data_source == "user_document_only"
    assert product_analysis._proof_source(pkg) == "user_document"


def test_proof_source_scraped_default() -> None:
    pkg = _pkg(user_document="x" * 60, scraped_text="y" * 60)
    assert product_analysis._proof_source(pkg) == "scraped_page"


@pytest.mark.parametrize(
    ("val", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("YES", True),
        ("0", False),
        ("", False),
    ],
)
def test_coerce_bool(val: object, expected: bool) -> None:
    assert product_analysis._coerce_bool(val) is expected


def test_dedupe_strings_order_preserved() -> None:
    assert product_analysis._dedupe_strings(["A", "a", "B", "A"]) == ["A", "B"]


def test_dedupe_features_by_name_casefold() -> None:
    from schemas.product_knowledge import Feature

    fs = [
        Feature(name="API", description="one"),
        Feature(name="api", description="two"),
    ]
    out = product_analysis._dedupe_features(fs)
    assert len(out) == 1


def test_normalize_integrations_list_dict_and_string() -> None:
    raw = [{"name": "GitHub"}, "Slack", {"title": "Jira"}]
    assert product_analysis._normalize_integrations_list(raw) == ["GitHub", "Slack", "Jira"]


def test_normalize_integrations_list_dedupes() -> None:
    assert product_analysis._normalize_integrations_list(["Slack", "slack", "Slack"]) == ["Slack"]


def test_empty_text_short_circuit_no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _boom(*_a, **_k):
        raise AssertionError("chat_completion must not be called")

    monkeypatch.setattr(product_analysis, "chat_completion", _boom)
    pkg = _pkg(user_document="short")
    pk = product_analysis.run(pkg)
    assert pk.product_category == "other"
    assert pk.run_id == pkg.run_id


def test_run_id_flows_through_real_parse_path(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False
    payload = {
        "product_name": "Acme",
        "tagline": None,
        "description": "word " * 40,
        "product_category": "developer tool",
        "features": ["F1: does thing one", "F2: does thing two"],
        "benefits": ["Gain A", "Gain B"],
        "proof_points": ["Used by ten thousand teams with strong adoption metrics"],
        "pain_points": ["Pain one daily", "Pain two daily"],
        "messaging_angles": ["Angle one"],
        "integrations": [],
        "pricing_mentioned": False,
        "pricing_description": None,
        "target_customer": None,
    }
    monkeypatch.setattr(
        product_analysis,
        "chat_completion",
        lambda *_a, **_k: json.dumps(payload),
    )
    pkg = _pkg(run_id="rid-abc", user_document="x" * 60)
    pk = product_analysis.run(pkg)
    assert pk.run_id == "rid-abc"
    assert pk.product_url == pkg.url


def test_proof_types_are_valid_literals(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False
    payload = {
        "product_name": "Z",
        "description": "word " * 40,
        "product_category": "tool",
        "features": ["A: b", "C: d"],
        "benefits": ["B1", "B2"],
        "proof_points": [
            "G2 leader badge for enterprise category in 2024",
            "Acme Corp and Contoso both standardize on this stack",
        ],
        "pain_points": ["P1 here now", "P2 here now"],
        "messaging_angles": ["M1"],
        "integrations": [],
        "pricing_mentioned": False,
        "pricing_description": None,
        "target_customer": None,
    }
    monkeypatch.setattr(
        product_analysis,
        "chat_completion",
        lambda *_a, **_k: json.dumps(payload),
    )
    pkg = _pkg(user_document="y" * 60)
    pk = product_analysis.run(pkg)
    allowed = set(get_args(ProofPointType))
    for pp in pk.proof_points:
        assert pp.proof_type in allowed


def test_mock_mode_returns_stable_product() -> None:
    settings.MOCK_MODE = True
    pkg = _pkg(run_id="m1")
    pk = product_analysis.run(pkg)
    assert pk.product_name == product_analysis._host_name(pkg.url)
    assert len(pk.features) >= 2


def test_host_name_from_url() -> None:
    assert product_analysis._host_name("https://www.linear.app/foo") == "Linear"


def test_fallback_description_meets_word_minimum() -> None:
    desc = product_analysis._fallback_description("Acme", "snippet " * 5)
    assert len(desc.split()) >= 30


def test_dedupe_proof_points_by_text() -> None:
    a = ProofPoint(
        text="Same text repeated for testing proof point dedupe logic",
        proof_type="stat",
        source="scraped_page",
    )
    b = ProofPoint(
        text="same text repeated for testing proof point dedupe logic",
        proof_type="stat",
        source="scraped_page",
    )
    out = product_analysis._dedupe_proof_points([a, b])
    assert len(out) == 1
