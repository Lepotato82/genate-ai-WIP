# Genate — Full Project Context
**Version:** 2.4
**Last updated:** March 2026
**Status:** Core 9-agent pipeline complete and validated. Phase 2 (Bannerbear image generation) shipped. Transitioning to Composite AI architecture (Deterministic Routing + Local ViT). **Phase 7 (interactive Canva-style editor)** is on the roadmap — see below; not yet shipped.

---

## What Genate Is

**Product name:** Genate  
**One-line position:** "The only AI content tool built specifically for SaaS companies — not coffee shops."

Genate is a multi-agent AI pipeline that takes a SaaS product URL (plus optional user uploads) and automatically generates platform-specific marketing content for LinkedIn, Twitter/X, Instagram, and Blog.

The core differentiator is not the content generation itself — it is the brand understanding that happens before any content is written. Genate extracts ground-truth brand data directly from CSS computed styles using Playwright browser automation. No competitor does this. Everyone else guesses from screenshots or asks users to manually input colors. Genate reads the actual design system.

---

## The Composite AI Architecture (The Moats)

Genate does not blindly throw massive LLMs at every problem. We use deterministic routing and specialized models:

### Moat 1 — CSS Token Extraction & Skipping the LLM
When Playwright renders a page, a JavaScript function reads computed CSS custom properties from `:root`. For a site like Linear, this produces exact values (`--color-brand-bg: #5e6ad2`). Visual identity data bypasses reasoning models entirely and pipes straight into the Bannerbear API to guarantee brand consistency. 

### Moat 2 — Strict Validation Layer (Sandboxing)
Pydantic schemas and Python validators heavily sandbox the text LLM. Fabricated stats and invalid CTAs are caught by Python regex before they ever reach the user or the next agent.

### Moat 3 — Knowledge Layer Memory
Brand memory gets smarter with every approved run. Strategy summaries, copy examples, and proof points are indexed into Qdrant per organisation.

### Moat 4 — SaaS-Specific Pipeline
Agents understand pain-agitate-solve narrative arcs, proof point grounding, messaging angle selection, and platform-native formats. 

### Moat 5 — Research Augmentation (Step 3.5)
Every content run is automatically enriched with real third-party industry statistics from Gartner, Forrester, McKinsey, etc. via Tavily search. 

---

## Market Position

Pomelli (Google-backed, most technically sophisticated competitor) is geo-locked to US, Canada, Australia, and New Zealand. The entire Indian SaaS ecosystem — Razorpay, Zerodha, Groww, Freshworks, Zepto, Chargebee — cannot access it. 

**The Indian SaaS market is Genate's uncontested home market.** All copy, positioning, and product language should lead with the SaaS angle and reflect this market.

---

## The 9-Agent Pipeline

Agents execute in the following order. Steps 2+3 run in parallel. Steps 6+7 run in parallel. 

### Step 1 — Input Processor
Playwright browser automation renders the target URL, extracts rendered text, runs CSS token extraction (`getComputedStyle()`), takes a screenshot, and packages an `InputPackage`. 
*Logo extraction:* After apple-touch-icon and large `rel=icon`, **local CLIP** scores header/nav screenshots (including **open shadow roots** via `_LOGO_DEEP_QUERY_JS` in `input_processor`) before header `img` heuristics and **`og:image`**. Optional **`LOGO_OG_IMAGE_MAX_BYTES`** / **`LOGO_OG_IMAGE_MAX_EDGE_PX`** skip oversized `og:image` assets. Optional **`LOGO_OCR_ENABLED`**, **`LOGO_BG_REMOVAL_ENABLED`**, **`LOGO_CLIP_*`** box filters — see `config/settings.py`.

**Strategic note (for future agents):** Logo extraction is now 95% reliable. If extraction returns `low` confidence, it is likely a closed shadow root or non-standard rendering; do not attempt further JS-based debugging. Reference **Task 9** in the backlog ([`agents/TODO.md`](agents/TODO.md) — Phase 6: Advanced Shadow Piercing / CDP).

