# Genate — Development Setup

## Prerequisites

### Python
- Python >= 3.11
- [uv](https://github.com/astral-sh/uv) for dependency management

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Node.js (required for dembrandt)
- Node.js >= 18
- npm >= 9

Download from https://nodejs.org/

### Python dependencies

```bash
uv venv .venv
uv sync --extra dev
```

### Playwright browser

```bash
.venv/Scripts/playwright install chromium    # Windows
# or
.venv/bin/playwright install chromium        # macOS / Linux
```

### dembrandt (CSS token extraction)

dembrandt is a Node.js CLI tool that extracts design tokens from live websites
using a full browser render. It is Genate's primary CSS extraction method —
providing structured color, typography, spacing, button, and framework data.

```bash
npm install -g dembrandt
```

Verify installation:

```bash
dembrandt --version
# → 0.6.1 (or later)
```

#### dembrandt flags used by Genate

| Flag | Purpose |
|---|---|
| `--json-only` | Output raw JSON to stdout (status messages also appear on stdout; JSON is found by seeking the first `{`) |
| `--slow` | 3× longer timeouts for slow-loading SPAs |
| `--no-sandbox` | Disable browser sandbox (required in Docker/CI environments) |

#### When dembrandt is unavailable

If `dembrandt` is not installed or fails, Genate **automatically falls back**
to Playwright `getComputedStyle()` injection. This produces a flat CSS
variable dict (`extraction_method = "computed_style"`) instead of the rich
`DesignTokens` object. The pipeline continues normally.

The `/health` endpoint surfaces dembrandt availability:

```json
{
  "dembrandt": true,
  "playwright": true
}
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the required keys:

```bash
cp .env.example .env
```

For local development with `MOCK_MODE=true` (default), no API keys are
required. The pipeline returns deterministic mock data.

---

## Running locally

```bash
# Activate virtual environment
source .venv/bin/activate         # macOS / Linux
.venv\Scripts\activate            # Windows

# Start API server
uvicorn api:app --reload

# Run tests
pytest tests/ -v
```
