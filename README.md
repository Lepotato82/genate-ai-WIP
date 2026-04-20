# Genate

Learning project for building a multi-agent AI content pipeline for SaaS.

It takes a company URL, extracts brand signals from the page, and generates platform-specific content drafts.

---

## Important: this is a learning/WIP project

This repository is for **learning, experimentation, and demos**.

- It is **work in progress (WIP)**
- Some features are partially implemented or behind flags
- Real-mode quality is still being validated for some output types
- The codebase is shared for project visibility, not as a production-ready product

`Bannerbear` and `Pollinations` are used here **purely for demo purposes**.

---

## What this project currently does

- Runs a 9-step agent pipeline from input analysis to formatted output and evaluation
- Uses schema validation (`Pydantic`) between stages
- Supports parallel execution in key steps to speed up runs
- Exposes API endpoints to analyze and generate content
- Includes tests and saved run artifacts for debugging and iteration

---

## High-level pipeline

1. Input processing (scrape + brand signal extraction)
2. UI/brand analysis
3. Product analysis
4. Planning
5. Strategy
6. Copywriting
7. Visual prompt generation
8. Formatting
9. Evaluation (+ retries)

Optional layers:

- Research augmentation (Tavily)
- Knowledge memory (Qdrant + Supabase)
- Image generation/compositing paths

---

## Tech stack

- **Backend:** FastAPI, Celery, Redis
- **Frontend:** Next.js
- **LLM routing:** Groq/OpenAI/Anthropic/Ollama through `llm/client.py`
- **Scraping:** Playwright
- **Validation:** Pydantic + deterministic Python checks
- **Data/Memory:** Supabase, Qdrant

---

## Quick start

### Prerequisites

- Python 3.11+
- `uv`
- Node.js 18+

### Setup

```bash
uv venv .venv
uv sync --extra dev
.venv/Scripts/playwright install chromium
```

### Run backend

```bash
uvicorn api:app --reload
```

### Run frontend

```bash
cd frontend
npm install
npm run dev
```

### Run tests

```bash
pytest tests/ -v -m "not integration"
```

---

## API (main endpoints)

- `GET /health`
- `GET /analyze`
- `POST /generate`
- `POST /runs/{id}/approve`

---

## Repo layout

- `agents/` - pipeline agents
- `schemas/` - typed contracts
- `prompts/` - YAML prompts
- `llm/` - model provider abstraction
- `config/` - settings + flags
- `frontend/` - UI app
- `tests/` - test suite
- `test_data/` - run snapshots and fixtures

---

## Current focus / roadmap

From `agents/TODO.md`:

- Interactive editor (canvas hydration + manual overrides + export)
- Better deterministic length control for long-form output
- Real-mode validation for newer structured content types
- Edge-case logo extraction improvements

---

## Notes

- Start with `GENATE_CONTEXT.md` for full project context
- See `agents/TODO.md` for backlog and completed tasks

---

## License

No open-source license is provided in this snapshot.