### Step 2 — UI Analyzer *(parallel with Step 3)*
Takes the extracted CSS tokens and uses a text LLM to classify the brand's design category (`minimal-saas`, `bold-enterprise`, etc.) based purely on hex codes, font weights, and spacing units. The LLM does *not* see the website visually. Returns a `BrandProfile` containing a `writing_instruction` injected directly into the Copywriter.
**Model:** Groq `llama-3.3-70b-versatile`

### Step 3 — Product Analysis *(parallel with Step 2)*
Analyses scraped + user-provided text. Extracts features, benefits, proof points, pain points, and messaging angles. Returns a `ProductKnowledge` Pydantic model. If no stats exist, a Python validator smoothly injects a fallback.
**Model:** Groq `llama-3.3-70b-versatile`

### Step 3.5 — Research Agent *(parallel-capable, after Step 3)*
Searches for real third-party industry statistics using Tavily web search. Validates the stat by checking key words appear in the original content (fabrication prevention). 
**Gating:** `RESEARCH_AUGMENTATION_ENABLED=false` by default.

### Step K — Knowledge Layer Query *(optional)*
Queries Qdrant for semantically relevant context from previous approved runs.

### Step 4 — Planner
Selects content type, narrative arc, content pillar, and platform-specific strategy. Returns a `ContentBrief`.

### Step 5 — Strategy
Selects the specific pain point to lead with, the primary claim, and exactly which proof point from `ProductKnowledge.proof_points` to use. Returns a `StrategyBrief`.

### Step 6 — Copywriting Agent *(parallel with Step 7)*
Writes raw copy executing the `StrategyBrief`. Strict Python validation (`CTA_SIGNALS`) ensures the requested CTA intent actually appears in the final 20% of the text.

**Backlog — LinkedIn `long_form` length:** For `ContentBrief.content_depth == "long_form"`, target word counts (e.g. 600–900w) are communicated via the Copywriter user message (`_depth_instruction()` in `copywriter.py`) and YAML; there is **no post-generation word-count gate** in Python, and the Evaluator does not score minimum length. Real runs on `lemonhealth.ai` vs `searchable.com` (see `test_data/pipeline_real_*_20260331T*.json`) showed the same `long_form` brief but **large variance** in `formatted_content.linkedin_content.full_post` length. **Task 14** in [`agents/TODO.md`](agents/TODO.md) tracks deterministic enforcement (retry and/or evaluator).

### Step 7 — Visual Gen Agent *(parallel with Step 6)*
Generates an image generation prompt and a `suggested_format`.

### Step 7.5 — Image Gen *(Phase 2, after Formatter)*
Converts LinkedIn carousel copy into Bannerbear API calls. Returns branded slide image URLs using exact hex codes.

### Step 8 — Formatter
Applies platform-specific structural rules. 
*Note:* Twitter, Instagram, and Blog are formatted *programmatically* via Python string manipulation. Only LinkedIn utilizes an LLM for formatting.

### Step 9 — Evaluator (with retry loop)
Scores the formatted output on four dimensions (1-5 each). Python post-processes scores (e.g., capping accuracy to 1 if hallucinated numbers are detected). `passes` is computed deterministically.

### Step K (post) — Knowledge Layer Persist
Stores `BrandProfile`, `ProductKnowledge`, `StrategyBrief`, and final approved copy into Supabase and Qdrant.

---

## Phase 7 — Interactive Editor (Canva-style) *(roadmap)*

**Product requirement:** Final generated output must be **human-editable** before publish — changeable colors, logo, and text (and fonts where the pipeline exposes them), comparable to Canva — not only a one-way render to static PNGs.

**Project file model:** The same strict, validated JSON the pipeline already produces (persisted runs, SSE aggregates, or captures such as `test_data/pipeline_real_*.json`) is the **initial state** for a **client-side canvas**. It is the “project file” the editor hydrates. Bannerbear remains valid for **unattended** template-based slides; the editor path is for **human-in-the-loop calibration** and **export** after tweaks.

**Data mapping (hydration):**

- **Text** — `FormattedContent` (platform-specific fields, e.g. LinkedIn `full_post` / carousel slices) maps to editable text layers on the canvas.
- **Colors** — `BrandIdentity` hex fields (`primary_color`, `secondary_color`, `accent_color`, `background_color`, `foreground_color`) and `css_color_vars` supply defaults; UI overrides update local editor state and re-render.
- **Logo** — `logo_url` and user uploads; `logo_bytes` is often omitted from JSON serialisation — hydration may require a signed URL, API fetch, or upload path.
- **Fonts** — `BrandIdentity` / CSS-derived font-family strings load into the editor where available.

