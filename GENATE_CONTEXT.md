# Genate — Full Project Context
**Version:** 2.2
**Last updated:** March 2026
**Status:** Core 9-agent pipeline complete and validated. Phase 2 (Bannerbear image generation) shipped. Phase 3 (video, Fal.ai, Pillow compositing) is next.

---

## What Genate Is

**Product name:** Genate  
**One-line position:** "The only AI content tool built specifically for SaaS companies — not coffee shops."

Genate is a multi-agent AI pipeline that takes a SaaS product URL (plus optional user uploads) and automatically generates platform-specific marketing content for LinkedIn, Twitter/X, Instagram, and Blog.

The core differentiator is not the content generation itself — it is the brand understanding that happens before any content is written. Genate extracts ground-truth brand data directly from CSS computed styles using Playwright browser automation. No competitor does this. Everyone else guesses from screenshots or asks users to manually input colors. Genate reads the actual design system.

---

## The Three Moats

### Moat 1 — CSS Token Extraction
When Playwright renders a page, a JavaScript function runs inside the browser and reads computed CSS custom properties from `:root`. For a site like Linear this produces exact values: `--color-brand-bg: #5e6ad2`, `--color-accent: #7170ff`, variable font weights like `510` and `590` (fractional weights that define a brand's visual personality), border radius per component type, spacing base units, button variants with exact colors. 60-100+ named tokens per site. No competitor does this.

### Moat 2 — Knowledge Layer Memory
Brand memory gets smarter with every approved run. Strategy summaries, copy examples, and proof points are indexed into Qdrant per organisation. Future runs retrieve semantically relevant context from previous runs — the output improves over time without any user action. The approval loop (`POST /runs/{id}/approve`) is the activation mechanism. Every user edit before approval is stored as a correction signal.

### Moat 3 — SaaS-Specific Pipeline
Agents understand pain-agitate-solve narrative arcs, proof point grounding, messaging angle selection, and platform-native formats. The pipeline is tuned for how SaaS products are positioned and marketed — not for coffee shops, DTC brands, or generic "teams."

### Moat 4 — Research Augmentation (Step 3.5)
Every content run is automatically enriched with real third-party industry statistics from Gartner, Forrester, McKinsey, HubSpot, and similar sources via Tavily search. These stats are distinct from the brand's own proof points — they validate the *problem* (AGITATE section) while the brand's own stat validates the *solution* (SOLVE section). The combination is uniquely credible: "Gartner found 67% of teams struggle with X → we reduced it by 206%." Fabrication prevention: any stat extracted by the LLM is validated against the source content before use. Gated by `RESEARCH_AUGMENTATION_ENABLED=false` — zero cost when not needed.

---

## Market Position

Pomelli (Google-backed, most technically sophisticated competitor) is geo-locked to US, Canada, Australia, and New Zealand during beta. The entire Indian SaaS ecosystem — Razorpay, Zerodha, Groww, Freshworks, Zepto, Chargebee, and 10,000+ funded companies — cannot access it. Holo targets ecommerce globally and does not speak SaaS language.

**The Indian SaaS market is Genate's uncontested home market.**

All copy, positioning, and product language should lead with the SaaS angle and reflect this market. Not generic "AI for teams."

---

## The 9-Agent Pipeline

Agents execute in the following order. Steps 2+3 run in parallel. Steps 6+7 run in parallel. All others are sequential.

### Step 1 — Input Processor
Playwright browser automation renders the target URL fully (including JavaScript), extracts rendered text, runs CSS token extraction via `getComputedStyle()`, takes a full-page screenshot, and packages everything into an `InputPackage`. User-uploaded images and documents take priority over scraped data.

**Priority order (highest to lowest trust):**
1. User-uploaded image → always used as primary visual
2. User-provided document → always used as primary text
3. Web scraped content → fills all gaps automatically

If scraping fails for any reason: log the error, return empty fields, continue with user-provided data only. Never crash the pipeline because a scrape failed.

### Step 2 — UI Analyzer *(parallel with Step 3)*
Vision model analyses the best available image plus CSS tokens. Classifies the brand into one of five design categories: `developer-tool`, `minimal-saas`, `bold-enterprise`, `consumer-friendly`, `data-dense`. Returns a `BrandProfile` Pydantic model including exact colors, typography, tone classification, and a `writing_instruction` string that is injected directly into the Copywriting agent's system prompt.

**Model:** Claude Haiku (vision) — chosen for instruction-following quality and consistent JSON output over llava.

### Step 3 — Product Analysis *(parallel with Step 2)*
Analyses scraped + user-provided text. Extracts features, benefits, proof points (stats, customer names, G2 badges, integration counts, uptime claims), pain points, and messaging angles. Returns a `ProductKnowledge` Pydantic model.

**Model:** Groq `llama-3.3-70b-versatile`

### Step 3.5 — Research Agent *(parallel-capable, after Step 3)*
Searches for real third-party industry statistics using Tavily web search. Builds 3 targeted queries from `ProductKnowledge` (category stats, pain point validation, buyer behaviour). For each result, uses an LLM to extract a concrete stat from the source content, then validates the stat by checking key words appear in the original content (6-word presence check — fabrication prevention). Classifies source credibility as tier_1 (Gartner/Forrester/McKinsey/academic journals), tier_2 (HubSpot/Salesforce/G2/Statista), or tier_3 (vendor blogs/news). Returns a sorted list of `ResearchProofPoint` objects attached to `ProductKnowledge.research_proof_points`. Strategy agent receives these and uses the best one in the AGITATE section.

**Gating:** `RESEARCH_AUGMENTATION_ENABLED=false` by default. Returns `[]` when disabled or when `TAVILY_API_KEY` is not set.

**Model:** Groq `llama-3.3-70b-versatile` (stat extraction only — 1 LLM call per Tavily result)

### Step K — Knowledge Layer Query *(optional, when `KNOWLEDGE_LAYER_ENABLED=true`)*
Before the Planner runs, the pipeline queries Qdrant for semantically relevant context from previous approved runs for this organisation. Returns `KnowledgeContext` containing prior strategy summaries, approved copy examples, and proof points that worked.

### Step 4 — Planner
Selects content type, narrative arc, content pillar, and platform-specific strategy. Uses SaaS engagement benchmarks (from research datasets) to inform defaults. Returns a `ContentBrief`.

**Narrative arc options:** `pain-agitate-solve-cta` · `before-after-bridge-cta` · `stat-hook-problem-solution-cta`
**Platform defaults:** LinkedIn → long-form or carousel arc · Twitter → always thread arc · Instagram → carousel-first arc

**Model:** Groq `llama-3.3-70b-versatile`

### Step 5 — Strategy
Decides what to say before any copy is written. Selects: the specific pain point to lead with (not generic — exact daily friction), the primary claim, the appeal type (rational/emotional/mixed), which proof point from `ProductKnowledge.proof_points` to use, and CTA direction. Returns a `StrategyBrief`.

The `proof_point` field **must** reference an actual proof point from `ProductKnowledge` — not fabricated. This is enforced in the prompt and validated by the Evaluator.

**Model:** Groq `llama-3.3-70b-versatile`

### Step 6 — Copywriting Agent *(parallel with Step 7)*
Writes raw copy executing the `StrategyBrief`. The `BrandProfile.tone.writing_instruction` is injected directly into the system prompt — mechanically tying brand voice to generation. Focus is purely on substance (what to say). Structure is handled separately by the Formatter.

**Model:** Groq `llama-3.3-70b-versatile`

### Step 7 — Visual Gen Agent *(parallel with Step 6)*
Generates an image generation prompt using exact brand parameters (hex colors, font names, design category signals, OG image as style reference). Also generates a `suggested_format` output (`static` | `carousel` | `video` | `ugc`). Video script generation is Phase 3.

**Model:** Groq `llama-3.3-70b-versatile`

### Step 7.5 — Image Gen *(Phase 2, after Formatter)*
`agents/image_gen.py` — runs after the Formatter and before the evaluator retry loop. Converts LinkedIn carousel copy into Bannerbear API calls. Returns branded slide image URLs. Gated by `IMAGE_GENERATION_ENABLED=true`. See Phase 2 section below.

### Step 8 — Formatter
Applies platform-specific structural rules from `config/platform_rules.json`. Rules are enforced mechanically — not suggested.

| Platform | Key rules |
|---|---|
| LinkedIn | Hook standalone in first 180 chars · 3-5 hashtags at end only · short paragraphs with whitespace |
| Twitter/X | 4-8 tweet thread · ≤280 chars each · Tweet 1 works standalone · 1-2 hashtags in final tweet only |
| Instagram | First 125 chars must be a complete emotional statement · 20-30 hashtags after 5 line breaks |
| Blog | H1/H2 structure · 1200-2500 words · keyword in first 100 words · `[INTERNAL_LINK: topic]` placeholders · meta_title 50-60 chars · meta_description 140-160 chars |

If this is a retry: receives `revision_hint` from Evaluator as a targeted rewrite instruction.

**Model:** Groq `llama-3.3-70b-versatile` (LinkedIn only — other platforms use programmatic formatting)

### Step 9 — Evaluator (with retry loop)
Scores the formatted output on four dimensions (1-5 each):
- `clarity` — is it easy to understand?
- `engagement` — does the hook grab attention?
- `tone_match` — does it match the `writing_instruction`?
- `accuracy` — are all claims grounded in real product evidence from the `StrategyBrief`?

`passes = true` if **all four** ≥ 3. If `passes = false` AND retries < 2: generates a targeted `revision_hint` (specific instruction, not "improve the copy") and sends back to the Formatter. `MAX_EVAL_RETRIES = 2`.

Python post-processes LLM scores before accepting them: fabricated stat cap (accuracy → 1), generic opener cap (engagement capped at 3), `passes` and `overall_score` always computed by Pydantic — never trusted from LLM output.

**Model:** Groq `llama-3.3-70b-versatile`

### Step K (post) — Knowledge Layer Persist
After a successful run, `persist_run()` stores `BrandProfile`, `ProductKnowledge`, `StrategyBrief`, and the final approved copy into Supabase (Postgres) and indexes semantic embeddings into Qdrant per `org_id`.

---

## The Image Pipeline

### Phase 2 — Bannerbear Programmatic Templates ✅ SHIPPED

`agents/image_gen.py` is live. Bannerbear receives brand colors, copy text, and logo URL and returns image URLs via its template API. This is the "guaranteed accuracy" layer — colors are exact hex from `BrandIdentity`, never approximate.

**What's done:**
- LinkedIn carousel copy split into slides (hook = slide 1 headline, paragraph pairs for slides 2-N, max 8 slides)
- Adaptive text color: `_is_dark()` detects background luminance; headline/body flip between `#ffffff`/`#cccccc` and `#111111`/`#444444`
- Accent bar contrast: `_pick_accent_color()` uses WCAG contrast ratio to pick primary → secondary → accent → fallback, preventing invisible accent bars when primary_color == background_color
- Logo compositing: injected via `logo_url` when `logo_confidence` is "high" or "medium"
- All color fields guaranteed `#rrggbb` hex via `BrandIdentity._to_hex()` before reaching Bannerbear
- `IMAGE_GENERATION_ENABLED=false` default — zero cost when not needed

**Bannerbear template layer names** (template must expose these):

| Layer | Type | Content |
|---|---|---|
| `background_color` | color | `BrandIdentity.background_color` |
| `accent_bar` | color | `_pick_accent_color(identity)` result |
| `slide_label` | text | `"01 / 05"` format |
| `headline` | text | max 120 chars |
| `body_text` | text | max 280 chars |
| `logo` | image | `logo_url` (when confidence high/medium) |

### Phase 3 — AI Generation + Compositing (deferred)

**Stage 1 — FLUX Dev + IP-Adapter (Fal.ai)** *(not yet built)*
The scraped OG image as IP-Adapter style reference. Transfers brand visual language to generated images. LoRA fine-tuning as premium upgrade (20-50 visual assets, ~$1-3/brand on Fal.ai).

**Stage 2 — Logo Compositing (Pillow)** *(not yet built)*
Pillow compositing of real extracted logo onto Bannerbear output. Blocked by: apple-touch-icon black background baked in — needs background removal before compositing on light-background brands.

**Brand consistency hierarchy (strongest to weakest) — target state:**
Programmatic template (guaranteed) → logo compositing (always real) → FLUX + IP-Adapter (stylistically consistent) → FLUX text-only (least consistent)

For text-in-image variants: **Ideogram** (significantly better than FLUX/DALL-E for readable text).

---

## The Video Pipeline (Phase 3)

Three-stage pipeline:

**Stage 1 — ElevenLabs (voiceover)**  
Converts the generated video script to audio. Brands can clone their founder's voice from a 1-minute sample via ElevenLabs instant voice clone, or choose from the professional library. Cost ~$0.002 per script.

**Stage 2 — Remotion (programmatic video)**  
React-based programmatic video generation. Exact brand colors, font, and scraped product screenshots are composed into an MP4. Brand consistency is guaranteed because the composition is code — not diffusion model generation. This is the primary video output.

**Stage 3 — HeyGen (AI avatar, premium tier only)**  
For brands that want talking-head UGC-style video. Brand uploads a 2-minute video of their founder or team member. HeyGen creates a custom avatar. Premium feature — higher cost, high-margin upsell.

---

## The Approval Loop

The mechanism that activates the Knowledge Layer:

1. User reviews generated content in the frontend inline copy editor
2. User edits copy directly (any edit is captured)
3. User clicks Approve → `POST /runs/{id}/approve` is called
4. `persist_run()` triggers: stores `BrandProfile`, `ProductKnowledge`, `StrategyBrief`, and the **edited** copy (not the original) into Supabase and Qdrant
5. All future runs for this `org_id` retrieve this context during the Planner and Strategy steps

Every correction teaches the system. The gap between first draft and approved version shrinks over time.

---

## Tech Stack

### The Full Stack

| Layer | Technology | Notes |
|---|---|---|
| LLM inference (production) | **Groq** (`llama-3.3-70b-versatile`) | ~300-500 tok/sec · ~$0.06/M input tokens · OpenAI-compatible API · 100K TPD free tier |
| Vision inference | **Claude Haiku** (Anthropic API) | UI Analyzer only · better JSON instruction-following than llava |
| LLM inference (local dev) | **Ollama** (llama3.2 + llava) | Unchanged for development loop |
| Web scraping | **Playwright** + **Browserless** | Playwright for CSS token extraction · Browserless as hosted browser service (scales independently) |
| Scraping proxies | **Bright Data** (residential) | Only for sites that block datacenter IPs — not all requests |
| Image generation | **Fal.ai** (FLUX Dev + IP-Adapter) | OG image as style reference · brand LoRA as premium upgrade |
| Text-in-image | **Ideogram** | For graphics requiring readable text |
| Programmatic templates | **Bannerbear / Placid** | Guarantees exact color + font accuracy |
| Image compositing | **Pillow** | Logo compositing onto generated images |
| AI voiceover | **ElevenLabs** | Instant voice clone from 1-min sample · ~$0.002/script |
| Programmatic video | **Remotion** | React-based MP4 render with exact brand assets |
| AI avatar video | **HeyGen** | Premium tier only · custom avatar from 2-min video |
| Vector database | **Qdrant** | Self-hosted on Railway · org-scoped filtering · replaces ChromaDB |
| Relational database | **Supabase** | Postgres + row-level security + real-time · replaces raw Postgres |
| Authentication | **Clerk** | Replaces custom JWT · org management + API key support built-in |
| Backend framework | **FastAPI** + **Celery** + **Redis** | Async · SSE streaming · background job queue |
| Frontend framework | **Next.js** + **Shadcn/ui** + **TanStack Query** | SSR for Brand DNA report · Shadcn components · TanStack for SSE state |
| Frontend animation | **Framer Motion** | Pipeline progress step-by-step animation |
| Backend deployment | **Railway** | Backend + Qdrant + Redis as separate services |
| Frontend deployment | **Vercel** | Next.js |
| LLM observability | **LangFuse** | Traces every agent call · logs prompts + responses · latency per agent |
| Error monitoring | **Sentry** | Stack traces when agents fail |
| Uptime monitoring | **Betterstack** | Pings health endpoint every minute |
| Transactional email | **Resend** | Auth flows + run notifications |
| Payments | **Lemonsqueezy** | Indian GST compliance · UPI support · Merchant of Record · replaces Stripe for initial launch |

---

## Explicit Stack Switches From Previous Version

These are deliberate changes from the original codebase. Each switch has a reason.

| What changed | From | To | Why |
|---|---|---|---|
| Production LLM inference | Ollama (local) | Groq API | Ollama requires a persistent GPU instance. Groq runs llama3.2 at 300-500 tok/sec via API at ~$0.06/M tokens. Same model, 10-20x faster, serverless-compatible. |
| Vision model | llava (via Ollama) | Claude Haiku (Anthropic API) | llava requires a separate GPU-heavy model pull. Haiku has significantly better JSON instruction-following — the UI Analyzer needs to return valid structured output every time. |
| Vector database | ChromaDB | Qdrant (self-hosted Railway) | ChromaDB works for development. Qdrant has better performance at scale, better `org_id` metadata filtering (needed for every query), and a cleaner production deployment story. |
| Relational database | Raw Postgres | Supabase | Supabase gives Postgres + row-level security for multi-tenant data isolation + real-time subscriptions + built-in auth option. Removes ops work at the worst possible time (early build). |
| Authentication | Custom JWT (bcrypt + tokens.py) | Clerk | Custom auth is the highest-risk area to get wrong. Clerk handles sessions, token rotation, org management, and API key management. Frees the team to focus on the pipeline. |
| Frontend | Plain React + Tailwind | Next.js + Shadcn/ui + TanStack Query | Next.js is required for SSR on the Brand DNA report page (social crawler rich previews won't work with a plain SPA). TanStack Query manages SSE streaming state. |
| Image generation | Visual Gen outputs text prompt only | Fal.ai FLUX Dev + IP-Adapter + Bannerbear | The text prompt was an intermediate step. The full pipeline now calls Fal.ai with the OG image as IP-Adapter style reference, then applies exact CSS token values programmatically via Bannerbear. |
| Payments | (not yet in original) | Lemonsqueezy | Indian GST compliance and UPI support out of the box. Acts as Merchant of Record. Stripe requires more compliance overhead for Indian businesses at launch. |
| Browser hosting | Chromium on Railway main instance | Browserless (hosted) | Running Chromium on the main Railway instance is memory-heavy and doesn't scale independently. Browserless is a hosted Playwright-compatible service called via API. |

---

## LLM API Flexibility — Critical Design Requirement

**This is a first-class architectural requirement, not an afterthought.**

The LLM landscape is moving fast. Groq is the right choice today (speed, cost, llama3.2 quality). That may change. A new model, a pricing shift, a rate limit issue, or a quality regression in a future Groq release should never require rewriting every agent.

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

## Dataset Strategy

Training data is built in parallel with agent development. Datasets must exist before agents are tested.

### Training Approach Per Agent

| Agent | Training type | Status |
|---|---|---|
| Evaluator | Fine-tune (LoRA on llama3.2) | Seed dataset needed: 110 examples |
| Copywriting | Few-shot → fine-tune later | Seed dataset needed: 60 examples. Knowledge Layer approval loop is the ongoing signal. |
| Product Analysis | Few-shot only | 30 edge case examples |
| UI Analyzer | Few-shot only | 50 examples (10 per design category) |
| Planner | Few-shot only | SaaS engagement benchmarks research doc |
| Strategy | Few-shot only | SaaS positioning patterns research doc |
| Image Pipeline | Per-brand LoRA (Fal.ai) | 20-50 visual assets per brand, collected during onboarding |
| Video Pipeline | Voice clone per brand | 1-minute voice sample per brand for ElevenLabs |

### Dataset Priority Order

1. **Evaluator** — human-rated quality pairs (40 LinkedIn, 30 Twitter, 20 Instagram, 20 Blog). At least 70 must be real human-written content. This determines whether the quality gate actually works.
2. **Copywriting** — (StrategyBrief + writing_instruction) → approved copy pairs. 15 examples per platform = 60 total. Covers all 3 narrative arcs.
3. **Product Analysis** — feature vs benefit edge cases. 30 examples.
4. **UI Analyzer** — design category examples. 10 per category × 5 categories = 50.
5. **Planner** — SaaS engagement benchmarks (research document with sources).
6. **Strategy** — SaaS positioning patterns by product category (research document).

### Dataset File Locations

```
/datasets/evaluator_seed.jsonl
/datasets/copywriting_seed.jsonl
/datasets/product_analysis_examples.jsonl
/datasets/ui_analyzer_examples.jsonl
```

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
/frontend/              → Next.js frontend (stub — not yet built)
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

## API Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Health check |
| `GET` | `/analyze` | None | Input Processor + UI Analyzer only. Returns `BrandProfile`. Brand Calibration endpoint. |
| `POST` | `/generate` | JWT (when Knowledge Layer enabled) | Full pipeline run. SSE stream (`text/event-stream`). Emits per-agent progress events. |
| `POST` | `/runs/{id}/approve` | JWT | Activates Knowledge Layer learning for the approved run. |
| `POST` | `/auth/register` | None | Create org + user (when Knowledge Layer enabled) |
| `POST` | `/auth/login` | None | Returns JWT access token |

SSE events emitted by `/generate`:
```json
{"step": 2, "agent": "ui_analyzer", "status": "complete", "elapsed": 45.2, "message": "Brand profile extracted"}
```

---

## Environment Variables — Complete List

```env
# Required
ENVIRONMENT=development
LLM_PROVIDER=groq                          # groq | openai | anthropic | ollama
LLM_VISION_PROVIDER=anthropic              # anthropic | ollama | openai
LLM_TEXT_MODEL=llama-3.3-70b-versatile     # production default (Groq 70B)
LLM_VISION_MODEL=claude-haiku-4-5          # vision model (UI Analyzer only)
MOCK_MODE=false                            # false = real LLM + real browser scrape

# LLM API keys (only active provider's key required)
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434/v1  # /v1 suffix required for OpenAI SDK compat

# Supabase
DATABASE_URL=postgresql+asyncpg://...
SUPABASE_URL=...
SUPABASE_ANON_KEY=...

# Qdrant
QDRANT_URL=...                             # Railway service URL
QDRANT_API_KEY=...
QDRANT_COLLECTION_PREFIX=genate

# Auth
CLERK_SECRET_KEY=...
CLERK_PUBLISHABLE_KEY=...

# Knowledge Layer
KNOWLEDGE_LAYER_ENABLED=false              # set true to enable Qdrant + Supabase memory

# Research Augmentation (Step 3.5)
RESEARCH_AUGMENTATION_ENABLED=false        # true enables Tavily third-party stat search
TAVILY_API_KEY=...                         # from app.tavily.com
TAVILY_MAX_RESULTS=3                       # results per query
TAVILY_MAX_PROOF_POINTS=5                  # max ResearchProofPoint objects returned

# Image generation (Phase 2 — Bannerbear is active)
IMAGE_GENERATION_ENABLED=false             # true enables Bannerbear slide generation
BANNERBEAR_API_KEY=bb_pr_...
BANNERBEAR_TEMPLATE_UID=YJBpekZX8X9wZ2XPnO  # template with layers: background_color, accent_bar, logo, slide_label, headline, body_text
BANNERBEAR_TIMEOUT_SECONDS=30
FAL_API_KEY=...                            # Phase 3 — not yet active
IDEOGRAM_API_KEY=...                       # Phase 3 — not yet active

# Video generation
ELEVENLABS_API_KEY=...
HEYGEN_API_KEY=...                         # premium tier only

# Scraping
BROWSERLESS_API_KEY=...
BRIGHTDATA_PROXY_URL=...                   # only for blocked sites
SCRAPE_TIMEOUT_SECONDS=15
SCRAPE_MAX_RETRIES=2

# Observability
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
SENTRY_DSN=...

# Payments
LEMONSQUEEZY_API_KEY=...

# Email
RESEND_API_KEY=...

# Redis / Celery
REDIS_URL=...
```

---

## Cost Per Full Run (Estimate)

Once all pipeline layers are live:

| Step | Cost |
|---|---|
| Input processing (Playwright) | $0.00 |
| UI Analyzer (Claude Haiku) | $0.002 |
| Product Analysis (Groq llama3.2) | $0.003 |
| Planner + Strategy (Groq × 2) | $0.004 |
| Copywriting + Evaluator (Groq × 3) | $0.006 |
| Image generation (Fal.ai FLUX) | $0.008 |
| ElevenLabs audio (~750 chars) | $0.002 |
| Remotion render (compute) | $0.010 |
| **Total per run** | **~$0.035** |

At $29/month for 50 runs: cost of goods = $1.75. Gross margin = ~94%.  
HeyGen avatar video as premium add-on at $5/video (cost: ~$0.08) is high-margin upsell.

---

## What Switches When and Why

### Switch now (before first paying customer)
- **Groq** instead of Ollama for production — pipeline must run in under 2 minutes for real users
- **Supabase** instead of raw Postgres — removes database ops at the moment when there's no time for ops
- **LangFuse** — observability from day one to know if output quality is acceptable
- **LLM abstraction layer** — must be built from the first agent, not retrofitted later

### Switch when first 50 users are active
- **Qdrant** tuning — when Knowledge Layer queries start showing latency
- **Clerk** — when auth edge cases start consuming engineering time
- **Celery + Redis** — when the synchronous pipeline starts blocking under concurrent requests

### Switch when revenue justifies it
- **Lemonsqueezy → Stripe** for usage-based billing (credits system)
- **Browserless** at scale for all scraping
- **Bright Data** for blocked enterprise sites

---

## Build Order

### ✅ Done
1. LLM abstraction layer (`llm/client.py`) — single provider interface, all agents use `chat_completion()`
2. Input Processor — Playwright scrape, CSS token extraction, logo extraction (priority 1-5 + 3.5 SVG), `InputPackage`
3. UI Analyzer — Claude Haiku vision + `BrandProfile` (prompts v2.2, 6 few-shot examples)
4. Product Analysis — Groq 70B + `ProductKnowledge`
5. Planner — `ContentBrief` with schema-validated platform/content_type combos
6. Strategy — `StrategyBrief` with proof_point_type normalization (BUG-005)
7. Copywriting — raw copy, FABRICATION PROHIBITION rule (prompts v1.3)
8. Visual Gen — image_prompt + suggested_format
9. Formatter — LinkedIn/Twitter/Instagram/Blog platform rules, hashtag rebuilding, tweet cleaning
10. Evaluator — 4-dimension scoring, Python-enforced caps, retry loop with revision_hint (prompts v1.2)
11. `pipeline.py` — full chain: `run_linkedin()`, `run()`, `run_stream()` (SSE), `run_pipeline()`
12. `api.py` — /health, /analyze, /generate, /runs/{id}/approve
13. `BrandIdentity` schema — color normalisation `_to_hex()` (BUG-006), WCAG helpers, all-or-nothing logo contract
14. Phase 2 image gen — `agents/image_gen.py`: Bannerbear slides, adaptive text color, `_pick_accent_color()` (BUG-007)
15. End-to-end validation — 10 Indian SaaS URLs, 3 platforms (LinkedIn/Twitter/Instagram), Groq 70B
16. Research Augmentation — Step 3.5: `agents/research_agent.py`, `schemas/research_proof_point.py`, Tavily integration, fabrication prevention, credibility tiers, strategy/copywriting prompt updates

### 🔜 Active next
- Frontend — Next.js · Brand Calibration UI · inline editor · approval flow · SSE progress display
- Knowledge Layer — wire Qdrant + Supabase (`KNOWLEDGE_LAYER_ENABLED=true`)

### Later (phased)
- Phase 3: Fal.ai FLUX + IP-Adapter image generation (Stage 1 of full image pipeline)
- Phase 3: Pillow logo compositing onto Bannerbear output (requires apple-touch-icon background removal)
- Phase 3: Video Pipeline — ElevenLabs voiceover + Remotion programmatic video + HeyGen avatar
- Phase 3: Competitor Intelligence agent
- Phase 3: Run history + replay
- Phase 4: One-click repurpose · Platform preview renderer
- Phase 5: Public Brand DNA report (viral acquisition) · Zapier integration · API access tier · Usage metering

---

*This document should be kept in the repo root and loaded as context in every Cursor Composer session. It supersedes all previous CONTEXT.md and FEATURECONTEXT.md files.*
