# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Single Source of Truth

**Read `GENATE_CONTEXT.md` at the start of every session.** It is the authoritative reference for architecture decisions, stack choices, agent pipeline order, LLM routing rules, team ownership, and the build roadmap. This file supersedes anything written here.

---

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Run the API server (development)
uvicorn api:app --reload

# Run all fast (non-integration) tests
pytest

# Run a single test file
pytest tests/test_pipeline_contracts.py

# Run integration tests (real network, real LLM — mark explicitly)
pytest -m integration

# Lint
ruff check .

# Type-check
pyright
```

### Running the pipeline directly

```bash
# Mock mode — no LLM calls, no browser
MOCK_MODE=true LLM_PROVIDER=ollama python -c "
from pipeline import run_linkedin
r = run_linkedin('https://linear.app')
print(r['passes'], r['overall_score'])
"

# Real mode — requires Ollama running locally
MOCK_MODE=false LLM_PROVIDER=ollama python -c "
from pipeline import run_linkedin
import json
r = run_linkedin('https://linear.app')
print(json.dumps(r['evaluation'], indent=2))
"
```

---

## Environment Variables (`.env`)

The critical ones for local development:

```env
MOCK_MODE=false                        # false = real LLM + real browser scrape
LLM_PROVIDER=groq                      # production default — groq | openai | anthropic | ollama
LLM_TEXT_MODEL=llama-3.3-70b-versatile # production default
LLM_VISION_PROVIDER=anthropic          # anthropic | ollama
OLLAMA_BASE_URL=http://localhost:11434/v1   # /v1 suffix required for OpenAI SDK compat (inactive when LLM_PROVIDER=groq)
OLLAMA_TEXT_MODEL=llama3.2:latest
OLLAMA_VISION_MODEL=llava:latest
KNOWLEDGE_LAYER_ENABLED=false          # true requires Qdrant + Supabase
IMAGE_GENERATION_ENABLED=false         # true enables Bannerbear carousel slide generation
BANNERBEAR_API_KEY=bb_pr_...           # Bannerbear project API key
BANNERBEAR_TEMPLATE_UID=YJBpekZX8X9wZ2XPnO  # template UID — must have layers: background_color, accent_bar, logo, slide_label, headline, body_text
BANNERBEAR_TIMEOUT_SECONDS=30          # HTTP timeout for Bannerbear API calls
```

Only the active provider's API key is required (e.g. only `GROQ_API_KEY` when `LLM_PROVIDER=groq`).

---

## Architecture

### The 9-Agent Pipeline

Agents run in order. Steps 2+3 are parallel; steps 6+7 are parallel.

```
1. input_processor  → InputPackage      (Playwright scrape + CSS tokens + screenshot)
2. ui_analyzer      → BrandProfile      (vision LLM — design category, colors, writing_instruction)
3. product_analysis → ProductKnowledge  (text LLM — features, proof points, pain points)
4. planner          → ContentBrief      (selects content type, arc, pillar, platform rules)
5. strategy         → StrategyBrief     (selects pain point, claim, proof point, hook direction)
6. copywriting      → str               (raw copy — no JSON, no formatting)
7. visual_gen       → dict              (image_prompt, suggested_format — video is Phase 3)
8. formatter        → FormattedContent  (applies platform rules; LLM for LinkedIn, programmatic for others)
9. evaluator        → EvaluatorOutput   (scores 1-5 × 4 dims; passes if all ≥ 3; max 2 retries)
```

`pipeline.run_linkedin()` is the simple validation entry point (skips visual gen). `pipeline.run_stream()` is the full SSE production chain.

### LLM Abstraction Rule — Never Break This

No agent imports any LLM SDK directly. Every agent calls only:

```python
from llm.client import chat_completion   # text agents
from llm.client import vision_completion # ui_analyzer only
```

All provider routing lives exclusively in `llm/client.py`. Switching providers is a one-line `.env` change.

### MOCK_MODE

`settings.MOCK_MODE` is a global bool. Every agent checks it at the top of `run()` and returns a deterministic mock instead of calling `chat_completion()`. This means the entire pipeline — including all 9 agents — is mockable with zero network calls. Tests rely on this.

### Schema Contracts

Pydantic models in `schemas/` enforce hard invariants. Key ones to know:

- `ContentBrief`: platform/content_type combos are validated (e.g. twitter requires `thread`); carousel requires `slide_count_target` 6-10; blog requires `word_count_target` and `seo_keyword`.
- `StrategyBrief`: `proof_point` must match verbatim from `ProductKnowledge.proof_points[].text`; `narrative_arc` must match `ContentBrief.narrative_arc` exactly. Cross-schema validation is called explicitly via `validate_against_product_knowledge()` and `validate_against_content_brief()` — these warn but do not crash in agent real mode.
- `EvaluatorOutput`: `passes` and `overall_score` are **always computed by Pydantic validators** — never set by the LLM. Strip them from LLM output before parsing.
- `FormattedContent`: exactly one platform content field (`linkedin_content`, `twitter_content`, etc.) must be non-null, and it must match `platform`.
- `BrandIdentity`: consolidated brand visual data assembled by `pipeline.build_brand_identity()` from `InputPackage` + `BrandProfile` + `ProductKnowledge`. No LLM — deterministic construction only. Logo fields (`logo_bytes`, `logo_url`, `logo_confidence`) enforce an all-or-nothing contract (all None or all non-None). `logo_compositing_enabled` is computed: `True` only when `logo_confidence == "high"`. Binary fields (`logo_bytes`, `og_image_bytes`) are excluded from JSON output via `model_dump(exclude=...)`. Consumed by Visual Gen (Step 7) and Phase 2 image pipeline. **Color normalisation:** all color fields (`primary_color`, `secondary_color`, `accent_color`, `background_color`, `foreground_color`) are guaranteed `#rrggbb` hex at construction time. `_to_hex()` in `schemas/brand_identity.py` converts rgb/rgba, oklch, oklab, hsl/hsla, and 3/8-digit hex. A `field_validator` enforces hex as a second layer. `build_brand_identity()` wraps every color with `_to_hex()` before passing to the constructor. Transparent/inherit/currentColor map to None. Unknown formats log a warning and return None (fallback `#000000`/`#ffffff` applied in `build_brand_identity`). **Phase 2 note:** Bannerbear requires hex — never pass `BrandProfile` color values directly to Bannerbear. Always use `BrandIdentity.css_color_vars` which is the correct interface for template injection and is always hex.

