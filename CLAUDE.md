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

## Key Patterns

**Weak-model-friendly design:** LLMs return flat JSON strings. Python enforces types, validates cross-schema contracts, and applies constraints. Never ask the LLM to enforce its own output constraints.

**Never crash on scrape failure:** `input_processor` catches all errors and returns a partial `InputPackage` with `scrape_error` set. Downstream agents must handle empty/partial text gracefully.

**`agents/_utils.py`** provides `parse_json_object()` (strips markdown fences, extracts `{...}`) and `utc_now_iso()`. Use these everywhere — do not inline JSON parsing in agents.

**Windows UTF-8:** The Windows terminal defaults to cp1252. `tests/conftest.py` reconfigures stdout/stderr to UTF-8. Any `print()` of scraped text in agents must use `sys.stdout.buffer.write(...encode('utf-8', errors='replace'))` or be removed.
