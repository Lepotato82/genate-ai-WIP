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