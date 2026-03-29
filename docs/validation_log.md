# Genate — Validation Log

**Format:** Date | URL | Agent | What was wrong  
**Owner:** Person D  
**Rule:** A failing validation with a specific description is more useful than a passing one with no notes. Not "copy was bad" — "the proof_point field in StrategyBrief was not used in the final copy — the agent fabricated a statistic instead."

---

## Sprint 1 — March 2026 | searchable.com | Groq (llama-3.3-70b-versatile)

Runs: LinkedIn, Twitter, Instagram against https://searchable.com

---

| Date | URL | Agent | What was wrong |
|---|---|---|---|
| 2026-03 | searchable.com | input_processor | PASS — InputPackage complete. CSS token extraction ran. Screenshot taken. Scraped text available. |
| 2026-03 | searchable.com | ui_analyzer | FAIL — design_category is inconsistent across runs for this site. Groq runs have returned developer-tool, minimal-saas, and data-dense for the same URL. The field is always present and always a valid enum value so the schema is not violated, but the value is not stable. The correct classification for searchable.com is minimal-saas. Fix: add searchable.com as a labelled few-shot example in the UI Analyzer prompt anchored to minimal-saas. |
| 2026-03 | searchable.com | product_analysis | FAIL (Ollama only, not reproduced on Groq) — description field returned boilerplate text ("We help teams...") instead of a real product description extracted from the page. The field is present and is a string so the schema is not violated, but the value is not usable. Groq run produces a correct real description. Root cause: Ollama product_analysis prompt does not force extraction over generation. |
| 2026-03 | searchable.com | product_analysis | PASS — proof_points[0].text = "206% share of voice improvements" on Groq run. Extracted verbatim from the product page. No fabricated stats. Features and benefits are real extractions, not boilerplate. |
| 2026-03 | searchable.com | planner | PASS — ContentBrief fields all present. narrative_arc = "pain-agitate-solve-cta" on all three platform runs. content_type = "thread" on Twitter run (Contract 3 holds). |
| 2026-03 | searchable.com | strategy | PASS — StrategyBrief fields all present. proof_point = "206% share of voice improvements" — matches ProductKnowledge.proof_points[0].text verbatim (Contract 1 holds). narrative_arc = "pain-agitate-solve-cta" — matches ContentBrief.narrative_arc (Contract 2 holds). cta_intent = "start_trial" — valid enum value. appeal_type = "rational" — valid enum value. lead_pain_point is specific ("Difficulty tracking brand mentions and rankings across multiple AI engines daily") — not a generic statement. |
| 2026-03 | searchable.com | copywriting | FAIL (Ollama LinkedIn run) — final copy contained "Searchable has helped over 200 companies" — this stat does not appear in ProductKnowledge.proof_points. The only verified stat is "206% share of voice improvements". The Copywriting agent ignored the proof_point field from StrategyBrief and invented a customer count figure. This is a Copywriting prompt failure, not a Strategy agent failure — the StrategyBrief proof_point field was correct. Not reproduced on Groq. |
| 2026-03 | searchable.com | copywriting | FAIL (Ollama Instagram run, retry_count=2) — model introduced "63%" across both retry attempts. "63%" does not appear in ProductKnowledge.proof_points or anywhere in the scraped page. The prohibition rule in the Evaluator revision_hint ("do not fabricate new figures on retry") was not followed. Terminal failure at MAX_EVAL_RETRIES=2. Not reproduced on Groq. |
| 2026-03 | searchable.com | copywriting | PASS (Groq, all three platforms) — proof_point from StrategyBrief used correctly in final copy. No fabricated stats. |
| 2026-03 | searchable.com | formatter | PASS — LinkedIn: hook is standalone in first 180 chars, 3-5 hashtags at end only, short paragraphs. Twitter: 4-8 tweets each ≤280 chars, tweet 1 works standalone, 1-2 hashtags in final tweet only. Instagram: first 125 chars is a complete emotional statement, 20-30 hashtags after 5 line breaks. All platform rules from platform_rules.json applied correctly. |
| 2026-03 | searchable.com | evaluator | PASS (Groq, all three platforms) — all four scores ≥ 3 on first attempt. passes=True. retry_count=0. passes is a Pydantic computed field — not an LLM output — so Contract 4 cannot be violated by hallucination. Twitter accuracy=5: proof point used verbatim. |
| 2026-03 | searchable.com | evaluator | PASS (Ollama failure detection) — Evaluator correctly returned passes=False and accuracy=1 on both the LinkedIn fabricated-stat run and the Instagram max-retries run. revision_hint named the fabricated claim and specified the correct replacement in both cases. The Evaluator catches fabrication correctly — the problem is the Copywriting agent not following the hint on Ollama. |
| 2026-03 | searchable.com | pipeline (Contract 1) | PASS (Groq) — StrategyBrief.proof_point = "206% share of voice improvements" matches ProductKnowledge.proof_points[0].text verbatim across all three platform runs. |
| 2026-03 | searchable.com | pipeline (Contract 2) | PASS — StrategyBrief.narrative_arc = ContentBrief.narrative_arc = "pain-agitate-solve-cta" across all three platform runs. |
| 2026-03 | searchable.com | pipeline (Contract 3) | PASS — ContentBrief.content_type = "thread" on Twitter run. |
| 2026-03 | searchable.com | pipeline (Contract 4) | PASS — EvaluatorOutput.passes computed by Pydantic validator (all four scores ≥ 3). Not an LLM output. Cannot be violated by hallucination unless the Pydantic model is changed. |
| 2026-03 | searchable.com | pipeline (Contract 5) | PASS — FormattedContent has exactly one non-null platform field per run: linkedin_post on LinkedIn run, twitter_thread on Twitter run, instagram_caption on Instagram run. All other fields null. |

