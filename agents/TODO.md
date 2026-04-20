# Genate Pipeline — Technical Debt & Refactoring TODOs

**Context for AI Agent:** Read `GENATE_CONTEXT.md` and `CLAUDE.md` before executing these tasks. Work through these items sequentially. Mark as `[x]` when complete and verify the fix against the project's Pydantic schemas.

## Phase 1: Critical Bug Fixes (API Cost & Crash Prevention)

- [x] **Task 1: Fix the Copywriter CTA Infinite Loop Trap**
  - **Target File:** `prompts/copywriting_v1.yaml`
  - **Context:** `agents/copywriter.py` strictly validates that the generated copy includes specific magic words from the `CTA_SIGNALS` dictionary (e.g., "trial", "demo", "book") in the last 20% of the text. However, the YAML prompt never tells the LLM what these allowed words are, causing endless validation failures and API retries.
  - **Action:** Inject the explicit list of allowed CTA words into the `copywriting_v1.yaml` system prompt so the LLM knows the rules.
  - **Status:** ✅ DONE — CTA ENFORCEMENT block added in v1.4 (lines 124-133)

- [x] **Task 2: Resolve Evaluator Doppelgänger Conflict**
  - **Target Files:** `prompts/evaluator_pipeline_v1.yaml`, `prompts/evaluator_v1.yaml`, `schemas/evaluator_output.py`
  - **Context:** There are two evaluator YAML files. `evaluator_pipeline_v1.yaml` expects a single `scores_rationale` string, which fatally conflicts with the `evaluator_output.py` Pydantic schema that strictly requires individual `_reason` fields (e.g., `clarity_reason`).
  - **Action:** Delete `prompts/evaluator_pipeline_v1.yaml` entirely. Ensure `agents/evaluator.py` is safely loading `evaluator_v1.yaml`.
  - **Status:** ✅ DONE — `evaluator_pipeline_v1.yaml` deleted, `evaluator.py` loads `evaluator_v1.yaml` correctly

## Phase 2: Pipeline Optimization & Cleanup

- [x] **Task 3: Trim Formatter Dead Weight**
  - **Target File:** `prompts/formatter_v1.yaml`
  - **Context:** The formatter prompt currently wastes input tokens by giving the LLM instructions for Twitter, Instagram, and Blog formatting. However, `agents/formatter.py` reveals that those platforms are handled entirely programmatically via Python string manipulation. 
  - **Action:** Strip all non-LinkedIn formatting instructions from `formatter_v1.yaml` to save tokens.
  - **Status:** ✅ DONE — `formatter_v1.yaml` deleted entirely (was unused legacy; all system prompts are inline in `formatter.py`)

## Phase 3: Architecture Upgrades (Composite AI)

- [x] **Task 4: Implement Local ViT (CLIP) for Logo Extraction**
  - **Target File:** `agents/input_processor.py`
  - **Context:** The current Priority 3.5 SVG extraction heuristic is brittle and fails on complex SVGs (extracting UI icons instead of brand logos). 
  - **Dependencies to Add:** `transformers`, `torch`, `pillow` (via `uv add`).
  - **Action:** 1. Update Playwright to gather an array of screenshots of all candidate elements in the `<header>` and `<nav>` using `el.screenshot(type="png", omit_background=True)`.
    2. Implement a local Hugging Face CLIP model (`openai/clip-vit-base-patch32`) to semantically score those candidate images against the prompt `"{product_name} official company logo"`.
    3. Return the bytes of the highest-scoring candidate.
    4. Remove the old DOM/CSS path-counting heuristics.
  - **Status:** ✅ DONE — `agents/logo_clip.py` + `_collect_header_nav_screenshots` / `_infer_product_name`; gated by `LOGO_CLIP_ENABLED` (see `config/settings.py`).

## Phase 4: Logo quality & priority tuning

- [x] **Task 5: Refine logo extraction priority order (CLIP vs og:image)**

  - **Target:** `agents/input_processor.py` (`_extract_logo`), `CLAUDE.md`, `GENATE_CONTEXT.md`
  - **Context:** `og:image` can be a large marketing hero (e.g. lemonhealth.ai `snippet3.png`) while the real mark lives in the nav. CLIP already ran *before* `og:image` in code; Lemon Health typically failed because CLIP collected zero qualifying screenshots or did not return a valid PNG — not because `og` preempted CLIP.
  - **Action:** (1) Move the CLIP block to **immediately after** P1–P2 (large icon) and **before** header `img` with "logo" attrs, so semantics run before that heuristic and before `og:image`. (2) Optional **`LOGO_OG_IMAGE_MAX_BYTES`** / **`LOGO_OG_IMAGE_MAX_EDGE_PX`** to reject hero-sized `og:image` assets when >0. (3) **`scripts/debug_logo.py -v`** enables DEBUG on `agents.input_processor` (e.g. CLIP screenshot count).
  - **Status:** ✅ DONE — March 2026