**Frontend direction:** [frontend/](frontend/) (Next.js) plus **Fabric.js** or **Konva.js** for an object-model canvas (draggable layers, per-object edit). A **Brand Calibration** sidebar applies live overrides to the in-memory `BrandIdentity` + `FormattedContent` shape. **Export** flattens to high-resolution PNG per slide or multi-page PDF for carousels (client-side or via a thin export service — implementation detail left to Task 20).

**Vision / hero imagery (later):** When Visual Gen + image APIs produce backgrounds, treat the raster as a **bottom canvas layer**; copy and logo stay editable **top layers** (aligns with Phase 6 Tasks 16–17).

**Backlog:** [`agents/TODO.md`](agents/TODO.md) — Tasks **18** (hydration), **19** (real-time overrides), **20** (export/flatten).

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| LLM inference (production) | **Groq** (`llama-3.3-70b-versatile`) | API · 100K TPD free tier |
| Local SLMs (Planned) | **CLIP ViT** (`openai/clip-vit-base-patch32`) | Vision Transformer for deterministic logo extraction (runs locally <1GB VRAM) |
| Web scraping | **Playwright** + **Browserless** | Playwright for CSS token extraction |
| Scraping proxies | **Bright Data** | Only for blocked enterprise sites |
| Image generation | **Fal.ai** / **Bannerbear** | Programmatic templates |
| Vector database | **Qdrant** | Self-hosted on Railway |
| Relational database | **Supabase** | Postgres + row-level security |
| Authentication | **Clerk** | Org management + API key support |
| Backend framework | **FastAPI** + **Celery** + **Redis** | Async · SSE streaming |
| Frontend framework | **Next.js** + **Shadcn/ui** | SSR |
| Editor canvas *(Phase 7)* | **Fabric.js** or **Konva.js** | Hydrate from pipeline JSON; editable layers; export to PNG/PDF |
| LLM observability | **LangFuse** | Traces every agent call |
| Payments | **Lemonsqueezy** | Indian GST compliance · UPI support |

---

## LLM API Flexibility — Critical Design Requirement

No agent imports the Groq SDK, Anthropic SDK, or any LLM provider SDK directly. All provider-specific code lives in one place (`llm/client.py`). Switching providers is a one-line `.env` change.

---

## Team Structure

| Person | Role | Primary ownership |
|---|---|---|
| Person A (Tech Lead) | Agent code, pipeline, backend, deployment | `/agents/`, `/pipeline.py`, `/api.py`, `/knowledge/`, `/auth/` |
| Person B | Prompts + dataset collection | `/prompts/*.yaml`, `/datasets/*.jsonl` |
| Person C | Frontend / UI | `/frontend/` (Next.js) |
| Person D | Research, schemas, validation | `/docs/`, `/test_data/`, schema specs |

---

## API Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Health check |
| `GET` | `/analyze` | None | Input Processor + UI Analyzer only. Returns `BrandProfile`. |
| `POST` | `/generate` | JWT | Full pipeline run. SSE stream (`text/event-stream`). |
| `POST` | `/runs/{id}/approve` | JWT | Activates Knowledge Layer learning for the approved run. |
| `POST` | `/auth/register` | None | Create org + user |
| `POST` | `/auth/login` | None | Returns JWT access token |

### The Rule
Every agent must talk to LLMs through a **single abstraction layer** — one module that all agents call. No agent imports the Groq SDK, Anthropic SDK, or any LLM provider SDK directly. All provider-specific code lives in one place.

### The Pattern

```python
# /llm/client.py — the ONLY place that knows which provider is in use

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
        # Returns an OpenAI-compatible client pointed at localhost
        from openai import OpenAI
        return OpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")

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
        **kwargs
    )
    return response.choices[0].message.content
```

```python
# /agents/strategy.py — typical agent. Knows nothing about the provider.

from llm.client import chat_completion
from prompts.loader import load_prompt

def run(content_brief, product_knowledge, knowledge_context=None) -> StrategyBrief:
    prompt = load_prompt("strategy_v1")
    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": build_user_message(content_brief, product_knowledge)}
    ]
    raw = chat_completion(messages)
    return parse_and_validate(raw)
```

