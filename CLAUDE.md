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
MOCK_MODE=true                         # false = real LLM + real browser scrape
LLM_PROVIDER=ollama                    # groq | openai | anthropic | ollama
LLM_VISION_PROVIDER=anthropic          # anthropic | ollama
OLLAMA_BASE_URL=http://localhost:11434/v1   # /v1 suffix required for OpenAI SDK compat
OLLAMA_TEXT_MODEL=llama3.2:latest
OLLAMA_VISION_MODEL=llava:latest
KNOWLEDGE_LAYER_ENABLED=false          # true requires Qdrant + Supabase
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

## Key Patterns

**Weak-model-friendly design:** LLMs return flat JSON strings. Python enforces types, validates cross-schema contracts, and applies constraints. Never ask the LLM to enforce its own output constraints.

**Never crash on scrape failure:** `input_processor` catches all errors and returns a partial `InputPackage` with `scrape_error` set. Downstream agents must handle empty/partial text gracefully.

**`agents/_utils.py`** provides `parse_json_object()` (strips markdown fences, extracts `{...}`) and `utc_now_iso()`. Use these everywhere — do not inline JSON parsing in agents.

**Windows UTF-8:** The Windows terminal defaults to cp1252. `tests/conftest.py` reconfigures stdout/stderr to UTF-8. Any `print()` of scraped text in agents must use `sys.stdout.buffer.write(...encode('utf-8', errors='replace'))` or be removed.