- [x] **Task 7: Implement Shadow DOM Deep Traversal**
  - **Target:** `agents/input_processor.py`
  - **Context:** Standard `querySelectorAll` cannot see inside Web Components. Lemon Health and other modern SaaS sites often wrap logos in shadow roots.
  - **Action:** Implemented `_LOGO_DEEP_QUERY_JS` to recursively traverse `shadowRoot` (open mode).
  - **Status:** ✅ DONE — 35 tests passed; shadow piercing active.

## Phase 5: Production Readiness (Next Steps)

- [x] **Task 8: Background Removal & Post-Processing Optimization**
  - **Context:** Some extracted logos (like Apple Touch icons) have hardcoded backgrounds that clash with dynamic templates.
  - **Action:** Refine `maybe_remove_dark_background()` tolerance for non-black plates (e.g., dark grays/navy).
  - **Status:** ✅ DONE — `_CORNER_LUMA_SKIP_ABOVE` 102, per-channel + Euclidean match in `logo_postprocess.py`; tests in `test_logo_postprocess.py`.

### Phase 5 — Prompt wiring and routing fixes (execution)

- [x] **Task 10: LinkedIn long-form length signal (schema-safe)**
  - **Target Files:** `agents/copywriter.py`, `prompts/planner_v1.yaml`
  - **Context:** `ContentBrief.word_count_target` is **blog-only** (`int` 1200–2500); Pydantic forbids non-null values for LinkedIn. Copy length for social platforms is driven by `content_depth` plus `_depth_instruction()` in the Copywriter user message — not by `word_count_target`.
  - **Action:** ✅ DONE — Inject `linkedin_word_range: 600-900` into the Copywriter user message when `platform == linkedin` and `content_depth == long_form`. Clarified in `planner_v1.yaml` that non-blog `word_count_target` stays null and length follows `content_depth` set in Python.

- [x] **Task 11: Tavily query specificity and URL dedup**
  - **Target File:** `agents/research_agent.py`
  - **Context:** Generic category queries and tracking query strings on URLs reduced result quality and deduplication.
  - **Action:** ✅ DONE — `_normalize_url` uses `urlunparse`, strips query/fragment, lowercases scheme and host. `_build_queries` generic fallback and category overrides include B2B / 2026 / market research style terms. Tests in `tests/test_research_agent.py`.

- [x] **Task 11.1: Re-weight Research Queries (Pain-First)**
  - **Target File:** `agents/research_agent.py`
  - **Context:** `_build_queries` prioritized `product_category` and B2B tails, so miscategorized B2C products (e.g. wellness apps as `vertical-saas`) pulled irrelevant B2B SaaS stats.
  - **Action:** ✅ DONE — Two of three queries are pain/tagline/description-led with neutral research tails; third is category anchor. Category YAML overrides supply Q3 only. `_is_likely_b2c()` softens Q3 wording when copy signals consumer/B2C. Tests in `tests/test_research_agent.py`.

- [x] **Task 12: Strategy hook_direction binding**
  - **Target File:** `prompts/strategy_v1.yaml`
  - **Context:** Thematic hook instructions leak into copy as generic openers.
  - **Action:** ✅ DONE — Added explicit BINDING CONTRAST BAD/GOOD one-liner pair after the HOOK DIRECTION RULE.

- [x] **Task 13: Fix Research Stat Truncation (Pydantic Field)**
  - **Target Files:** `schemas/research_proof_point.py`, `agents/research_agent.py`
  - **Context:** The LLM was extracting naked numbers (e.g., "54%") instead of full sentences, tripping the 10-char validator on `ResearchProofPoint.text`.
  - **Action:** ✅ DONE — `text` now has `Field(..., description=...)` on the schema; `_EXTRACTION_SYSTEM` and the extraction user message require a full sentence/clause (min 10 chars, ≥3 words), not an isolated figure.

## Phase 6: Image Generation Layer (Asset Creation)

**Context:** With the shift to an interactive frontend editor (Phase 7), we are moving away from Bannerbear for hard-compositing. The vision models will strictly generate the *background/hero illustration*, while the extracted logo and text will be layered on top via the frontend canvas to preserve editability and brand safety.