### Prompt Files

System prompts for copywriting and evaluation live in `prompts/*.yaml` (owned by Person B). Agents load them via `prompts/loader.py`. Inline fallback prompts exist in each agent for when YAML files are absent. The YAML files take precedence when present.

### Platform Rules

Mechanical formatting constraints for each platform live in `config/platform_rules.json`. The formatter reads this at runtime — do not hardcode platform limits in agent code.

### Knowledge Layer (disabled by default)

`KNOWLEDGE_LAYER_ENABLED=false` skips Qdrant + Supabase entirely. When enabled, `pipeline.run_stream()` queries prior approved runs before the Planner and persists approved copy after a successful evaluation. The approval endpoint is `POST /runs/{id}/approve`.

---

## Known Issues (Input Layer — Return to Later)

- `--sx-` token prefix filter not fully applied on Linear (257 tokens vs expected ~30)
- `tagline` returns None consistently — verbatim extraction not working
- `description` includes raw nav text on some sites
- Lemon Health pain_points contaminated with engineering context from LLM training data

## Known Issues — UI Analyzer

These are known and accepted for now. Return to them after switching to Groq and validating real-mode output quality.

**design_category default bias**
`_normalize_design_category()` in `agents/ui_analyzer.py` falls back to `"developer-tool"` when the LLM returns an unrecognized value. Light-background consumer sites (e.g. health apps, warm palette brands) get misclassified. Fix: infer from background color token before defaulting.

**tone default bias**
`_normalize_tone()` falls back to `"technical"` for unrecognized values. Consumer and warm-brand sites get `"technical"` instead of `"playful"` or `"minimal"`. Same sites affected as above.