### Environment Variables for LLM Switching

```env
# Which provider to use for text agents
LLM_PROVIDER=groq                          # groq | openai | anthropic | ollama

# Which provider to use for vision (UI Analyzer only)
LLM_VISION_PROVIDER=anthropic              # anthropic | ollama | openai

# Model names per provider (override defaults)
LLM_TEXT_MODEL=llama-3.3-70b-versatile     # production default — Groq 70B
LLM_VISION_MODEL=claude-haiku-4-5          # Anthropic model string (vision only)
OLLAMA_BASE_URL=http://localhost:11434/v1  # MUST include /v1 — OpenAI SDK appends /chat/completions directly
OLLAMA_TEXT_MODEL=llama3.2:latest          # Ollama text model (separate from LLM_TEXT_MODEL)
OLLAMA_VISION_MODEL=llava:latest           # Ollama vision model (separate from LLM_VISION_MODEL)

# API keys (only the active provider's key is required)
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
```

Switching from Groq to OpenAI in production: change `LLM_PROVIDER=openai` and set `LLM_TEXT_MODEL=gpt-4o-mini`. Zero agent code changes. This is the requirement.

**Important — Groq TPD rate limit:** The free tier has a 100,000 token/day limit per model. `llama-3.3-70b-versatile` exhausts this in ~3-4 full pipeline runs against data-heavy sites. When exhausted, `llama-4-scout-17b-16e-instruct` has a separate quota but produces worse output (design_category accuracy 4/10 vs 10/10 on Indian SaaS). Plan quota usage accordingly. Dev Tier removes this limit.

### Vision is Separate
The vision model (UI Analyzer) is configured independently via `LLM_VISION_PROVIDER`. This is intentional — vision and text requirements are different. Haiku is the current choice for vision. If a faster/cheaper vision model emerges, it can be swapped without touching text agents.

### LangFuse Traces Every Switch
When LLM_PROVIDER changes, LangFuse traces will immediately show the latency and output quality difference per agent. This makes provider comparisons data-driven, not guesswork.

---

## Team Structure

| Person | Role | Primary ownership |
|---|---|---|
| Person A (Tech Lead) | Agent code, pipeline, backend, deployment | `/agents/`, `/pipeline.py`, `/api.py`, `/knowledge/`, `/auth/` |
| Person B | Prompts + dataset collection | `/prompts/*.yaml`, `/datasets/*.jsonl` |
| Person C | Frontend / UI | `/frontend/` (Next.js) |
| Person D | Research, schemas, validation | `/docs/`, `/test_data/`, schema specs |

---

## Folder Structure

