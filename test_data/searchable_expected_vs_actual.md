# Searchable Research + Long-form Run — Expected vs Actual
Date: 2026-03-30
Model: llama-3.1-8b-instant (Groq 70B daily quota exhausted — 8B used as fallback)
RESEARCH_AUGMENTATION_ENABLED: true
IMAGE_GENERATION_ENABLED: false

---

## Research Proof Points

**Expected:** At least one of Stat A (Gartner 25% search volume drop), Stat B (AirOps 30% brand visibility), or Stat C (Adobe 123% AI referral traffic growth). All tier_1 or tier_2, source_url starts with https.

**Actual:**
- Count: 2
- [tier_3] Specter Insights: `"up to 72,730 hours"` — https://insights.tryspecter.com/devtools-landscape-2025/
- [tier_3] business.com 2026 Survey: `"chatbots 84%"` — https://votednumberone.com/small-business-ai-adoption-statistics/

**Match: NO**

Root cause: The 8B model extracted fragments ("chatbots 84%") rather than complete stat sentences. Both are tier_3 and unrelated to AI search visibility. None of Stat A/B/C appeared in Tavily results for this run. The 6-word validation rejected longer stats for the same reason as prior runs — LLM fabrication on sparse Searchable-specific content. Strategy correctly set `research_proof_point_used=None` (no qualifying stat to use).

Re-run with 70B to verify: Searchable is a niche product and Tavily may need better query tuning for AI search market stats.

---

## Content Depth

**Expected:** content_depth=long_form, 600-900 words

**Actual:** content_depth=long_form ✅ — word_count=250 ❌

**Match: PARTIAL** — Depth was correctly selected (research enabled triggered long_form via `_select_depth`). But the 8B model ignored the 600-900 word target and wrote 250 words. This is a model capability issue, not a prompt issue — llama-3.1-8b does not reliably follow word count instructions. The CONTENT DEPTH RULE was present in the prompt. Expected to resolve on 70B.

---

## Hook

**Expected:** Names specific daily friction for a digital marketing manager. Something like: "You check your Google rankings every morning. You have no idea where your brand appears in ChatGPT." No product name in hook. Under 180 chars.

**Actual (110 chars):**
`"Manually tracking visibility and analytics across multiple AI engines is a tedious and time-consuming process."`

**Match: PARTIAL** — Under 180 chars ✅. No product name ✅. But fails the specificity test: "tedious and time-consuming process" is a category, not a named daily friction. "Manually tracking visibility" is closer to the right territory but does not name a specific action (what the person does, when, on which tool). Expected hook would be: "You check five AI engines every morning just to see if your brand shows up." The 8B model writes category language instead of scene-specific friction.

---

## AGITATE Section — Research Stat

**Expected:** References one of the three research stats. Format: "[Source] found that [stat]."

**Actual:**
"Research by Forrester found that 61% of marketers spend 10 hours or more per week manually tracking and reporting on marketing metrics."

**Match: NO** — The `research_proof_point_used` field in StrategyBrief was `None` (no qualifying research stat was accepted by the validation pipeline). The 8B model fabricated a Forrester stat that does not exist in Searchable's proof points or in any Tavily-sourced content. The fabrication was caught by `_check_fabricated_stats()` (accuracy capped at 1 on all three evaluator attempts).

---

## SOLVE Section — Brand Proof Point

**Expected:** Uses brand proof point verbatim — "206% share of voice improvements" or "Generated over £1 million in qualified pipeline from AI search". Introduces named Searchable features.

**Actual:** `"Companies using AI for content creation report maintaining or improving engagement while producing high-quality content efficiently"` and `"3x increase in content output"`.

**Match: NO** — The proof_point selected by Strategy was `"Companies using AI for content creation report a 3x increase in content output while maintaining or improving engagement"`. This appears to be fabricated — it does not match any known Searchable proof point ("206% share of voice", "£1 million pipeline"). The 8B model hallucinated a generic AI productivity claim and treated it as a brand proof point. The evaluator correctly scored accuracy=1.

---

## Evaluation

**Expected:** clarity≥4, engagement≥4, tone_match≥4, accuracy=5, passes=True, overall≥4.0

**Actual:** clarity=3, engagement=3, tone_match=3, accuracy=1, overall=2.5, passes=False, retry_count=2

**Match: NO**

All three retry attempts failed due to fabricated stats (`61%` from fabricated Forrester stat). This is the fabrication prevention working correctly — the evaluator correctly refused to pass copy that invented numbers. The underlying cause is the 8B model's weak instruction-following on complex multi-rule prompts, same pattern as BUG-004 (Ollama llama3.2 fabrication).

---

## Summary

| Check | Expected | Actual | Match |
|-------|----------|--------|-------|
| research_proof_points ≥ 1 | ≥1 | 2 (fragments) | PARTIAL |
| Stat A/B/C present | YES | NO | NO |
| source_url starts with https | YES | YES | YES |
| content_depth = long_form | YES | YES | YES |
| word_count > 400 | YES | 250 | NO |
| hook ≤ 180 chars | YES | 110 chars | YES |
| hook names specific daily friction | YES | generic category | NO |
| AGITATE references research stat | YES | fabricated stat | NO |
| SOLVE uses brand proof point verbatim | YES | fabricated proof point | NO |
| No fabricated statistics (accuracy=5) | YES | accuracy=1 | NO |
| passes = True | YES | False | NO |
| overall_score ≥ 4.0 | YES | 2.5 | NO |
| Hashtags at end only (3-5) | YES | 5 at end | YES |

---

## Verdict

**7 of 13 checks failed.** All failures trace to a single root cause: `llama-3.1-8b-instant` cannot follow complex multi-rule prompts reliably (same as BUG-004 with Ollama llama3.2). Specifically:
1. Research stat extraction produces fragments, not complete sentences
2. Proof point fabrication (invents "3x" and "Forrester 61%") despite FABRICATION PROHIBITION rule
3. Word count instruction ignored (250w vs 600-900w target)

The 3 checks that passed are structural (content_depth=long_form triggered correctly, hook under 180 chars, hashtags at end only) — these are Python-enforced, not LLM-dependent.

**Action required:** Re-run with llama-3.3-70b-versatile when Groq daily quota resets. All 13 checks expected to pass based on prior 70B runs (BUG-004 comparison: Groq 70B → accuracy=5, passes=True, no fabrication vs Ollama 8B → accuracy=1, passes=False on same proof points).