- [x] **Task 15: Create `prompts/visual_gen_v1.yaml`**
  - **Context:** `agents/visual_gen.py` currently uses a hardcoded system prompt. We need a dedicated YAML file to instruct the LLM on how to write prompts for text-to-image models (e.g., DALL-E 3, Midjourney). 
  - **Action:** Write strict instructions mapping the `design_category` (e.g., `minimal-saas`) to specific illustration styles (e.g., "flat vector, corporate style"). **CRITICAL:** Enforce that the LLM NEVER attempts to generate the brand logo or text in the prompt. It must only design the "scene".
  - **Status:** ✅ DONE — `prompts/visual_gen_v1.yaml` + `visual_gen.py` loader; pipeline runs `visual_gen` in parallel with copywriter.

- [x] **Task 15.1: Enforce Negative Space in `visual_gen_v1.yaml`**
  - **Context:** Hero images were too busy for Canva-style text/logo overlays.
  - **Action:** ✅ DONE — v1.1 adds mandatory asymmetric layout (~60% clean negative space on the left, interest biased right); `image_prompt` must reflect this. Tests in `tests/test_visual_gen_prompt.py`.

- [x] **Task 16: Integrate Image API in `image_gen.py`**
  - **Context:** Execute the text-to-image prompt generated by Task 15.
  - **Action:** Add an API call (to chosen provider like fal.ai, Replicate, or OpenAI) in `image_gen.py` to generate the background image based on the AI's visual prompt.
  - **Status:** ✅ DONE — `agents/hero_image_providers.py` (Pollinations + Fal), `HERO_IMAGE_*` settings; `image_gen.run(..., visual=)`.

- [x] **Task 17: Wire Asset to JSON Payload (Deprecate Bannerbear)**
  - **Context:** The Canva-style frontend needs the raw image asset to use as a bottom layer, rather than a flattened Bannerbear final image.
  - **Action:** Update `image_gen.py` to strip out the Bannerbear layout mapping logic. Instead, simply append the generated background image URL to the final JSON payload (e.g., adding `background_hero_url` to the output) so the frontend can retrieve it.
  - **Status:** ✅ PARTIAL — `images` dict includes `background_hero_url`, `hero_generation_enabled`, `hero_error`; pipeline returns `visual`. Bannerbear slide path retained until Phase 7 drops flattened slides.

## Phase 7: Interactive Editor (The "Canva" Layer)

**Owner:** Person C (Frontend / UI) — [`GENATE_CONTEXT.md`](../GENATE_CONTEXT.md) Phase 7 section.
**Context:** The backend output is treated as a "Project File" that hydrates a state-driven editor, allowing the user to tweak the AI's generation before publishing.

- [ ] **Task 18: Build Canvas Hydration Logic (Next.js + Fabric.js/Konva.js)**
  - **Context:** The pipeline's JSON output needs to map to independent, draggable layers on a canvas.
  - **Action:** Create a Next.js component that loads the JSON payload. 
    1. Set the generated image (Task 17) as the static bottom background layer.
    2. Map `BrandIdentity` (colors/fonts) to the theme.
    3. Render the `logo_bytes` and `FormattedContent` as editable, draggable top layers.

- [ ] **Task 19: Implement Real-time State Overrides**
  - **Context:** Users must be able to change colors, swap logos, or tweak text manually if the AI's "first guess" isn't 100% perfect.
  - **Action:** Build a sidebar UI in the Brand Calibration view that binds to the canvas state. Modifying a hex code, font, or text block in the sidebar should trigger an immediate canvas re-render.

- [ ] **Task 20: Export & Flattening Engine**
  - **Context:** Once the user is happy with their edits, the canvas must be converted back into a social-ready asset.
  - **Action:** Implement a client-side export function (e.g., `canvas.toDataURL()`) to flatten the state into high-resolution PNGs or a multi-page PDF for LinkedIn carousels.

## Phase 8: Edge Case Research (Future Backlog)

- [ ] **Task 21: Advanced Shadow Piercing (CDP / Accessibility Tree)**
  - **Context:** `lemonhealth.ai` showed that some logos are still invisible to standard JS-based deep queries (potential closed shadow roots or canvas-based rendering).
  - **Action:** Investigate using Playwright's `CDPSession` to access the full Accessibility Tree or taking a full-page screenshot and using a local YOLO/object-detection model to "find" the logo visually.
  - **Status:** BACKLOG (v2.0)