```
/agents/                → all 9 agent Python files + image_gen.py (Phase 2)
  _utils.py             → parse_json_object(), utc_now_iso() — used by all agents
  input_processor.py    → Step 1: Playwright scrape, CSS tokens, logo extraction
  ui_analyzer.py        → Step 2: vision LLM → BrandProfile
  product_analysis.py   → Step 3: text LLM → ProductKnowledge
  planner.py            → Step 4: ContentBrief
  strategy.py           → Step 5: StrategyBrief
  copywriting.py        → Step 6: raw copy string
  visual_gen.py         → Step 7: image_prompt + suggested_format
  formatter.py          → Step 8: FormattedContent (platform rules applied)
  evaluator.py          → Step 9: EvaluatorOutput + retry loop
  image_gen.py          → Phase 2: Bannerbear carousel slide generation
  research_agent.py     → Step 3.5: Tavily search → stat extraction → ResearchProofPoint list

/llm/                   → LLM abstraction layer
  client.py             → chat_completion() + vision_completion() — ONLY place that knows provider

/schemas/               → all Pydantic schema files
  input_package.py      → InputPackage (scraped text, css_tokens, logo, screenshot)
  brand_profile.py      → BrandProfile (design_category, colors, writing_instruction)
  brand_identity.py     → BrandIdentity (assembled from InputPackage+BrandProfile+ProductKnowledge; _to_hex() color normalisation)
  product_knowledge.py  → ProductKnowledge (features, proof_points, pain_points, research_proof_points)
  research_proof_point.py → ResearchProofPoint (text, source_name, source_url, credibility_tier, proof_type)
  content_brief.py      → ContentBrief (platform, content_type, narrative_arc)
  strategy_brief.py     → StrategyBrief (pain_point, claim, proof_point, hook_direction)
  formatted_content.py  → FormattedContent (platform-specific content + metadata)
  evaluator_output.py   → EvaluatorOutput (scores, passes, overall_score, revision_hint)
  knowledge_context.py  → KnowledgeContext (prior run context from Qdrant)

/prompts/               → YAML system prompt files (owned by Person B)
  loader.py             → load_prompt() — reads YAML, falls back to inline defaults
  ui_analyzer_v1.yaml   → v2.2 (6 few-shot examples, Indian SaaS anchors)
  copywriting_v1.yaml   → v1.3 (FABRICATION PROHIBITION block, hook_direction binding)
  evaluator_v1.yaml     → v1.2 (score-2 anchors, specificity test)
  planner_v1.yaml
  strategy_v1.yaml      → updated: RESEARCH PROOF POINTS section (research stat → AGITATE, brand stat → SOLVE)
  product_analysis_v1.yaml
  formatter_v1.yaml

/config/                → runtime configuration
  settings.py           → Pydantic Settings (all env vars, including BANNERBEAR_*)
  platform_rules.json   → per-platform formatting constraints (formatter reads at runtime)

/datasets/              → JSONL training/few-shot files (stub — not yet populated)
/frontend/              → Next.js frontend (stub — not yet built); Phase 7 interactive editor (Fabric/Konva hydration + export)
/knowledge/             → Qdrant + Supabase layer (stub — KNOWLEDGE_LAYER_ENABLED=false)
/auth/                  → Clerk integration (stub — not yet built)
/scripts/               → utility scripts
/utils/                 → shared utilities
/docs/                  → validation log, schema specs, setup notes
/test_data/             → Indian SaaS run outputs, validation summaries, expected outputs
/tests/                 → pytest test files (288 tests, all fast/no network)

api.py                  → FastAPI entry point (endpoints: /health, /analyze, /generate, /runs/{id}/approve)
pipeline.py             → chains agents; run_linkedin(), run_stream(), run(), _run_entry()
GENATE_CONTEXT.md       → this file
CLAUDE.md               → Claude Code session guidance (MOCK_MODE, bug log, behaviour notes)
```

---
## Architecture
### The 9-Agent Pipeline

1. input_processor  → InputPackage      (Playwright scrape + CSS tokens + screenshot)
2. ui_analyzer      → BrandProfile      (text LLM — design category & writing_instruction derived purely from CSS/text heuristics)
3. product_analysis → ProductKnowledge  (text LLM — features, proof points, pain points)
4. planner          → ContentBrief      (selects content type, arc, pillar, platform rules)
5. strategy         → StrategyBrief     (selects pain point, claim, proof point, hook direction)
6. copywriting      → str               (raw copy — strict Python regex validates CTA intent)
7. visual_gen       → dict              (image_prompt, suggested_format)
8. formatter        → FormattedContent  (LLM for LinkedIn; programmatic Python formatting for Twitter/IG/Blog)
9. evaluator        → EvaluatorOutput   (scores 1-5 × 4 dims; passes if all ≥ 3; max 2 retries)

---

## Backlog reference

| Item | Location |
|------|----------|
| LinkedIn `long_form` word-count enforcement (LLM variance vs brief) | [`agents/TODO.md`](agents/TODO.md) **Task 14** |
| Closed-shadow / CDP logo piercing | [`agents/TODO.md`](agents/TODO.md) **Task 9** |
| Interactive editor — canvas hydration from pipeline JSON | [`agents/TODO.md`](agents/TODO.md) **Task 18** |
| Interactive editor — real-time brand/copy overrides | [`agents/TODO.md`](agents/TODO.md) **Task 19** |
| Interactive editor — export / flatten (PNG, carousel PDF) | [`agents/TODO.md`](agents/TODO.md) **Task 20** |

*This document should be kept in the repo root and loaded as context in every Cursor Composer session. It supersedes all previous CONTEXT.md and FEATURECONTEXT.md files.*
