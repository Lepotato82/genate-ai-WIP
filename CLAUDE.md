# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Project Is

**Genate** is a multi-agent AI pipeline that takes a SaaS product URL and generates platform-specific marketing content (LinkedIn, Twitter/X, Instagram, Blog). The core differentiator is brand extraction: Genate reads actual CSS design tokens from a live page using Playwright + dembrandt, rather than guessing from screenshots or asking users to fill forms. No competitor does this.

Target market: **Indian SaaS** (Razorpay, Freshworks, Chargebee, etc.) — this is the uncontested home market. All copy and positioning should lead with the SaaS angle.

---

## Commands

```bash
# Install dependencies (uses uv, not pip)
uv venv .venv
uv sync --extra dev

# Activate venv
source .venv/bin/activate         # macOS/Linux
.venv\Scripts\activate            # Windows

# Install Playwright browser
.venv/Scripts/playwright install chromium    # Windows
.venv/bin/playwright install chromium        # macOS/Linux

# Install dembrandt (Node.js CSS token extractor — primary extraction method)
npm install -g dembrandt

# Start API server
uvicorn api:app --reload

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_research_agent.py -v

# Run a single test by name
pytest tests/test_research_agent.py::test_normalize_url -v

# Run only fast/unit tests (skip integration/network tests)
pytest tests/ -v -m "not integration"
```

All 454 tests are fast and require no network access. Integration tests (real API calls) are marked `@pytest.mark.integration` and must be run explicitly.

---

## Architecture: The 9-Agent Pipeline

`pipeline.py` chains all agents. Steps 2+3 run in parallel; Steps 6+7 run in parallel.

```
Step 1  input_processor   → InputPackage        (Playwright scrape, CSS tokens via dembrandt, logo via local CLIP ViT)
Step 2  ui_analyzer        → BrandProfile        (vision LLM classifies design_category from CSS/text — never sees page visually)
Step 3  product_analysis   → ProductKnowledge    (text LLM: features, proof points, pain points)
Step 3.5 research_agent   → ResearchProofPoint[] (Tavily web search for real third-party stats; gated by RESEARCH_AUGMENTATION_ENABLED)
Step K  knowledge layer   → KnowledgeContext     (Qdrant query of prior approved runs; gated by KNOWLEDGE_LAYER_ENABLED)
Step 4  planner            → ContentBrief        (content type, narrative arc, platform strategy; POST /generate accepts optional force_content_type to pin a specific type)
Step 5  strategy           → StrategyBrief       (selects pain point, claim, specific proof point, hook_direction)
Step 6  copywriter         → str                 (raw copy; Python regex validates CTA intent appears in last 20%; structured types — poll/story/single_tweet — receive type-aware mock and format-hint prompting)
Step 7  visual_gen         → dict                (image_prompt + suggested_format; background only — no logo/text)
Step 7.5 image_gen        → hero_url            (text-to-image via Pollinations/Fal; gated by HERO_IMAGE_ENABLED)
Step 8  formatter          → FormattedContent    (LinkedIn text uses LLM; poll/story/single_tweet dispatch to dedicated Python formatters; Twitter/IG/Blog are pure Python)
Step 9  evaluator          → EvaluatorOutput     (scores 1–5 × 4 dims; passes if all ≥ 3; max 2 retries)
Step K  knowledge persist  → (Supabase + Qdrant; gated by KNOWLEDGE_LAYER_ENABLED)
```

---

## Critical Design Rules

### LLM Abstraction — Never Break This
No agent ever imports Groq, Anthropic, or OpenAI SDKs directly. **All LLM calls go through `llm/client.py`** (`chat_completion()` and `vision_completion()`). Switching providers is a single `.env` change:

```env
LLM_PROVIDER=groq           # groq | openai | anthropic | ollama
LLM_VISION_PROVIDER=anthropic
LLM_TEXT_MODEL=llama-3.3-70b-versatile
LLM_VISION_MODEL=claude-haiku-4-5
```

Vision (UI Analyzer) is intentionally on a separate provider setting from text agents.

### MOCK_MODE
`MOCK_MODE=true` is the default in `config/settings.py`. With mock mode on, no API keys are needed — the pipeline returns deterministic mock data. Always develop and test with `MOCK_MODE=true` unless explicitly testing real API calls.

### Prompt Files
All agent system prompts live in `prompts/*.yaml` and are loaded via `prompts/loader.py`. If a YAML file is missing, the loader falls back to hardcoded inline defaults in the agent. Prompts are owned separately from agent code (see team structure below).

### Validation Is Deterministic
`schemas/` contains Pydantic models for every pipeline artifact. Python validators (not LLM judgement) enforce CTA presence, stat format, score capping, etc. When an LLM output fails validation, agents retry — don't weaken validators to paper over bad LLM output.

---

## Key Files

| File | Purpose |
|---|---|
| `GENATE_CONTEXT.md` | Authoritative project context — read this first for any new task |
| `agents/TODO.md` | Backlog with task history; shows what's done and what's open |
| `pipeline.py` | Orchestrator — wires all agents, handles parallelism and retry loop |
| `config/settings.py` | All feature flags and env vars with defaults |
| `llm/client.py` | ONLY file that knows which LLM provider is active |
| `prompts/loader.py` | Loads YAML prompts; agents call this, not file I/O directly |
| `config/platform_rules.json` | Per-platform formatting constraints (read by formatter at runtime) |
| `agents/_utils.py` | `parse_json_object()`, `utc_now_iso()` — shared by all agents |

---