- [ ] **Task 22: Enforce LinkedIn `long_form` word count (deterministic)**
  - **Target Files:** `agents/copywriter.py`, optionally `agents/evaluator.py` / `prompts/evaluator_v1.yaml`
  - **Context (March 2026 real runs):** Both `lemonhealth.ai` and `searchable.com` recorded `content_depth == "long_form"`, but full post lengths diverged sharply. The Evaluator scores clarity/accuracy/engagement/tone_match only — **no minimum word count**.
  - **Action:** Add Python-enforced gates for `platform == linkedin` and `content_depth == long_form` (e.g. count words on raw or formatted body; if under threshold, retry Copywriter once with explicit expansion instruction, or cap `engagement` / fail a dedicated length check in Evaluator).
  - **Status:** BACKLOG

- [ ] **Task 23: Verify and fix new structured content types in real-mode LLM runs**
  - **Target Files:** `prompts/copywriting_v1.yaml`, `agents/copywriter.py`, `agents/formatter.py`, `agents/evaluator.py`
  - **Context (April 2026):** LinkedIn Poll, Twitter Poll, Twitter Single Tweet, Instagram Story, and LinkedIn Question Post content types were wired into the pipeline (formatter dispatch + `force_content_type` API param). All 454 tests pass in mock mode, but **real-mode LLM output quality has not been validated** — only LinkedIn text posts and carousels have been tested against real SaaS URLs. Known concerns: (a) real LLM may not reliably output `INTRO/QUESTION/OPTION_1-4` labels for polls; (b) formatter real-mode early-return branches for structured types are untested end-to-end; (c) Evaluator short-form types (story = 2 fields, single tweet = 1 tweet) may receive unfair low engagement/clarity scores calibrated for long-form.
  - **Action:**
    1. Run `pipeline.py` in real mode (`MOCK_MODE=false`) with `force_content_type` set for each new type against 2–3 real Indian SaaS URLs (Razorpay, Freshworks, Chargebee).
    2. If copywriter does not emit structured labels, tighten the FORMAT BLOCKS in `prompts/copywriting_v1.yaml` and add a retry hint in `copywriter.py` (similar to CTA retry logic).
    3. Confirm formatter real-mode dispatch fires the right early-return branch for each structured type.
    4. Review Evaluator scores — if short-form types consistently fail `passes` due to length-related low engagement, add a `content_type`-aware scoring note to `prompts/evaluator_v1.yaml`.
    5. Update the relevant real-mode test data snapshots in `test_data/` once verified.
  - **Status:** BACKLOG

## Phase 9: Brand Post Quality — Lemon Health Parity

**Context (April 2026):** Analysis of `sample_posts/` (Lemon Health carousel samples) identified three layers of gap vs. current Genate output: (1) no real photography — Pollinations AI art doesn't match editorial lifestyle photos; (2) copy structure mismatch — research stat is placed mid-narrative instead of on the hook slide; (3) engagement CTAs ("Comment below") blocked by the CTA validator which only accepts conversion intents.

All six tasks are achievable with free tools. Tasks 24–26 close the visual gap. Tasks 27–29 close the copy/structure gap. Task 30 closes the research quality gap for B2C health brands.

- [x] **Task 24: Pexels Stock Photo Provider**
  - **Target Files:** `agents/hero_image_providers.py`, `config/settings.py`
  - **Context:** Current `HERO_IMAGE_PROVIDER` options are Pollinations and Fal — both generative. For `consumer-friendly` brands (health, wellness, lifestyle), real stock photography looks more authentic than AI art. Pexels API is free (200 req/hour, 20K/month), all images commercially licensed.
  - **Action:**
    1. Add `HERO_IMAGE_PROVIDER=pexels` option to `config/settings.py` with `PEXELS_API_KEY` env var.
    2. Implement `PexelsProvider` in `agents/hero_image_providers.py`: build query from `pain_point` + product keywords; fetch `orientation=square`, `size=large`; return `src.large2x` URL.
    3. In `pipeline.py`, when `identity.design_category == "consumer-friendly"` and `HERO_IMAGE_ENABLED=true`, default to Pexels provider.
    4. Add `PEXELS_API_KEY` to `.env.example`.
  - **Status:** BACKLOG