---

## Session 4 — March 2026 | 10 Indian SaaS URLs | Llama 4 Scout via Groq

**Note on model:** Groq daily quota (100K tokens/day free tier) was exhausted from prior sessions. Runs executed with `meta-llama/llama-4-scout-17b-16e-instruct` (17B MoE, Groq). Some results, particularly `design_category`, should be re-validated against `llama-3.3-70b-versatile` when quota resets — the v2.2 prompts were calibrated for 70B.

Platform: LinkedIn only. Results saved to `test_data/indian_<name>_run.json`.

| Date | URL | Agent | What was wrong |
|---|---|---|---|
| 2026-03 | razorpay.com | strategy | BUG-005 (FIXED this session) — `proof_point_type` field returned null by Llama 4 Scout. Pydantic StrategyBrief requires a non-None literal. Pipeline crashed. Fix: added normalization in strategy.py — infers type from matched proof_point entry in ProductKnowledge, defaults to "stat". |
| 2026-03 | razorpay.com | product_analysis | FAIL — 0 real proof points despite 2345 words scraped. Razorpay homepage is marketing-heavy ("boldest disruptors") with no explicit stats visible in scraped text. Known limitation: Product Analysis doesn't scroll to pricing/testimonials pages. |
| 2026-03 | razorpay.com | ui_analyzer | FAIL — design_category=minimal-saas but expected bold-enterprise. Razorpay is a v2.2 few-shot example anchored to bold-enterprise. Likely a Llama 4 Scout model capability issue (not following few-shot as well as 70B). Re-validate with 70B. |
| 2026-03 | razorpay.com | input_processor | PASS — logo_confidence=medium (og:image, 2.3MB marketing graphic). Expected. Razorpay blocks direct logo extraction. |
| 2026-03 | chargebee.com | ui_analyzer | FAIL — design_category=bold-enterprise but expected minimal-saas. Chargebee is a v2.2 few-shot example anchored to minimal-saas. Same suspected model mismatch as Razorpay. |
| 2026-03 | chargebee.com | copywriting | FAIL (initial, fixed by retry) — fabricated "5%" and "125%" not present in proof_points. Pre-check detected, retry system fixed. Final accuracy=5 (clean copy on retry). |
| 2026-03 | chargebee.com | full pipeline | PASS — overall=4.25, passes=True, logo=high, 2 real proof points. |
| 2026-03 | freshworks.com | input_processor | NOTE — only 568 words scraped. Site uses heavy JS rendering, most content likely deferred. Only 1 proof point extracted: "74% first contact resolution (FCR)". |
| 2026-03 | freshworks.com | full pipeline | PASS — overall=4.0, passes=True, design_category=bold-enterprise (correct), logo=high. |
| 2026-03 | postman.com | input_processor | NOTE — only 307 words scraped (thinnest of the batch). Nav-heavy homepage, content not rendered. Proof point is qualitative not quantitative: "The world's APIs are built and shipped on Postman." |
| 2026-03 | postman.com | ui_analyzer | FAIL — design_category=bold-enterprise but expected developer-tool. Orange dominant brand color may pull toward bold-enterprise. |
| 2026-03 | postman.com | copywriting | FAIL (initial, fixed by retry) — fabricated "70%" not in proof_points. Pre-check caught it. Final accuracy=5. |
| 2026-03 | postman.com | full pipeline | PASS — overall=4.0, passes=True, logo=high. |
| 2026-03 | hasura.io | input_processor | NOTE — scraped contact form page rather than marketing homepage (422 words, "AI Catalyst Team" page). Likely scrape landing issue. |
| 2026-03 | hasura.io | ui_analyzer | FAIL — design_category=minimal-saas but expected developer-tool. primary_color=#000000 fallback (CSS token extraction probably didn't find a brand color). |
| 2026-03 | hasura.io | formatter | NOTE — "LLM returned non-JSON; falling back to mechanical parse." Formatter recovered correctly. No crash. |
| 2026-03 | hasura.io | full pipeline | PASS — overall=3.5, passes=True, logo=high. |
| 2026-03 | browserstack.com | ui_analyzer | FAIL — design_category=minimal-saas but expected developer-tool. primary_color=#000000 fallback. |
| 2026-03 | browserstack.com | input_processor | FAIL — logo_confidence=None, logo_url=None. Logo extraction failed entirely. BrowserStack may serve logos as inline SVG or behind auth walls. 4 real proof points extracted including "GoodRx cuts testing time by 90%" — strong extraction. |
| 2026-03 | browserstack.com | full pipeline | PASS — overall=4.0, passes=True, logo=None (NOT Phase 2 ready — no logo or OG image). |
| 2026-03 | zoho.com | ui_analyzer | PASS — design_category=bold-enterprise (correct). Unique font: Zoho_Puvi_Regular (brand's own typeface). |
| 2026-03 | zoho.com | product_analysis | NOTE — product_name="Zoho One" (expected "Zoho"). Homepage redirects to Zoho One product suite. Only 1 weak proof point: "With our complete business under control..." — a customer quote, not a stat. |
| 2026-03 | zoho.com | full pipeline | PASS — overall=3.75, passes=True, logo=high. |
| 2026-03 | clevertap.com | product_analysis | PASS — best proof point extraction of the batch: 5 real proof points including "60% Increase in CTRs using best time", "45% Reduction in support tickets", Gartner Magic Quadrant Leader 2026. |
| 2026-03 | clevertap.com | full pipeline | PASS — overall=4.0, passes=True, design_category=bold-enterprise (correct), logo=high. |
| 2026-03 | darwinbox.com | ui_analyzer | FAIL — design_category=minimal-saas but expected bold-enterprise. primary_color=#007aff (Apple system blue — suspicious, likely a CSS variable default not the brand color). |
| 2026-03 | darwinbox.com | input_processor | NOTE — logo_confidence=medium (Framer-based site, og:image returned instead of logo). Confirmed known Framer behavior. |
| 2026-03 | darwinbox.com | strategy | NOTE — proof_point_type mismatch warning: Strategy selected "[g2_badge] Recognized by..." but ProductKnowledge stored it without the prefix. Cross-validation warning logged, no crash. |
| 2026-03 | darwinbox.com | full pipeline | PASS — overall=3.75, passes=True. |
| 2026-03 | moengage.com | input_processor | FAIL — logo_confidence=None, logo_url=None. Logo extraction failed. No OG image found either. Not Phase 2 ready. |
| 2026-03 | moengage.com | product_analysis | PASS — 3 real proof points: "Trusted by 1350+ Consumer Brands Worldwide", Gartner Customers' Choice 2026, Gartner Visionary 2026. |
| 2026-03 | moengage.com | full pipeline | PASS — overall=4.0, passes=True, design_category=bold-enterprise (correct). |
| 2026-03 | (all 10) | brand_identity | DEFERRED — primary_color stored in rgb() format on 6/10 sites (Razorpay, Chargebee, Freshworks, Postman, Zoho, MoEngage). Phase 2 Bannerbear template injection expects hex. Need rgb-to-hex normalization in build_brand_identity() before Phase 2 starts. |
| 2026-03 | (all 10) | ui_analyzer | DEFERRED — design_category accuracy 4/10 with Llama 4 Scout. Re-run with llama-3.3-70b-versatile to separate model vs prompt issues. Note: both v2.2 few-shot anchors (Razorpay, Chargebee) were misclassified — suggests 4 Scout doesn't follow few-shot as reliably as 70B. |

---

## Pending — Next Session

| Date | URL | Agent | What was wrong |
|---|---|---|---|
| TBD | linear.app | ui_analyzer | Not yet run. Validate design_category=developer-tool and fractional font weight extraction (expected: weight ~510–590 range from variable font CSS tokens). A round-number result (400, 600) would indicate CSS token extraction failure on a variable font site. |
| TBD | linear.app | product_analysis | Not yet run. Validate proof_points include "Used by Vercel, Raycast, and Mercury teams" — this is the most well-known proof point for this site and a good extraction baseline check. |
| TBD | any | formatter | Blog platform rules completely unvalidated. No Blog run has been produced. Need to check: H1/H2 structure present, word count 1200–2500, keyword in first 100 words, [INTERNAL_LINK: topic] placeholders present, meta_title 50–60 chars, meta_description 140–160 chars. |
| TBD | (all 10 Indian SaaS) | full pipeline | Re-run all 10 with llama-3.3-70b-versatile when Groq quota resets. Design category results from this session are Llama 4 Scout only. |
| TBD | browserstack.com moengage.com | input_processor | Logo extraction failed (None) for both sites. Investigate whether inline SVG or JS-rendered logos are the cause. Fix before Phase 2. |