**writing_instruction is category-based not brand-specific**
`_build_writing_instruction()` generates copy from design_category rather than actual token signals. Output is generic per category rather than specific to the brand (e.g. does not reference Inter Variable weight 510, indigo #5e6ad2, or Berkeley Mono by name). Fix: extract specific named token values and embed them.

**font_family returns [object Object] on some sites**
The Playwright JS evaluation returns a font-face object instead of a string on some sites. The extractor needs to handle this and stringify the value before storing in css_tokens.

**primary_color falls back to #000000 on some sites**
BrowserStack and Hasura returned #000000. Likely the CSS `--sx-` token prefix filter or the color extraction logic didn't find a distinctive brand color variable. May require expanding the CSS token name patterns searched for primary color.

**design_category accuracy with Llama 4 Scout is poor (4/10 on Indian SaaS)**
Session 4 ran against `llama-4-scout-17b-16e-instruct` due to Groq 70B daily quota exhaustion. Only 4/10 sites classified correctly vs 10/10 expected design_category. Both v2.2 few-shot anchors (Razorpay→bold-enterprise, Chargebee→minimal-saas) were wrong. This is a model capability gap on 4 Scout, not a prompt regression. Re-validate with 70B — the v2.2 prompts were calibrated for and validated against 70B only.

**Impact**: Low while running on mock input or weak models. Becomes important when switching to real input + Groq, because writing_instruction feeds directly into Copywriter system prompt.
Priority: fix after first successful Groq real-mode run.

## Platform Coverage Status

- linkedin carousel: ✅ working
- linkedin text_post: ✅ working (Planner selects based on signals)
- linkedin single_image, poll: schema ready, not wired in Formatter
- twitter thread: ✅ working — char counts computed by Python, hashtags enforced in final tweet only
- instagram carousel: ✅ working — real hashtags from product category, no placeholder tags
- instagram single_image: schema ready, not wired
- blog: schema ready, not wired

## Logo Extraction Status

- InputPackage.logo_bytes/logo_url/logo_confidence: ✅ implemented
- Extraction priority: apple-touch-icon → large icon (≥192px) → header img with "logo" attr → inline SVG → og:image → favicon
- MOCK_MODE: returns deterministic PNG mock bytes (1208 bytes, "high" confidence)
- Phase 2 usage: Pillow compositing (not yet wired — Phase 2)
- All-or-nothing contract enforced by Pydantic `model_validator`
- Validation results (5/5 sites extracted):

| Site | Confidence | Source | Size |
|---|---|---|---|
| linear.app | high | apple-touch-icon | 25 KB |
| searchable.com | high | header img | 5 KB |
| razorpay.com | medium | og:image | 2.3 MB |
| chargebee.com | high | apple-touch-icon | 4 KB |
| freshworks.com | high | apple-touch-icon | 23 KB |

## Formatter Behaviour Notes

- **LinkedIn**: hashtags stripped from LLM body, rebuilt at end only
- **Instagram**: hashtags padded from `_CATEGORY_IG_TAGS` and `_GENERIC_IG_PAD_TAGS` when LLM returns fewer than 20; if LLM returns `body` as a list, it is joined with `"\n\n"` before building `InstagramContent` (weak models sometimes return a list of paragraph strings)
- **Twitter**: `tweet_char_counts` always recomputed by Python, never trusted from LLM output
- **Evaluator**: copy wrapped in `--- COPY TO EVALUATE ---` delimiters, tweets numbered (Tweet 1/N format) before scoring

## Evaluator Calibration Rules (Python-enforced, not LLM-trusted)

These rules are applied in Python after parsing the LLM's score output — the LLM cannot override them:

- **Fabricated stat cap**: any numeric stat in copy (e.g. `63%`, `2x`) that is NOT present verbatim in `proof_point` or `primary_claim` → `accuracy = 1`. This catches hallucinated statistics from the model's training data (e.g. Chargebee dunning stats appearing in Searchable copy).
- **Generic opener cap**: hooks starting with "Discover how", "Are you struggling", "Your daily friction is" → `engagement` capped at 3.
- **passes and overall_score**: always computed by Pydantic validators, never set by the LLM.

## Planner Behaviour Notes

- **reasoning fallback**: if the LLM echoes the signals dict back as the `reasoning` field (starts with `{` or `[`), or if the string is < 20 chars, it is replaced with a generated sentence: `"{feature_count} features and {proof_point_count} proof points support {content_type} format for {platform}."`
- **narrative_arc / content_pillar / funnel_stage**: normalized from human-readable LLM values to schema literals before building `ContentBrief`. Unrecognised values are mapped via keyword matching; unmatched values fall back to defaults.

## Bug Fixes & Root Causes

This section documents bugs found in real-mode pipeline runs, their root causes, and fixes applied. Use this to identify similar issues in future sessions.

---

### BUG-001 — Fabricated statistics in generated copy

**Found:** Real-mode run against searchable.com, all platforms
**Symptom:** Copy contained numeric claims not present in proof_points:
- "Searchable has helped over 200 companies" (LinkedIn) — proof_point had "206%", model invented "200 companies"
- "40% of brands waste up to 12 hours each month" (Twitter) — proof_point had "40% visibility increases", model fabricated "12 hours"

**Root cause:** Copywriter prompt said "use the proof_point" but did not explicitly forbid the LLM from inventing adjacent numeric claims. LLMs extrapolate from training data when given partial numeric context ("40% visibility" → fabricates "40% of brands waste X hours").

**Fix:**
1. Added `FABRICATION PROHIBITION` block to `prompts/copywriting_v1.yaml` immediately before the PROOF POINT RULE — includes explicit permitted/forbidden examples and the exact patterns to avoid (frequency invention, count invention, rounding/approximation)
2. Added `_check_fabricated_stats()` to `agents/evaluator.py` — pre-check before the LLM call that scans copy numbers against proof_point + primary_claim numbers; injects violation as `PRE-DETECTED VIOLATION:` prefix to system prompt when fabricated stats detected
3. Existing `_apply_fabricated_stat_cap()` post-processes the LLM's accuracy score down to 1 when fabricated stats are found

**Watch for:** Any time a proof_point contains a number, check that the copy does not introduce *different* numbers in the same context. The model will approximate, round, or combine stats. The pre-check fires before LLM scoring. Year numbers (2020–2030) are excluded from detection.

---

### BUG-002 — Twitter Copywriter leaks meta-instructions into output

**Found:** Real-mode Twitter run against searchable.com
**Symptom:** Tweet 3 contained "(Formatter will split this single long block into two separate tweets)" — an internal note exposed in the output. Also leading number prefixes like "3 " left in tweet bodies.

**Root cause:** The Copywriter prompt described the Formatter's role in a way the model echoed back. Weak models narrate their uncertainty instead of resolving it.

**Fix:**
1. Added explicit "no meta-annotations" rule to Twitter section of `prompts/copywriting_v1.yaml`
2. Added `_clean_tweet()` in `agents/formatter.py` that strips parenthetical notes matching `(Formatter...)`, `(Note...)`, `(This...)`, `(Split...)` and leading tweet number prefixes (`3/ `, `3 `) before building `TwitterContent`. Applied to every tweet during normalization.

**Watch for:** Any tweet containing parenthetical text. Also watch for tweets starting with a digit followed by space or slash — these are numbering artifacts. `_clean_tweet()` handles both but new patterns may emerge with different models.

---

### BUG-003 — Instagram preview_text truncated mid-sentence

**Found:** Real-mode Instagram run against searchable.com
**Symptom:** `preview_text` ended on "your" — incomplete sentence fragment, not a "complete emotional statement"

**Root cause:** Simple `_truncate_at_word_boundary(text, 125)` call with no sentence boundary check. The formatter cut at char 125 regardless of whether that fell mid-sentence.

**Fix:** Replaced with `_truncate_to_sentence()` in `agents/formatter.py`. Priority: sentence boundary within 125 chars → sentence boundary within 150 chars → word boundary within 125 chars. Applied in `_instagram_postprocess()` and both programmatic Instagram fallback paths.

**Note:** `InstagramContent.preview_text` has a `max_length=125` schema constraint, so the 150-char extension only applies when `_truncate_to_sentence()` is used outside the Instagram schema path. Within Instagram, it must stay at 125.

**Watch for:** `preview_text` that does not end with `.`, `!`, or `?`. This happens when the LLM writes one long sentence (> 125 chars) with no mid-sentence punctuation. The fallback to word boundary is correct per spec — it avoids mid-word cuts but cannot guarantee a sentence end.

---

### BUG-004 — Ollama llama3.2 fabrication rate vs Groq llama-3.3-70b

**Found:** Real-mode run against searchable.com, all platforms
**Context:** After implementing the fabrication prohibition rule in the Copywriter prompt and `_check_fabricated_stats()` pre-check in the Evaluator, all three platforms still failed with `accuracy=1` on every retry when using Ollama llama3.2. The fabricated stats changed each retry (`3x`, `5x`, `8x`, then `40%`, `63%`, `90%`) confirming the model was not following the prohibition rule despite it being explicit.

**Root cause:** llama3.2 via Ollama (7B/8B parameter range) does not reliably follow complex multi-rule prompts. When the actual proof_points contain no numbers ("Trusted by leading brands", "Proven results with measurable ROI"), the model defaults to inventing plausible-sounding stats from training data rather than writing number-free copy. This is a model capability floor issue, not a prompt design issue.

**Fix:** Switched `LLM_PROVIDER` from `ollama` to `groq` with `llama-3.3-70b-versatile`. The 70B model follows the fabrication prohibition rule reliably and writes compelling copy from qualitative proof points without inventing numbers.

**Result:** All three platforms: accuracy 1→5, passes False→True, retry_count 2→0. Groq comparison:

| platform  | ollama_acc | groq_acc | ollama_pass | groq_pass |
|-----------|-----------|---------|------------|---------|
| linkedin  | 1         | 5       | False      | True    |
| twitter   | 1         | 5       | False      | True    |
| instagram | 1         | 5       | False      | True    |

**Watch for:** If fabrication recurs on Groq, the issue is in proof_point extraction quality (Product Analysis returning weak qualitative proof points instead of real stats from the page). The fix is to improve the Product Analysis prompt to extract only concrete, specific proof points and skip vague qualitative claims like "Proven results with measurable ROI".

---

### PROMPT UPDATE — v1 → v2 (Person B, March 2026)

**Prompts updated:**
- `ui_analyzer_v1.yaml` → v2.2
- `copywriting_v1.yaml` → v1.3
- `evaluator_v1.yaml` → v1.2

**Key changes:**
1. `writing_instruction` (ui_analyzer) — now outputs pure copywriting guidance (sentence structure, register, banned words, first-line pattern). Zero design references. Previously read like a design system doc.
2. `hook_direction` rule (copywriting) — HOOK DIRECTION RULE section added. `hook_direction` is now binding, not a suggestion. Includes WRONG/RIGHT example pair from actual pipeline output.
3. Instagram `preview_text` rule (copywriting) — complete rewrite. MUST/MUST NOT lists, three verbatim good examples, explicit subject+verb requirement.
4. Engagement score-2 anchors (evaluator) — three real pipeline hooks added as explicit score-2 negative examples. Specificity test added: "Can a specific person at a specific time of day see themselves in this hook?"

**Few-shot examples added:**
- ui_analyzer: 6 examples (all 5 design categories + borderline Razorpay). All grounded in Indian SaaS companies.
- copywriting: 6 examples across platforms and arcs. Indian SaaS: Leegality, Razorpay Payroll, Chargebee.
- evaluator: 6 examples including FAIL cases with specific `revision_hint`s.

**Validated results vs v1 Groq baseline (searchable.com):**

| platform  | dim        | v1  | v2  | delta |
|-----------|-----------|-----|-----|-------|
| linkedin  | tone_match | 4   | 5   | +1    |
| linkedin  | overall    | 4.0 | 4.25| +0.25 |
| twitter   | tone_match | 3   | 4   | +1    |
| twitter   | overall    | 4.0 | 4.25| +0.25 |
| instagram | engagement | 3   | 4   | +1    |
| instagram | tone_match | 4   | 3   | -1    |

design_category consistent across all three runs: `minimal-saas` (was inconsistent in v1).

**Watch for:** Chargebee 63% stat appears in copywriting few-shot example cw_ex_05 (TikTok). If this stat appears in copy for non-Chargebee products, it is a few-shot contamination issue. The FABRICATION PROHIBITION rule should prevent this but monitor. Also: Instagram tone_match dropped 4→3 in this run — possible conflict between new `preview_text` rule (complete sentence) and evaluator's tone calibration for the `minimal-saas` category. Worth re-running to check if this is variance or a regression.

---

### BUG-005 — StrategyBrief crashes when LLM returns proof_point_type=null

**Found:** Real-mode run against razorpay.com, Session 4 (Llama 4 Scout)
**Symptom:** Pipeline crashed with `ValidationError: proof_point_type — Input should be 'stat', 'customer_name', ... [input_value=None]`

**Root cause:** Llama 4 Scout (17B MoE) omitted `proof_point_type` from JSON output, returning null for a required Literal field. The strategy agent had no fallback before passing `**data` to the Pydantic constructor.

**Fix:** Added normalization in `agents/strategy.py` after `parse_json_object()`:
1. Check if `proof_point_type` is a valid literal value
2. If not: try to infer from the matching proof_point entry in `ProductKnowledge.proof_points` (by text match)
3. If no match: default to `"stat"` (most common type)

**Watch for:** Any StrategyBrief construction. Other required Literal fields (cta_intent, appeal_type, narrative_arc) could have the same problem on weaker models. `narrative_arc` is already force-set from `content_brief.narrative_arc` in code (immune). `cta_intent` and `appeal_type` have no fallback yet — add if they crash.

---

### BUG-006 — rgb() and oklch() color values reaching BrandIdentity

**Found:** Session 4 — Indian SaaS validation run (6/10 sites affected)
**Symptom:** `primary_color` stored as `rgb(193, 95, 60)`, `oklch(98.4% .006 85.5)`, or `rgb(1, 1, 1)` — not hex. Bannerbear template API requires hex. Phase 2 image generation would fail silently or raise on color injection.

**Root cause:** CSS `getComputedStyle()` returns colors in the browser's computed format, which is not necessarily hex. Modern sites increasingly use oklch/oklab color spaces. The UI Analyzer returned whatever format the browser computed.

**Fix:** Added `_to_hex()` in `schemas/brand_identity.py`. Handles: `#hex` (3/6/8-digit), `rgb`/`rgba`, `oklch`, `oklab`, `hsl`/`hsla`. Applied in `build_brand_identity()` for all five color fields. `BrandIdentity` `field_validator` provides a second enforcement layer.

**Watch for:** New CSS color spaces (`color()`, `display-p3`, `rec2020`) may appear on cutting-edge sites. `_to_hex()` will log a warning and return `None` for unknown formats — Phase 2 falls back to `#000000`/`#ffffff` rather than crashing.

---

### BUG-007 — Accent bar invisible when primary_color == background_color

**Found:** Phase 2 validation — Linear run 2
**Symptom:** `accent_bar` rendered same color as background — completely invisible. Linear `primary_color` extracted as `#08090a` (near-black) matching `background_color` `#08090a` exactly.

**Root cause:** CSS token extraction is not deterministic for which token becomes `primary_color`. On some runs the foreground token wins (`#f7f8f8`), on others the background token wins (`#08090a`). When background wins, `primary == background` and the accent bar disappears. Contrast ratio in that case is 1.0.

**Fix:** Added `_pick_accent_color()` in `agents/image_gen.py`. Tries `primary_color` → `secondary_color` → `accent_color` in order, picking the first with `contrast_ratio > 1.5` against background. Falls back to `#ffffff` or `#000000` when all candidates are too close to bg. `_luminance()` and `_contrast_ratio()` use WCAG 2.1 linearisation formula.

**Validated:** Unit test confirms Linear scenario: `primary=#08090a == background=#08090a` → `_pick_accent_color` returns `#5e6ad2` (secondary_color, contrast 4.24).

**Watch for:** Brands where all three color fields (`primary`, `secondary`, `accent`) are very close to the background — monochrome brands. The `#ffffff`/`#000000` fallback handles it but is not brand-specific. Also: Lemon Health `primary_color=#ffdc42` (yellow) on `#ffffff` background has contrast 1.07, below threshold — `_pick_accent_color` correctly falls back to `#000000`. This is visually correct (yellow accent bar on white is nearly invisible) but brand-incorrect. Phase 3: allow user accent color override.

---

### IMPROVEMENT — Logo extraction priority 3.5 (SVG in header/nav)

**Added:** Session after Phase 2 validation
**Problem:** Sites built on Framer/Webflow/component frameworks render logos as inline SVGs inside JS components. The previous priority 4 (basic SVG extraction) only took the first SVG in `header` without any quality checks — it could grab a decorative icon instead of the logo. Confirmed affected: `lemonhealth.ai`, `browserstack.com`, `moengage.com`.

**Fix:** Replaced the simple priority 4 SVG block with an enhanced version in `_extract_logo()` in `agents/input_processor.py`:
- Extended selectors: `header svg, nav svg, [role="banner"] svg, .navbar svg, .nav svg, .header svg`
- Color match: checks if brand color from `css_tokens` appears as a fill value in the SVG
- Label match: checks for `logo`, `brand`, `mark`, `icon`, `aria-label`, `title` in SVG markup
- Size validation: bounding box ≥ 24×24px
- Path-count fallback: first SVG with ≥2 `<path>` elements at valid size (catches logos with no explicit label)
- `_extract_logo()` now accepts `css_tokens: dict | None = None` — passed from `_scrape_page_sync()`

Priority order in docstring updated: old priority 4 (inline SVG) is now labeled "Priority 3.5", og:image becomes "Priority 4".

**Still deferred to Phase 3:**
- Apple-touch-icon black background baked in — needs Pillow background removal before compositing on light backgrounds
- Font injection into Bannerbear — template uses default font, brand fonts not yet applied to text layers

---

## Indian SaaS Validation — Session 4 Results

Date: March 2026
URLs: 10 Indian SaaS companies from test_data/indian_saas_companies.csv
Platform: LinkedIn only
Model: **Llama 4 Scout (meta-llama/llama-4-scout-17b-16e-instruct) via Groq** — NOT llama-3.3-70b-versatile. Daily 100K token quota exhausted. Results should be re-validated with 70B.

Results summary:
- Pipeline passes:      10/10 (after BUG-005 fix)
- Category correct:     4/10 (bold-enterprise: Freshworks, Zoho, CleverTap, MoEngage — Razorpay, Chargebee, Postman, Hasura, BrowserStack, Darwinbox all wrong)
- Logo high confidence: 6/10 (Chargebee, Freshworks, Postman, Hasura, Zoho, CleverTap)
- Phase 2 ready:        8/10 (BrowserStack and MoEngage have no logo or OG image)

Sites where design_category was wrong: Razorpay (got minimal-saas), Chargebee (got bold-enterprise), Postman (got bold-enterprise), Hasura (got minimal-saas), BrowserStack (got minimal-saas), Darwinbox (got minimal-saas)
— NOTE: Razorpay and Chargebee are v2.2 few-shot anchors that should be immune to misclassification with 70B. The 6/10 wrong rate is a Llama 4 Scout capability issue, not a prompt issue. Re-run with 70B to confirm.

Sites where logo was medium or missing: Razorpay (medium — og:image), Darwinbox (medium — Framer site), BrowserStack (None), MoEngage (None)

Sites where proof points were empty or boilerplate: Razorpay (0 real proof points — homepage is marketing-only, no stats in scraped text)

Sites that crashed: 0 (Razorpay crashed on first run, fixed by BUG-005 fix, re-ran successfully)

Key finding: The pipeline completes for all 10 Indian SaaS URLs once BUG-005 is fixed. The fabrication retry system worked correctly — Chargebee and Postman both had initial fabrications caught and corrected on retry. The input layer gaps are: (1) rgb() color format stored in BrandIdentity needs hex normalization before Phase 2; (2) thin scrapes on JS-heavy sites (Postman 307 words, Freshworks 568 words) limit proof point quality; (3) logo extraction failed for BrowserStack and MoEngage. Design category accuracy cannot be assessed until re-run with 70B model.

---

## Phase 2 — Image Generation (Bannerbear)

`agents/image_gen.py` produces branded carousel slide images via the Bannerbear template API. Runs after `formatter` and before the evaluator retry loop. Gated by `IMAGE_GENERATION_ENABLED=true` (default: false).

### Bannerbear template layer names

The template UID (`BANNERBEAR_TEMPLATE_UID`) must expose these named layers:

| Layer name         | Type   | Content                                     |
|--------------------|--------|---------------------------------------------|
| `background_color` | color  | `BrandIdentity.background_color` (hex)      |
| `accent_bar`       | color  | `BrandIdentity.primary_color` (hex)         |
| `slide_label`      | text   | `"01 / 05"` format; color = secondary_color |
| `headline`         | text   | Slide headline (max 120 chars + ellipsis)   |
| `body_text`        | text   | Slide body copy (max 280 chars + ellipsis)  |
| `logo`             | image  | Only injected when `logo_compositing_enabled=True` or `logo_confidence=="medium"` |

**Color values:** Always use `BrandIdentity` color fields — never pass raw `BrandProfile` values. All `BrandIdentity` colors are guaranteed `#rrggbb` hex at construction time.

### Copy splitting rules (LinkedIn carousel)

- **Slide 1:** `hook` as headline, first body paragraph as body_text
- **Slides 2–N:** remaining paragraphs split into pairs (para[i] = headline, para[i+1] = body_text)
- **Cap:** max 8 slides
- **Labels:** `f"{i+1:02d} / {total:02d}"` — added after splitting

### Logo behaviour

- `logo_compositing_enabled=True` (i.e. `logo_confidence=="high"`) → injects `logo` layer with `logo_url`
- `logo_confidence=="medium"` → also injects `logo` layer (may be an OG marketing image — logs warning)
- `logo_confidence` is `None` or `"low"` → omits `logo` modification; template default is used

### Disabled / degraded behaviour

| Condition                            | `generation_enabled` | `image_urls` | `error`         |
|--------------------------------------|----------------------|--------------|-----------------|
| `MOCK_MODE=true`                     | `False`              | 3 mock URLs  | `None`          |
| `IMAGE_GENERATION_ENABLED=false`     | `False`              | `[]`         | `None`          |
| `BANNERBEAR_API_KEY` not set         | `False`              | `[]`         | string message  |
| Individual slide API call fails      | `True`               | partial list | `"slide N failed"` |

### Known gaps (Phase 2)

- Images are generated from the **first** formatted output, not the final evaluator-approved copy. If the evaluator triggers a retry and the second copy is used, the images correspond to copy v1. Fix: defer image generation to after the final evaluator approval. Deferred to Phase 3.
- Bannerbear `synchronous=True` is not honored by all Bannerbear plan tiers. `_poll_bannerbear()` is the async fallback — called when the initial response has a `uid` but no `image_url`.
- Instagram and Twitter content types are not yet split into slides — `_split_into_slides()` only handles `linkedin_content`. Instagram uses `preview_text` + `body` as a single slide.
- **Apple-touch-icon black background** — icon files include a background fill; shows as a black box when composited on light-background brands. Fix requires Pillow background-removal before compositing. Deferred to Phase 3.
- ~~**primary_color == background_color**~~ — **Fixed** via `_pick_accent_color()`. See BUG-007.

---

## Key Patterns

**Weak-model-friendly design:** LLMs return flat JSON strings. Python enforces types, validates cross-schema contracts, and applies constraints. Never ask the LLM to enforce its own output constraints.

**Never crash on scrape failure:** `input_processor` catches all errors and returns a partial `InputPackage` with `scrape_error` set. Downstream agents must handle empty/partial text gracefully.

**`agents/_utils.py`** provides `parse_json_object()` (strips markdown fences, extracts `{...}`) and `utc_now_iso()`. Use these everywhere — do not inline JSON parsing in agents.

**Windows UTF-8:** The Windows terminal defaults to cp1252. `tests/conftest.py` reconfigures stdout/stderr to UTF-8. Any `print()` of scraped text in agents must use `sys.stdout.buffer.write(...encode('utf-8', errors='replace'))` or be removed.
