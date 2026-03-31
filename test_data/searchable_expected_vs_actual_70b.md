# Searchable Research + Long-form Run — Expected vs Actual (70B)
Date: 2026-03-30
Model: llama-3.3-70b-versatile (Groq)
RESEARCH_AUGMENTATION_ENABLED: true
IMAGE_GENERATION_ENABLED: false
Output file: test_data/searchable_research_longform_run_70b.json

---

## Research Proof Points

**Expected:** At least one of Stat A (Gartner 25% search volume drop), Stat B (AirOps 30% brand visibility), or Stat C (Adobe 123% AI referral traffic growth). tier_1 or tier_2, source_url starts with https.

**Actual — 3 points returned:**
- [tier_2] Statista: `"six billion internet users worldwide"` — https://www.statista.com/topics/871/online-shopping/
- [tier_2] Statista: `"six billion internet users worldwide"` *(duplicate URL with different tracking param)*
- [tier_3] Coherent Solutions: `"nearly 65% of organizations have adopted or are actively investigating AI technologies for data and analytics"` — https://www.coherentsolutions.com/insights/...

**Match: PARTIAL**

- ≥1 result ✅
- All source_urls start with https ✅
- source_content_snippet NOT in output ✅
- None of Stat A/B/C appeared ❌
- Statista stat ("six billion internet users worldwide") is off-topic — pulled from an e-commerce topic page, not AI search research
- Coherent Solutions stat is adjacent but tier_3 and not specific to AI search visibility
- Duplicate result: seen_url deduplication should have caught the two Statista URLs — they differ only in srsltid tracking param. Root cause: URL dedup uses exact string match; tracking params break it.

`research_proof_point_used: None` — Strategy correctly declined to use these (stat quality too low for AGITATE).

**Action items:**
1. Fix URL dedup: strip query params before adding to `seen_urls` set (or normalise to scheme+host+path only).
2. Improve Tavily queries for AI search category: current queries (`"AI search optimization platform market statistics trends"`) are too broad and return e-commerce/general-internet stats. Add product-specific terms: `"GEO generative engine optimization"`, `"AI chatbot search visibility brands"`, `"AI search engine market share brands"`.

---

## Content Depth

**Expected:** content_depth=long_form, 600-900 words

**Actual:** content_depth=long_form ✅ — word_count=173 ❌

**Match: PARTIAL**

Depth was correctly selected (research augmentation + education_and_insight pillar). But the 70B model wrote 173 words against a 600-900 word target. The CONTENT DEPTH RULE is present in the prompt but the user message does not pass an explicit numeric target — the model reads the rule but defaults to concise copy length. This is a prompt wiring issue, not a model capability issue.

**Fix required:** Pass word count target explicitly in the copywriter user message when `content_depth == "long_form"`:
```
content_depth: long_form
word_count_target: 600-900 words (LinkedIn long_form)
```
The model responds to explicit numeric targets in the user message more reliably than rules in the system prompt.

---

## Hook

**Expected:** Specific daily friction for a digital marketing manager. Something like: "You check your Google rankings every morning. You have no idea where your brand appears in ChatGPT." Under 180 chars, no product name.

**Actual (91 chars):**
`"You're missing out on sales because your brand isn't visible where customers are searching."`

**Match: PARTIAL**

- Under 180 chars ✅
- No product name ✅
- Addresses the right problem area ✅
- Not a specific daily friction ❌ — "missing out on sales" is a consequence, not a named action. No specific person, no specific moment. Fails the specificity test: a marketing manager cannot read this and think "that is exactly what I do at 9am on Monday."

The `hook_direction` from StrategyBrief would be the right fix — if it names the specific action ("check five AI engines every morning"), the HOOK DIRECTION RULE forces the model to execute it literally. Confirm `hook_direction` is populated in the strategy brief for this run (check full JSON).

---

## AGITATE Section — Research Stat

**Expected:** References one of the three research stats. Format: "[Source] found that [stat]."

**Actual:** `"Gartner found that most B2B buyers consult AI engines before contacting a vendor."`

**Match: PARTIAL**