- [x] **Task 25: Duotone Photo Treatment in Compositor**
  - **Target File:** `agents/compositor.py`
  - **Context:** Lemon's photo slides apply a brand-color duotone — desaturate the image, tint with primary brand color. Makes any stock photo feel on-brand instantly. Currently `photo_overlay` applies a dark gradient only; no brand-color tinting.
  - **Action:**
    1. Add `_duotone(img: Image.Image, dark_color: tuple, light_color: tuple) -> Image.Image` helper using `ImageOps.colorize(img.convert("L"), black=dark_color, white=light_color)`.
    2. In `_layout_photo_overlay`, apply `_duotone(hero, dark=_darken(primary_rgb, 0.5), light=primary_rgb)` before compositing text, when `hero_bytes` present.
    3. Add `COMPOSITOR_DUOTONE_ENABLED` flag (default `true`).
  - **Status:** BACKLOG

- [x] **Task 26: PlayfairDisplay-Italic Font + `stat_hero` Layout**
  - **Target Files:** `assets/fonts/`, `agents/compositor.py`, `frontend/src/lib/types.ts`
  - **Context:** Lemon uses italic + regular weight contrast for headlines ("*Viceral Fat:* The Invisible danger"). We have `PlayfairDisplay-Bold.ttf` but no italic. `stat_hero` is a new layout for research-stat hook slides: flat brand-color bg (no gradient), massive italic first line, regular weight second line.
  - **Action:**
    1. Download `PlayfairDisplay-Italic.ttf` from Google Fonts GitHub (`ofl/playfairdisplay/static/`) into `assets/fonts/`.
    2. Add `"display_italic": "PlayfairDisplay-Italic.ttf"` to `_FONT_FILES`.
    3. Implement `_layout_stat_hero`: flat `primary_color` fill, italic display font for headline (max_size=140), `display_bold` for second line, body below separator.
    4. Add `"stat_hero"` to `_LAYOUT_FNS`, `LayoutArchetype` in `frontend/src/lib/types.ts`, and `DESIGN_CATEGORY_LAYOUTS` for `consumer-friendly` + `data-dense`.
  - **Status:** BACKLOG

- [x] **Task 27: Carousel Per-Slide Word Budget**
  - **Target Files:** `prompts/copywriting_v1.yaml`, `agents/image_gen.py` (`_split_into_slides`)
  - **Context:** Copywriter writes one continuous narrative block; formatter splits arbitrarily. No per-slide word budget. Lemon's hook slides ≤ 20 words; body slides ≤ 40 words. Long paragraphs look bad at 1080×1080.
  - **Action:**
    1. Add `CAROUSEL SLIDE WORD BUDGET` block to `copywriting_v1.yaml`: hook slide ≤ 20 words, body slides ≤ 40 words, CTA slide ≤ 15 words. Include compliant/non-compliant examples.
    2. Update `_split_into_slides` in `agents/image_gen.py` to prefer double-newline then sentence-ending splits over character-count splits.
  - **Status:** BACKLOG

- [x] **Task 28: Engagement CTA Type for B2C Brands**
  - **Target Files:** `agents/copywriter.py`, `prompts/copywriting_v1.yaml`, `prompts/evaluator_v1.yaml`
  - **Context:** Lemon's CTAs are engagement triggers: "Comment below", "What's holding you back?", "Tag someone who needs this." These fail our CTA validator which only accepts conversion intents. Consumer-friendly brands are penalised for natural engagement CTAs.
  - **Action:**
    1. Add `engagement_cta` as a valid `cta_intent` value in `schemas/content_brief.py`.
    2. Add `CTA_SIGNALS["engagement_cta"]` in `copywriter.py`: `["comment", "share", "tag", "tell us", "what do you think", "reply"]`.
    3. Update CTA ENFORCEMENT block in `copywriting_v1.yaml` to document `engagement_cta` signals.
    4. Add note to `evaluator_v1.yaml`: engagement CTAs score at parity with conversion CTAs for `consumer-friendly` brands.
  - **Status:** BACKLOG

- [x] **Task 29: Stat-on-Hook Routing for Carousels**
  - **Target Files:** `prompts/strategy_v1.yaml`, `agents/strategy.py`
  - **Context:** Strategy currently places research stats in AGITATE (mid-narrative). For carousels, the stat should be the hook slide — it's the first thing visible. Lemon's hook slide is one stat + one question. No warm-up.
  - **Action:**
    1. In `prompts/strategy_v1.yaml`, add a `CAROUSEL HOOK RULE`: when `content_type == carousel` and a `research_proof_point` is available, `hook_direction` must instruct the copywriter to open with the stat as the headline.
    2. In `agents/strategy.py`, inject a carousel hook hint into the strategy user message when `brief.content_type == "carousel"` and `research_proof_points` is non-empty.
  - **Status:** BACKLOG

