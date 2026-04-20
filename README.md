# Genate

Genate is a multi-agent AI pipeline for SaaS marketing content generation.  
Given a product URL, it extracts brand signals from a live website, builds a strategy brief, and produces platform-specific copy and visual directions for LinkedIn, Twitter/X, Instagram, and blog formats.

## Project status

This repository is **work in progress (WIP)** and under active development.

- Core 9-agent pipeline is implemented and validated
- Structured output types (`poll`, `single_tweet`, `story`) are wired and mock-tested
- Interactive Canva-style editing layer is planned and partially scaffolded
- Some quality checks are still pending in real-mode LLM runs (see roadmap)

## Demo integrations notice

`Bannerbear` and `Pollinations` are included here **purely for demo/prototyping purposes**.  
This public snapshot does **not** present them as final long-term production choices.

## Resume-oriented highlights

- Built and orchestrated a production-style **9-agent pipeline** with typed contracts between every stage
- Enforced output quality with **deterministic validation gates** (Pydantic + Python checks), reducing blind trust in LLM responses
- Added **parallel execution paths** (2+3 and 6+7) to improve end-to-end generation flow
- Implemented **provider-agnostic LLM routing** (`llm/client.py`) so model vendors can be swapped without agent rewrites
- Designed around **feature flags** for safe rollout of research, memory, and image layers
- Maintained a broad test suite (mock-first workflow; structured content paths mock-tested)

## Why this architecture is different

Most AI content tools guess brand identity from screenshots or ask users to manually enter colors.  
Genate reads rendered CSS design tokens from the live page and uses those as source-of-truth brand inputs before copy generation.

Key technical differentiators:

- CSS token extraction from rendered pages (`Playwright` + browser runtime)
- Deterministic validation layer (`Pydantic` + Python validators) to constrain LLM output
- LLM provider abstraction in one place (`llm/client.py`) for easy provider switching
- Local CLIP-based logo extraction and shadow-DOM aware traversal
- Optional research enrichment pipeline with source-grounded proof points

## High-level architecture

`pipeline.py` orchestrates a 9-agent workflow.  
Steps 2 and 3 run in parallel. Steps 6 and 7 run in parallel. The output of each stage is schema-validated before handoff.

1. **Input Processor**: scrape page, extract CSS signals, capture screenshot/logo
2. **UI Analyzer**: infer design category and writing instruction from brand signals
3. **Product Analysis**: extract product benefits, pain points, and proof points
4. **Planner**: choose platform strategy and content structure
5. **Strategy**: select claim, hook direction, and proof emphasis
6. **Copywriter**: generate copy with deterministic CTA enforcement
7. **Visual Gen**: generate image prompt and visual direction
8. **Formatter**: platform-specific formatting (LLM + deterministic formatters)
9. **Evaluator**: score output quality and trigger bounded retries

Optional stages:

- **Research Agent (Step 3.5)** for third-party stat enrichment
- **Knowledge Layer** query/persist with Qdrant and Supabase
- **Image generation path** for rendered visuals and slide assets

## API surface

- `GET /health` - service health check
- `GET /analyze` - run input + brand analysis preview
- `POST /generate` - run full content pipeline (SSE stream)
- `POST /runs/{id}/approve` - approve run and persist learning artifacts

## Reliability model

- **Strict schema contracts**: each step returns typed objects under `schemas/`
- **Deterministic safeguards**: CTA and quality checks happen in Python, not just prompt instructions
- **Bounded retries**: evaluator-guided retry loop avoids unbounded generation churn
- **Mock-first development**: `MOCK_MODE=true` supports local development without external API cost

## Tech stack

- **Backend**: FastAPI, Celery, Redis
- **Models**: Groq/OpenAI/Anthropic/Ollama via unified client abstraction
- **Scraping**: Playwright (+ Browserless/Bright Data hooks)
- **Data/Memory**: Supabase, Qdrant
- **Observability**: LangFuse, Sentry
- **Frontend**: Next.js (with planned canvas editor layer)
- **Validation**: Pydantic schemas + deterministic Python checks

## Repository structure

- `agents/` - pipeline agent implementations
- `schemas/` - strict contracts for each pipeline artifact
- `prompts/` - YAML prompt assets
- `llm/` - provider abstraction layer
- `config/` - runtime settings and feature flags
- `frontend/` - Next.js application
- `tests/` - unit and integration tests
- `test_data/` - example artifacts and validation snapshots

## Quick start

### Prerequisites

- Python `>=3.11`
- `uv` for dependency management
- Node.js `>=18` and npm
- Playwright Chromium runtime

### Backend setup

```bash
uv venv .venv
uv sync --extra dev
.venv/Scripts/playwright install chromium
uvicorn api:app --reload
```

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

### Run tests

```bash
pytest tests/ -v -m "not integration"
```

## Configuration

1. Copy `.env.example` to `.env`
2. Keep `MOCK_MODE=true` for local development without external keys
3. Enable optional features gradually (`RESEARCH_AUGMENTATION_ENABLED`, `KNOWLEDGE_LAYER_ENABLED`, `IMAGE_GENERATION_ENABLED`, `HERO_IMAGE_ENABLED`)

Design rule: no agent should directly import provider SDKs. All model calls route through `llm/client.py`.

## Current roadmap focus

From `agents/TODO.md` and project context:

- **Phase 7**: interactive Canva-style editor
- canvas hydration from pipeline JSON
- real-time brand/text overrides
- export and flatten to PNG/PDF
- **Quality backlog**: deterministic LinkedIn long-form length enforcement, real-mode validation for new structured content types, and edge-case logo extraction for closed shadow roots

## Known boundaries in this public snapshot

- This is an engineering-focused WIP snapshot, not a polished production release
- Some integrations and flows are scaffolded but intentionally feature-flagged
- Real-mode quality parity is strongest for LinkedIn text/carousel paths
- Supporting artifacts in `test_data/` are for validation and iteration context

## Notes for reviewers

- Start with `GENATE_CONTEXT.md` for full architecture context
- Use `agents/TODO.md` to see completed fixes and active backlog phases

## License

No license file is included yet in this snapshot. Add a project license before broad public distribution.