The model wrote a Gartner citation from its training data — not from the validated research pipeline (`research_proof_point_used=None`). Critically: this claim has no number, so it did not trigger the fabricated-stat cap (`accuracy=5`). The claim is directionally correct (Gartner has published similar research) but it is not grounded in a Tavily-sourced, validation-checked stat. It is effectively a hallucination of training-data memory, not research augmentation.

When `research_proof_point_used` is non-null, the model correctly cites `[Source] found that [stat]`. When null, it falls back to training-data memory. This is the intended fallback behaviour — the issue is the research pipeline is not yet finding high-quality stats for Searchable's category.

---

## SOLVE Section — Brand Proof Point

**Expected:** `"206% share of voice improvements"` or `"Generated over £1 million in qualified pipeline from AI search"` verbatim.

**Actual:** `"Our users have seen 206% share of voice improvements."`

**Match: YES** ✅

206% used verbatim. No approximation. No fabricated adjacent numbers.

---

## Evaluation

**Expected:** clarity≥4, engagement≥4, tone_match≥4, accuracy=5, passes=True, overall≥4.0

**Actual:** clarity=4, engagement=4, tone_match=5, accuracy=5, overall=4.5, passes=True, retry_count=0

**Match: YES** ✅

All dimensions at or above threshold. No retries. Fabrication prevention not triggered (Gartner claim has no number). tone_match=5 confirms the `minimal-saas` writing instruction was followed correctly.

---

## Hashtags

**Expected:** 3-5 hashtags at end only

**Actual:** `#AISearch #Searchable #GrowthStrategy` — 3 hashtags at end ✅

**Match: YES** ✅

---

## Full Checklist

| Check | Expected | Actual | Match |
|-------|----------|--------|-------|
| research_proof_points ≥ 1 | ≥1 | 3 | ✅ YES |
| Stat A/B/C present | YES | NO | ❌ NO |
| source_url starts with https | YES | YES | ✅ YES |
| source_content_snippet excluded | YES | YES | ✅ YES |
| content_depth = long_form | YES | YES | ✅ YES |
| word_count > 400 (long_form min) | YES | 173 | ❌ NO |
| hook ≤ 180 chars | YES | 91 chars | ✅ YES |
| hook names specific daily friction | YES | generic consequence | ❌ PARTIAL |
| AGITATE references research stat | YES | training-data Gartner (no number) | ⚠️ PARTIAL |
| SOLVE uses brand proof point verbatim (206%) | YES | YES | ✅ YES |
| No fabricated statistics (accuracy=5) | YES | YES (5) | ✅ YES |
| passes = True | YES | YES | ✅ YES |
| overall_score ≥ 4.0 | YES | 4.5 | ✅ YES |
| Hashtags at end only (3-5) | YES | 3 at end | ✅ YES |

**9 of 14 checks pass. 3 partial. 2 fail.**

---

## vs 8B Run

| Check | 8B | 70B |
|-------|----|-----|
| passes | False | True ✅ |
| overall_score | 2.5 | 4.5 ✅ |
| accuracy | 1 | 5 ✅ |
| content_depth=long_form | YES | YES |
| word_count target met | NO | NO |
| proof_point 206% verbatim | NO | YES ✅ |
| hook specificity | NO | PARTIAL |
| research stat used | NO | PARTIAL (training memory) |

70B resolves all fabrication and evaluation failures from the 8B run. Remaining gaps (word count, hook specificity, research stat quality) are addressable issues, not model capability ceilings.

---

## Action Items for Next Session

1. **Word count enforcement** — Pass explicit `word_count_target: 600-900` in copywriter user message when `content_depth=long_form`. This is a one-line addition to `agents/copywriter.py`.

2. **URL dedup fix** — Strip query params from Tavily result URLs before adding to `seen_urls` in `research_agent.py`. Prevents duplicate stats from the same domain.

3. **Tavily query improvement for AI search category** — Current queries are too generic. For products in `"AI search optimization"` / `"GEO"` category, add targeted terms: `"generative engine optimization brand visibility statistics"`, `"AI chatbot search market share brands 2025"`.

4. **Re-run with 70B once Tavily query is improved** — Expected: Stat A/B/C should appear; `research_proof_point_used` should be non-null; AGITATE should cite it explicitly.