## Feature Flags (Off by Default)

| Flag | Default | What it gates |
|---|---|---|
| `MOCK_MODE` | `true` | Bypass all real API calls |
| `RESEARCH_AUGMENTATION_ENABLED` | `false` | Tavily stat search (Step 3.5) |
| `KNOWLEDGE_LAYER_ENABLED` | `false` | Qdrant/Supabase memory |
| `IMAGE_GENERATION_ENABLED` | `false` | Bannerbear carousel slides |
| `HERO_IMAGE_ENABLED` | `false` | Stock/generative photo for compositor layouts — Pexels (real photos, consumer brands) or Pollinations (generative) |
| `HERO_IMAGE_PROVIDER` | `"pollinations"` | `pexels` \| `pollinations` \| `fal` — Pexels recommended for `consumer-friendly` brands |
| `COMPOSITOR_DUOTONE_ENABLED` | `true` | Brand-color duotone tint applied to hero photos in `photo_overlay` and `editorial_photo` layouts |
| `COMPOSITOR_PHOTO_TEXTURE_ENABLED` | `true` | Halftone dot overlay on hero photos for editorial/risograph print feel |
| `COMPOSITOR_CUTOUT_ENABLED` | `true` | Background removal on hero photos for `cutout_hero` layout (requires rembg) |
| `COMPOSITOR_DECORATIONS_ENABLED` | `true` | Stamp curated decorative illustrations (botanicals) onto `editorial_with_assets` and text layouts. Assets live under `assets/decorations/<design_category>/`; zero network calls |
| `LOGO_CLIP_ENABLED` | `true` | Local CLIP ViT for logo extraction |
| `LOGO_BG_REMOVAL_ENABLED` | `false` | Background removal on extracted logos |

---

## Groq Rate Limit Warning
The free tier for `llama-3.3-70b-versatile` is 100K tokens/day — exhausted in ~3–4 full pipeline runs against data-heavy sites. When exhausted, `llama-4-scout-17b-16e-instruct` has a separate quota but lower output quality. Plan quota usage accordingly; Dev Tier removes this limit.

---

## Team Ownership

| Area | Owner | Path |
|---|---|---|
| Agent code, pipeline, backend | Person A (Tech Lead) | `/agents/`, `pipeline.py`, `api.py`, `/knowledge/`, `/auth/` |
| Prompts + datasets | Person B | `/prompts/*.yaml`, `/datasets/*.jsonl` |
| Frontend (Next.js) | Person C | `/frontend/` |
| Research, schemas, validation | Person D | `/docs/`, `/test_data/`, `/schemas/` |

---

## Brand Post Quality — Lemon Health Gap Analysis (April 2026)

Reference posts: `sample_posts/` — five Lemon Health Instagram carousel samples.

Three layers of gap identified between current Genate output and Lemon Health quality:

### Visual gap — CLOSED (Tasks 24-26, 31-36)
- **Fix (Phase 9)**: Pexels API (Task 24) + duotone treatment (Task 25) + `stat_hero` layout (Task 26).
- **Fix (Phase 10)**: Photo halftone texture (Task 31) + `cutout_hero` layout (Task 32) + `photo_bottom_text` layout (Task 33) + slide-role layout mapping (Task 34) + logo top-right positioning (Task 35).
- **Fix (Phase 11)**: Decorative asset layer (Task 36) — `editorial_with_assets` layout + `agents/asset_layer.py` deterministic picker + curated starter pack under `assets/decorations/consumer-friendly/` (6 procedurally-generated botanicals via `scripts/generate_decorations.py`). Matches `lemonappUI.png` / `lemonappbehavior1.png` editorial style. Consumer-friendly only in v1; other categories extend by dropping PNGs into their respective folder — no code changes needed.
- **Compositor now has 16 layout archetypes**. Carousel slides get role-aware layouts: hook → photo-heavy, body → text-only or editorial-with-assets, CTA → bold/simple. Photo layouts apply duotone + halftone texture for editorial feel. Decoration stamp happens between layout draw and logo stamp so logo remains topmost.
- **Free photo APIs**: Pexels (200 req/hr, 20K/month, commercial use OK). Pollinations (generative, no key).

### Copy/structure gap — CLOSED (Tasks 27-29)
- Per-slide word budget (Task 27), engagement CTA `"engage"` intent (Task 28), stat-on-hook routing (Task 29).

### Research quality gap — CLOSED (Task 30)
- Clinical/medical research query tier for B2C health brands (CDC, JAMA, Lancet).

---

## Open Backlog (as of April 2026)

- **Task 18–20** (Phase 7): Interactive Canva-style editor — canvas hydration from pipeline JSON, real-time brand/copy overrides, PNG/PDF export. Frontend work for Person C using Fabric.js or Konva.js.
- **Task 21**: Advanced shadow piercing for logo extraction (CDP / Accessibility Tree).
- **Task 22**: Deterministic LinkedIn `long_form` word count enforcement (Copywriter retry gate or Evaluator length check).
- **Task 23**: Verify and fix new structured content types in real-mode LLM runs — poll, single_tweet, story, question_post. Only LinkedIn text posts and carousels have verified real-mode quality today. See `agents/TODO.md` for action items.
- **Tasks 24–30** (Phase 9): DONE — Pexels photos, duotone, `stat_hero`, word budget, engagement CTA, stat-on-hook, clinical queries.
- **Tasks 31–35** (Phase 10): DONE — Photo texture, `cutout_hero`, `photo_bottom_text`, role-based layout mapping, logo top-right.
