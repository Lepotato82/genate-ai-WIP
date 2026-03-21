"""
Integration tests — Input Layer (Part 1–3).

Real network calls + real API calls. No mocks.
Requires MOCK_MODE=false (set in .env or overridden via env).

Run:
    uv run pytest tests/test_input_layer_integration.py \\
      -m integration -v --tb=short -s \\
      2>&1 | tee test_data/input_layer_audit.txt
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import pytest

from agents import input_processor, product_analysis, ui_analyzer
from schemas.brand_profile import BrandProfile
from schemas.input_package import InputPackage
from schemas.product_knowledge import ProductKnowledge

# ── Test targets ──────────────────────────────────────────────────────────────

TARGETS = [
    {"name": "Razorpay",   "url": "https://razorpay.com",         "expected_category": "consumer-friendly"},
    {"name": "Chargebee",  "url": "https://www.chargebee.com",    "expected_category": "minimal-saas"},
    {"name": "Postman",    "url": "https://www.postman.com",      "expected_category": "developer-tool"},
    {"name": "Hasura",     "url": "https://hasura.io",            "expected_category": "developer-tool"},
    {"name": "Freshworks", "url": "https://www.freshworks.com",   "expected_category": "bold-enterprise"},
    {"name": "Linear",     "url": "https://linear.app",           "expected_category": "developer-tool"},
]

# Expected dark-theme values for spot-checks
_EXPECTED_DARK = {
    "Linear":     True,
    "Razorpay":   False,
    "Postman":    False,
}

# Adjacent-category map — "close enough" for WARN instead of FAIL
_ADJACENT = {
    "developer-tool": {"minimal-saas"},
    "minimal-saas":   {"developer-tool", "bold-enterprise"},
    "bold-enterprise":{"minimal-saas", "consumer-friendly"},
    "consumer-friendly": {"bold-enterprise", "minimal-saas"},
    "data-dense":     {"developer-tool", "minimal-saas"},
}

_SIGNAL_WORDS = [
    "platform", "product", "team", "customer", "free",
    "enterprise", "api", "integrate", "scale", "automate",
    "solution", "workflow", "dashboard", "data",
]
_COOKIE_PREFIXES = [
    "we use cookies", "cookie policy", "accept all",
    "privacy", "by continuing", "this site uses",
]
_SIGNAL_TOKEN_KEYS = {"color", "bg", "background", "font", "accent", "brand", "primary"}

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# ── Result accumulator ────────────────────────────────────────────────────────

class SiteResult:
    def __init__(self, name: str, url: str, expected_category: str):
        self.name = name
        self.url = url
        self.expected_category = expected_category
        self.ip: dict[str, Any] = {"failures": [], "warnings": []}
        self.ui: dict[str, Any] = {"failures": [], "warnings": []}
        self.pa: dict[str, Any] = {"failures": [], "warnings": []}

    def overall(self) -> str:
        if self.ip["failures"] or self.ui["failures"] or self.pa["failures"]:
            return "FAIL"
        if self.ip["warnings"] or self.ui["warnings"] or self.pa["warnings"]:
            return "WARN"
        return "PASS"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_image_format(data: bytes) -> str:
    if data[:2] == b"\xff\xd8":
        return "JPEG"
    if data[:4] == b"\x89PNG":
        return "PNG"
    if data[:4] == b"RIFF":
        return "WebP"
    return "UNKNOWN"


def _signal_keys_in(named_colors: dict[str, str]) -> list[str]:
    found = []
    for k in named_colors:
        kl = k.lower()
        for sig in _SIGNAL_TOKEN_KEYS:
            if sig in kl:
                found.append(k)
                break
    return found


def _numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,\.]*\d|\d", text))


# ── Part 1: Input Processor validation ───────────────────────────────────────

def _validate_input_processor(pkg: InputPackage, r: SiteResult) -> None:
    dt = pkg.design_tokens
    ip = r.ip

    # T1 token_count
    count = len(dt.named_colors) if dt else 0
    ip["token_count"] = count
    scrape_failed = bool(pkg.scrape_error)
    if count == 0:
        if scrape_failed:
            ip["warnings"].append(f"T1: named_colors empty (scrape failed: {pkg.scrape_error})")
        else:
            ip["failures"].append("T1: named_colors is empty")
    elif count < 3:
        ip["warnings"].append(f"T1: token_count={count} (expected >= 3)")

    # T2 signal_tokens
    # Only a hard FAIL when enhanced extraction ran — computed_style may return generic var names
    if dt:
        sig_keys = _signal_keys_in(dt.named_colors)
        ip["signal_keys_found"] = sig_keys
        if not sig_keys:
            if dt.extraction_method in ("playwright_enhanced", "dembrandt"):
                ip["failures"].append("T2: no signal keys found in named_colors")
            else:
                ip["warnings"].append("T2: no signal keys found (computed_style fallback)")
    else:
        ip["signal_keys_found"] = []
        ip["warnings"].append("T2: no design_tokens — extraction did not run")

    # T3 font_families_extracted
    # Fonts are populated by playwright_enhanced and dembrandt; computed_style cannot extract them
    if dt:
        font_names = [f.name for f in dt.fonts if f.name]
        ip["font_names"] = font_names
        if not font_names:
            if dt.extraction_method in ("playwright_enhanced", "dembrandt"):
                ip["failures"].append("T3: fonts list is empty or all names are blank")
            else:
                ip["warnings"].append("T3: fonts empty (expected with computed_style fallback)")
    else:
        ip["font_names"] = []
        ip["warnings"].append("T3: no design_tokens — extraction did not run")

    # T4 font_weights_include_body
    if dt:
        body_weights = {400, 500, 510}
        weights = set(dt.font_weights)
        ip["font_weights"] = list(weights)
        has_body = bool(weights & body_weights)
        only_extreme = weights and weights.issubset({100, 200, 800, 900})
        if not has_body:
            if only_extreme:
                ip["warnings"].append(f"T4: only extreme weights found: {sorted(weights)}")
            else:
                ip["warnings"].append(f"T4: no body-weight (400/500/510) found in {sorted(weights)}")
    else:
        ip["font_weights"] = []
        ip["warnings"].append("T4: no design_tokens")

    # T5 extraction_method
    if dt:
        method = dt.extraction_method
        ip["extraction_method"] = method
        if method != "playwright_enhanced":
            ip["warnings"].append(f"T5: extraction_method={method!r} (expected 'playwright_enhanced')")
    else:
        ip["extraction_method"] = None
        ip["warnings"].append("T5: design_tokens is None — extraction did not run")

    # T6 dark_theme_detection
    if dt:
        ip["has_dark_theme"] = dt.has_dark_theme
        expected = _EXPECTED_DARK.get(r.name)
        if expected is not None and dt.has_dark_theme != expected:
            ip["warnings"].append(
                f"T6: has_dark_theme={dt.has_dark_theme}, expected {expected} for {r.name}"
            )
    else:
        ip["has_dark_theme"] = None

    # T7 text_length
    tlen = len(pkg.scraped_text)
    ip["text_length"] = tlen
    if tlen < 200:
        if scrape_failed:
            ip["warnings"].append(f"T7: scraped_text empty (scrape failed: {pkg.scrape_error})")
        else:
            ip["failures"].append(f"T7: scraped_text too short: {tlen} chars (need >= 200)")
    elif tlen < 500:
        ip["warnings"].append(f"T7: scraped_text only {tlen} chars (expected >= 500)")

    # T8 product_signal_words
    lower_text = pkg.scraped_text.lower()
    found_signals = [w for w in _SIGNAL_WORDS if w in lower_text]
    ip["signal_words_found"] = found_signals
    if len(found_signals) < 2:
        if scrape_failed:
            ip["warnings"].append(f"T8: no signal words (scrape failed)")
        else:
            ip["failures"].append(f"T8: only {len(found_signals)} signal words found: {found_signals}")
    elif len(found_signals) < 3:
        ip["warnings"].append(f"T8: only {len(found_signals)} signal words found (expected >= 3)")

    # T9 no_cookie_banner_noise
    first200 = pkg.scraped_text[:200].lower()
    ip["scraped_text_start"] = pkg.scraped_text[:100]
    for prefix in _COOKIE_PREFIXES:
        if first200.startswith(prefix):
            ip["failures"].append(f"T9: cookie banner detected at start: {prefix!r}")
            break

    # T10 og_image_present
    if pkg.og_image_bytes and len(pkg.og_image_bytes) > 5000:
        fmt = _detect_image_format(pkg.og_image_bytes)
        ip["og_image"] = {"present": True, "format": fmt, "size": len(pkg.og_image_bytes)}
        if fmt == "UNKNOWN":
            ip["warnings"].append("T10: og_image has unknown magic bytes")
    else:
        ip["og_image"] = {"present": False}
        ip["warnings"].append("T10: og_image_bytes is None or too small")


# ── Part 2: UI Analyzer validation ───────────────────────────────────────────

def _validate_ui_analyzer(
    result: BrandProfile, pkg: InputPackage, r: SiteResult
) -> None:
    ui = r.ui

    # U1 returns_valid_brand_profile — Pydantic already validated on construction
    ui["valid"] = True

    # U2 design_category_plausible
    actual = result.design_category
    expected = r.expected_category
    ui["design_category_expected"] = expected
    ui["design_category_actual"] = actual
    ui["category_match"] = actual == expected
    if actual != expected:
        if actual in _ADJACENT.get(expected, set()):
            ui["warnings"].append(f"U2: category={actual!r}, expected {expected!r} (adjacent — warn)")
        else:
            ui["failures"].append(f"U2: category={actual!r}, expected {expected!r} (wrong)")

    # U3 writing_instruction_quality
    wi = result.writing_instruction
    ui["writing_instruction"] = wi
    wi_lower = wi.lower()
    has_specific = (
        (result.primary_color or "").lower() in wi_lower
        or (result.font_family or "").lower() in wi_lower
        or result.design_category in wi_lower
    )
    is_generic = "professional" in wi_lower and "engaging" in wi_lower and not has_specific
    if is_generic:
        ui["warnings"].append("U3: writing_instruction appears generic (no brand-specific signals)")

    # U4 primary_color_extracted
    pc = result.primary_color
    ui["primary_color"] = pc
    if not pc:
        ui["failures"].append("U4: primary_color is None")
    elif not _HEX_RE.match(pc):
        ui["warnings"].append(f"U4: primary_color {pc!r} is not a valid hex")

    # U5 confidence_reasonable
    conf = result.confidence
    ui["confidence"] = conf
    if conf < 0.5:
        ui["warnings"].append(f"U5: confidence={conf:.2f} < 0.5 (model was uncertain)")

    # U6 dark_theme_consistent
    if pkg.design_tokens is not None:
        token_dark = pkg.design_tokens.has_dark_theme
        model_dark = result.has_dark_theme
        ui["dark_theme_token"] = token_dark
        ui["dark_theme_model"] = model_dark
        if token_dark != model_dark:
            ui["warnings"].append(
                f"U6: dark_theme mismatch — token={token_dark}, model={model_dark}"
            )
    else:
        ui["dark_theme_token"] = None
        ui["dark_theme_model"] = result.has_dark_theme


# ── Part 3: Product Analysis validation ──────────────────────────────────────

def _validate_product_analysis(
    result: ProductKnowledge, pkg: InputPackage, r: SiteResult
) -> None:
    pa = r.pa
    lower_text = pkg.scraped_text.lower()

    # P1 returns_valid_product_knowledge — already validated by Pydantic

    # P2 features_not_empty
    pa["feature_count"] = len(result.features)
    if not result.features:
        pa["failures"].append("P2: features list is empty")

    # P3 benefits_not_empty
    pa["benefit_count"] = len(result.benefits)
    if not result.benefits:
        pa["failures"].append("P3: benefits list is empty")

    # P4 features_vs_benefits_distinct
    feat_set = set(f.lower() for f in result.features)
    ben_set  = set(b.lower() for b in result.benefits)
    overlap = feat_set & ben_set
    if overlap:
        pa["warnings"].append(f"P4: feature/benefit overlap: {list(overlap)[:3]}")

    # P5 proof_points_grounded
    pa["proof_point_count"] = len(result.proof_points)
    fabrication_warnings: list[str] = []
    for pp in result.proof_points:
        text_lower = pp.text.lower()
        in_source = text_lower in lower_text
        short_enough = len(pp.text) < 100
        if not in_source and not short_enough:
            fabrication_warnings.append(f"possible fabrication: {pp.text[:80]!r}")
    pa["fabrication_warnings"] = fabrication_warnings
    if fabrication_warnings:
        pa["warnings"].extend([f"P5: {w}" for w in fabrication_warnings])

    # P6 no_fabricated_stats
    stat_warnings: list[str] = []
    source_numbers = _numbers_in(pkg.scraped_text)
    for pp in result.proof_points:
        if pp.proof_type == "stat":
            stat_numbers = _numbers_in(pp.text)
            missing = stat_numbers - source_numbers
            if missing:
                stat_warnings.append(f"stat number(s) {missing} not in source: {pp.text[:80]!r}")
    pa["stat_warnings"] = stat_warnings
    if stat_warnings:
        pa["warnings"].extend([f"P6: {w}" for w in stat_warnings])

    # P7 product_name_extracted
    pa["product_name"] = result.product_name
    if not result.product_name:
        pa["warnings"].append("P7: product_name is None or empty")

    # P8 pain_points_present
    pa["pain_point_count"] = len(result.pain_points)
    if not result.pain_points:
        pa["warnings"].append("P8: pain_points is empty (homepage may hide pain)")


# ── Summary printer ───────────────────────────────────────────────────────────

def _print_summary(results: list[SiteResult]) -> None:
    print("\n")
    print("=" * 78)
    print("INTEGRATION AUDIT SUMMARY")
    print("=" * 78)
    header = f"{'Site':<12} | {'T_pass':>6} | {'U_cat':<12} | {'U_conf':>6} | {'P_feat':>6} | {'P_proof':>7} | OVERALL"
    print(header)
    print("-" * 78)

    full_pass = warnings_only = failures = category_hits = 0

    for r in results:
        ip = r.ip
        ui = r.ui
        pa = r.pa

        # token checks: T1–T6 token, T7–T10 text, resilience excluded from per-site
        t_checks = 10
        t_fail_count = len(ip.get("failures", []))
        t_warn_count = len(ip.get("warnings", []))
        t_pass = t_checks - t_fail_count - t_warn_count
        t_pass = max(0, t_pass)

        cat_match = ui.get("category_match", False)
        if cat_match:
            category_hits += 1
        cat_actual = ui.get("design_category_actual", "?")
        cat_str = f"{'Y' if cat_match else 'N'} {cat_actual[:9]:<9}"

        conf = ui.get("confidence", 0.0)
        feat = pa.get("feature_count", 0)
        proof = pa.get("proof_point_count", 0)
        overall = r.overall()

        print(
            f"{r.name:<12} | {t_pass:>2}/{t_checks:<3} | {cat_str} | "
            f"{conf:>5.2f}  | {feat:>6} | {proof:>7} | {overall}"
        )

        if overall == "PASS":
            full_pass += 1
        elif overall == "WARN":
            warnings_only += 1
        else:
            failures += 1

    print("=" * 78)
    print(f"Category accuracy: {category_hits}/{len(results)}")
    print(f"Full PASS: {full_pass}  |  WARN: {warnings_only}  |  FAIL: {failures}")
    print()


def _save_json(results: list[SiteResult], targets: list[dict]) -> None:
    target_map = {t["name"]: t for t in targets}

    def _site_dict(r: SiteResult) -> dict:
        return {
            "name": r.name,
            "url": r.url,
            "input_processor": r.ip,
            "ui_analyzer": r.ui,
            "product_analysis": r.pa,
            "overall": r.overall(),
        }

    total = len(results)
    full_pass = sum(1 for r in results if r.overall() == "PASS")
    warn_only = sum(1 for r in results if r.overall() == "WARN")
    fail_cnt  = sum(1 for r in results if r.overall() == "FAIL")
    cat_hits  = sum(1 for r in results if r.ui.get("category_match"))

    doc = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "environment": "real-mode",
        "api_keys_used": ["ANTHROPIC_API_KEY", "GROQ_API_KEY"],
        "results": [_site_dict(r) for r in results],
        "summary": {
            "total_sites": total,
            "full_pass": full_pass,
            "warnings_only": warn_only,
            "failures": fail_cnt,
            "category_accuracy": f"{cat_hits}/{total}",
            "notes": "",
        },
    }

    out_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "test_data", "input_layer_audit.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, default=str)
    print(f"Audit saved -> {out_path}")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def site_results() -> list[SiteResult]:
    """
    Run the full input-layer pipeline once per target.
    Collects all results; individual tests read from this shared state.
    """
    from config import settings as _settings
    _orig_mock_mode = _settings.MOCK_MODE
    _settings.MOCK_MODE = False

    results: list[SiteResult] = []

    try:
        for target in TARGETS:
            name = target["name"]
            url = target["url"]
            expected = target["expected_category"]
            r = SiteResult(name, url, expected)
            print(f"\n[{name}] Scraping {url} ...")

            # ── Part 1 ──
            try:
                pkg: InputPackage = input_processor.run(url)
                _validate_input_processor(pkg, r)
                print(
                    f"  Input: tokens={r.ip.get('token_count', '?')}  "
                    f"text={r.ip.get('text_length', '?')}  "
                    f"method={r.ip.get('extraction_method', '?')}  "
                    f"dark={r.ip.get('has_dark_theme', '?')}"
                )
            except Exception as exc:
                r.ip["failures"].append(f"input_processor.run raised: {exc}")
                pkg = InputPackage(url=url, scraped_text="", scrape_error=str(exc))
                print(f"  Input: EXCEPTION - {exc}")

            # ── Part 2 ──
            try:
                brand = ui_analyzer.run(pkg)
                _validate_ui_analyzer(brand, pkg, r)
                print(
                    f"  UI:    category={r.ui.get('design_category_actual', '?')!r}  "
                    f"{'Y' if r.ui.get('category_match') else 'N'} expected={expected!r}  "
                    f"conf={r.ui.get('confidence', 0):.2f}"
                )
            except Exception as exc:
                r.ui["failures"].append(f"ui_analyzer.run raised: {exc}")
                print(f"  UI:    EXCEPTION - {exc}")

            # ── Part 3 ──
            try:
                knowledge = product_analysis.run(pkg)
                _validate_product_analysis(knowledge, pkg, r)
                print(
                    f"  Prod:  name={r.pa.get('product_name', '?')!r}  "
                    f"features={r.pa.get('feature_count', '?')}  "
                    f"proofs={r.pa.get('proof_point_count', '?')}"
                )
            except Exception as exc:
                r.pa["failures"].append(f"product_analysis.run raised: {exc}")
                print(f"  Prod:  EXCEPTION - {exc}")

            results.append(r)

        # Resilience test T11 + T12 captured separately (see below)
        _print_summary(results)
        _save_json(results, TARGETS)
    finally:
        _settings.MOCK_MODE = _orig_mock_mode

    return results


# ── Resilience fixtures (run independently, not in main loop) ─────────────────

@pytest.fixture(scope="module")
def nonexistent_pkg() -> InputPackage:
    from config import settings as _settings
    _orig_mock_mode = _settings.MOCK_MODE
    _settings.MOCK_MODE = False
    try:
        return input_processor.run("https://genate-nonexistent-xyz123.io")
    finally:
        _settings.MOCK_MODE = _orig_mock_mode


# ── Part 1 tests ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestInputProcessor:
    def test_T1_token_count(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ip.get("failures", []):
                if f.startswith("T1"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_T2_signal_tokens(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ip.get("failures", []):
                if f.startswith("T2"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_T3_font_families_extracted(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ip.get("failures", []):
                if f.startswith("T3"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_T4_font_weights_include_body(self, site_results):
        # WARN-only — no hard assert
        for r in site_results:
            warns = [w for w in r.ip.get("warnings", []) if w.startswith("T4")]
            for w in warns:
                print(f"WARN {r.name}: {w}")

    def test_T5_extraction_method(self, site_results):
        for r in site_results:
            warns = [w for w in r.ip.get("warnings", []) if w.startswith("T5")]
            for w in warns:
                print(f"WARN {r.name}: {w}")

    def test_T6_dark_theme_detection(self, site_results):
        for r in site_results:
            dark = r.ip.get("has_dark_theme")
            print(f"{r.name}: has_dark_theme={dark}")
            warns = [w for w in r.ip.get("warnings", []) if w.startswith("T6")]
            for w in warns:
                print(f"WARN {r.name}: {w}")

    def test_T7_text_length(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ip.get("failures", []):
                if f.startswith("T7"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_T8_product_signal_words(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ip.get("failures", []):
                if f.startswith("T8"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_T9_no_cookie_banner_noise(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ip.get("failures", []):
                if f.startswith("T9"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_T10_og_image_present(self, site_results):
        # WARN-only — some sites omit OG tags
        for r in site_results:
            og = r.ip.get("og_image", {})
            print(f"{r.name}: og_image={og}")

    def test_T11_nonexistent_domain_does_not_raise(self, nonexistent_pkg):
        assert isinstance(nonexistent_pkg, InputPackage)
        assert nonexistent_pkg.scrape_error is not None, (
            "Expected scrape_error to be set for nonexistent domain"
        )

    def test_T12_js_spa_renders(self, site_results):
        spa_sites = {"Postman", "Hasura"}
        failures = []
        for r in site_results:
            if r.name in spa_sites:
                tlen = r.ip.get("text_length", 0)
                # Only fail if scrape did not error out (timeout = infrastructure, not test failure)
                scrape_errored = bool(next(
                    (s for s in r.ip.get("warnings", []) if "scrape failed" in s), None
                ) or next(
                    (f for f in r.ip.get("failures", []) if "scrape" in f.lower()), None
                ))
                if tlen < 300 and not scrape_errored:
                    failures.append(f"{r.name}: only {tlen} chars (SPA may not have rendered)")
                elif tlen < 300:
                    print(f"  WARN T12 {r.name}: scrape timed out, SPA render unverifiable")
        assert not failures, "\n".join(failures)


# ── Part 2 tests ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestUIAnalyzer:
    def test_U1_returns_valid_brand_profile(self, site_results):
        for r in site_results:
            for f in r.ui.get("failures", []):
                if "raised" in f:
                    pytest.fail(f"{r.name}: {f}")

    def test_U2_design_category_plausible(self, site_results):
        """
        Expect >= 4/6 correct. All 6 are logged regardless.
        Hard fail only if < 4 correct (clearly broken).
        """
        total = len(site_results)
        correct = sum(1 for r in site_results if r.ui.get("category_match"))
        for r in site_results:
            match = r.ui.get("category_match")
            actual = r.ui.get("design_category_actual", "?")
            expected = r.expected_category
            marker = "Y" if match else "N"
            print(f"  {marker} {r.name}: expected={expected!r} actual={actual!r}")
        assert correct >= 4, (
            f"Category accuracy {correct}/{total} is below minimum threshold of 4/6"
        )

    def test_U3_writing_instruction_quality(self, site_results):
        for r in site_results:
            wi = r.ui.get("writing_instruction", "")
            print(f"{r.name}: {wi[:120]}")
            for w in r.ui.get("warnings", []):
                if w.startswith("U3"):
                    print(f"  WARN: {w}")

    def test_U4_primary_color_extracted(self, site_results):
        failures = []
        for r in site_results:
            for f in r.ui.get("failures", []):
                if f.startswith("U4"):
                    failures.append(f"{r.name}: {f}")
            pc = r.ui.get("primary_color")
            print(f"{r.name}: primary_color={pc!r}")
        assert not failures, "\n".join(failures)

    def test_U5_confidence_reasonable(self, site_results):
        for r in site_results:
            conf = r.ui.get("confidence", 0.0)
            print(f"{r.name}: confidence={conf:.2f}")
            for w in r.ui.get("warnings", []):
                if w.startswith("U5"):
                    print(f"  WARN: {w}")

    def test_U6_dark_theme_consistent(self, site_results):
        for r in site_results:
            tok = r.ui.get("dark_theme_token")
            mod = r.ui.get("dark_theme_model")
            print(f"{r.name}: token={tok} model={mod}")
            for w in r.ui.get("warnings", []):
                if w.startswith("U6"):
                    print(f"  WARN: {w}")


# ── Part 3 tests ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestProductAnalysis:
    def test_P1_returns_valid_product_knowledge(self, site_results):
        for r in site_results:
            for f in r.pa.get("failures", []):
                if "raised" in f:
                    pytest.fail(f"{r.name}: {f}")

    def test_P2_features_not_empty(self, site_results):
        failures = []
        for r in site_results:
            for f in r.pa.get("failures", []):
                if f.startswith("P2"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_P3_benefits_not_empty(self, site_results):
        failures = []
        for r in site_results:
            for f in r.pa.get("failures", []):
                if f.startswith("P3"):
                    failures.append(f"{r.name}: {f}")
        assert not failures, "\n".join(failures)

    def test_P4_features_vs_benefits_distinct(self, site_results):
        for r in site_results:
            for w in r.pa.get("warnings", []):
                if w.startswith("P4"):
                    print(f"WARN {r.name}: {w}")

    def test_P5_proof_points_grounded(self, site_results):
        for r in site_results:
            for f in r.pa.get("fabrication_warnings", []):
                print(f"WARN {r.name}: {f}")
        # Warn only — no hard assert

    def test_P6_no_fabricated_stats(self, site_results):
        for r in site_results:
            for w in r.pa.get("stat_warnings", []):
                print(f"WARN {r.name}: {w}")

    def test_P7_product_name_extracted(self, site_results):
        for r in site_results:
            name = r.pa.get("product_name")
            print(f"{r.name}: product_name={name!r}")
            for w in r.pa.get("warnings", []):
                if w.startswith("P7"):
                    print(f"  WARN: {w}")

    def test_P8_pain_points_present(self, site_results):
        for r in site_results:
            count = r.pa.get("pain_point_count", 0)
            print(f"{r.name}: pain_point_count={count}")
            for w in r.pa.get("warnings", []):
                if w.startswith("P8"):
                    print(f"  WARN: {w}")