- [x] **Task 30: Medical Research Query Tier for B2C Health Brands**
  - **Target File:** `agents/research_agent.py`
  - **Context:** For B2C health/wellness brands, the research agent pulls market adoption stats ("72% of consumers use health apps") not clinical research ("visceral fat linked to insulin resistance in lean adults"). Clinical stats give posts the authority Lemon's content has.
  - **Action:**
    1. Add a `health-wellness-clinical` tier to `CATEGORY_QUERY_OVERRIDES` with tails targeting CDC, WHO, JAMA, Lancet, PubMed: `"[pain_point] clinical study CDC WHO JAMA 2024 2025"`.
    2. When `design_category == "consumer-friendly"` and product keywords include health/wellness signals, use the clinical tier for at least one of the three Tavily queries.
    3. Validate extracted stats pass the `ResearchProofPoint` text validator (≥ 10 chars, ≥ 3 words).
  - **Status:** BACKLOG

---

## Phase 10: Carousel Visual Quality — Photo Textures + Role Mapping

Closes the visual gap vs Lemon Health. No new dependencies, no API cost.

- [x] **Task 31: Photo Texture on Hero Images**
  - Added `_apply_photo_texture()` — halftone dot overlay on hero photos for editorial/risograph feel
  - Integrated into `photo_overlay`, `editorial_photo` layouts
  - Gated by `COMPOSITOR_PHOTO_TEXTURE_ENABLED` (default `true`)

- [x] **Task 32: Cutout Hero Layout**
  - New `_layout_cutout_hero()` — removes photo background via rembg, composites subject onto solid brand primary
  - Matches Lemon Health lemon1.png style (person cutout on flat blue)
  - Gated by `COMPOSITOR_CUTOUT_ENABLED` (default `true`), graceful fallback without rembg
  - Added to `consumer-friendly` family + `_PHOTO_LAYOUTS`

- [x] **Task 33: Photo-Bottom Hook Layout**
  - New `_layout_photo_bottom_text()` — photo fills top 60%, solid brand panel at bottom with italic+bold headline
  - Matches lemonresearch1hook.png style. Duotone + halftone applied to photo.
  - Added to `consumer-friendly` and `bold-enterprise` families + `_PHOTO_LAYOUTS`

- [x] **Task 34: Slide-Role Layout Mapping**
  - Replaced blind `slide_index % len(family)` rotation with role-based selection
  - `_assign_slide_role()` → hook/body/cta based on slide position
  - `_select_role_layout()` → picks from `ROLE_LAYOUT_MAP` per design category and role
  - Hook slides get photo-heavy layouts, body slides get text-only, CTA slides get bold/simple

- [x] **Task 35: Logo Position + Visual Polish**
  - Logo placement: top-right for photo/hook layouts (`cutout_hero`, `photo_bottom_text`, `photo_overlay`, `stat_hero`)
  - Added decorative accent circle to `stat_hero` bottom-left corner

### Known Issues from Real-Mode Testing (2026-04-12)

Issues observed during Lemon Health pipeline runs. Not blocking — pipeline passes at 4.25/5.0 — but worth fixing for quality.

- [ ] **Body paragraph word budget not enforced**: Copywriter LLM writes 40–77 word paragraphs despite CAROUSEL SLIDE WORD BUDGET prompt (≤40 words). The prompt instruction exists but the LLM doesn't comply. May need a Python-level paragraph splitter in `_split_into_slides()` or a post-copy validator that rejects over-budget paragraphs.
- [ ] **CTA retry fires every run for `engage` intent**: The copywriter never produces engagement CTA words ("comment", "share", "tag") on the first attempt — always needs the explicit injection retry. The `engage` signals need stronger presence in the system prompt or few-shot examples.
- [ ] **Research agent token cost**: 8–10 Groq LLM calls for stat extraction from 3 Tavily queries. Each query result gets a separate extraction call. On the free tier (100K TPD), research alone uses ~30K tokens. Consider batching extraction (multiple results → one LLM call) or caching Tavily results.
- [ ] **Groq SDK internal retry conflicts with our retry**: Groq SDK has its own 429 retry (`Retrying request ... in N seconds`) that runs *before* our `_RATE_LIMIT_RETRIES` loop in `llm/client.py`. Total retry time = Groq SDK retries + our retries. Consider disabling Groq SDK auto-retry via `max_retries=0` on client init.