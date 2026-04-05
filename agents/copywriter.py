"""
Step 6: Copywriter — raw copy from strategy + brief + brand (no structural formatting).
"""

from __future__ import annotations

import logging

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief

logger = logging.getLogger(__name__)


CTA_SIGNALS: dict[str, list[str]] = {
    "start_trial": ["trial", "try", "start", "free", "sign up", "get started"],
    "learn_more": ["learn", "read", "find out", "discover", "see how", "explore", "more"],
    "book_demo": ["demo", "book", "schedule", "call", "talk", "meet"],
    "sign_up": ["sign up", "register", "join", "create account", "get access"],
}


def _validate_cta(copy: str, cta_intent: str) -> bool:
    """Return True if a CTA signal for cta_intent appears in the last 20% of copy."""
    if not cta_intent:
        return True
    signals = CTA_SIGNALS.get(cta_intent, [])
    if not signals:
        return True
    copy_lower = copy.lower()
    cta_window = copy_lower[int(len(copy_lower) * 0.8):]
    return any(signal in cta_window for signal in signals)


def _validate_research_usage(copy: str, research_points: list) -> bool:
    """Return True if at least one research stat's first 4 words (≥3) appear in copy."""
    if not research_points:
        return True
    copy_lower = copy.lower()
    for point in research_points:
        stat_text = getattr(point, "text", "") or ""
        stat_words = stat_text.lower().split()[:4]
        if len(stat_words) < 3:
            # Short stat — check for literal substring presence
            if stat_text.lower() in copy_lower:
                return True
        elif sum(1 for w in stat_words if w in copy_lower) >= 3:
            return True
    return False


_LONG_FORM_WORD_TARGETS: dict[str, str] = {
    "linkedin":  "600-900 words",
    "twitter":   "6-8 tweets, each tweet fully developed (40-60 words per tweet)",
    "instagram": "250-400 words in the body section",
}

_CONCISE_WORD_TARGETS: dict[str, str] = {
    "linkedin":  "150-300 words",
    "twitter":   "4-6 tweets, each tweet concise (20-40 words per tweet)",
    "instagram": "80-150 words in the body section",
}


def _depth_instruction(platform: str, depth: str) -> str:
    if depth == "long_form":
        target = _LONG_FORM_WORD_TARGETS.get(platform, "600-900 words")
        return (
            f"\n\nCONTENT LENGTH — HARD REQUIREMENT:\n"
            f"Write {target}.\n"
            f"This is long_form content — write the full narrative arc "
            f"with complete sections. Do not summarise. Do not truncate.\n"
            f"Count your words mentally before returning. "
            f"If your draft is under the minimum, expand each section "
            f"with specific detail before returning."
        )
    target = _CONCISE_WORD_TARGETS.get(platform, "150-300 words")
    return (
        f"\n\nCONTENT LENGTH:\n"
        f"Write {target}. "
        f"Concise. One idea per paragraph. No padding."
    )


def _product_name_hint(strategy: StrategyBrief) -> str:
    claim = (strategy.primary_claim or "").strip()
    if not claim:
        return "Linear"
    first = claim.split()[0].strip(".,'\"")
    return first if first else "Linear"


def _mock_twitter(strategy: StrategyBrief) -> str:
    return (
        "1/ Your team is spending too long converting product truth into social copy.\n\n"
        "2/ The result is delayed launches and weak hooks.\n\n"
        "3/ Genate structures strategy first, then generates grounded messaging.\n\n"
        f"4/ Proof: {strategy.proof_point}\n\n"
        "5/ Read more and adapt this workflow for your next campaign."
    )


def _mock_instagram(strategy: StrategyBrief) -> str:
    return (
        "You are one scroll away from copy that actually matches your product truth.\n\n"
        "Most teams still ship generic hooks because strategy never meets the page.\n\n"
        f"We anchor every line in proof like: {strategy.proof_point}\n\n"
        "Try a workflow where brand, claim, and CTA stay aligned end to end."
    )


def _mock_linkedin_post(strategy: StrategyBrief) -> str:
    name = _product_name_hint(strategy)
    return (
        f"Your standup keeps circling the same blocked issues because nobody trusts the board.\n\n"
        f"That is not a people problem — it is a systems problem. When issue state drifts from reality, "
        f"every roadmap conversation starts with cleanup instead of decisions.\n\n"
        f"{name} is built for teams that ship software: fast keyboard flows, clear ownership, "
        f"and a roadmap that stays tied to execution.\n\n"
        f"{strategy.proof_point}\n\n"
        f"If you are tired of translating spreadsheets into status updates, it is worth seeing how "
        f"modern product teams run their weekly planning in one place.\n\n"
        f"#productmanagement #engineering #saas"
    )


def _mock_poll(strategy: StrategyBrief, platform: str) -> str:
    """Structured poll output in the INTRO/QUESTION/OPTION format the formatter expects."""
    intro = (
        "INTRO: Most SaaS teams face this exact friction every week - "
        "we want to know where you stand.\n"
        if platform == "linkedin" else ""
    )
    return (
        f"{intro}"
        f"QUESTION: What is your biggest obstacle right now?\n"
        f"OPTION_1: Lack of visibility\n"
        f"OPTION_2: Manual processes\n"
        f"OPTION_3: Tool fragmentation\n"
        f"OPTION_4: Team alignment\n"
    )


def _mock_single_tweet(strategy: StrategyBrief) -> str:
    """Single-tweet output — under 260 chars, ends with a hashtag."""
    claim = strategy.primary_claim or "Genate turns product truth into brand-native copy."
    tweet = claim[:220].rstrip(".")
    return f"{tweet}. See how it works → #saas #b2bmarketing"


def _mock_story(strategy: StrategyBrief) -> str:
    """Story output in HOOK/CTA format the formatter expects."""
    pain = strategy.lead_pain_point or "Your copy doesn't sound like your brand."
    hook = pain[:75].rstrip(".,;")
    return f"HOOK: {hook}.\nCTA: Link in bio"


def run(
    strategy_brief: StrategyBrief,
    content_brief: ContentBrief,
    brand_profile: BrandProfile,
    research_proof_points: list | None = None,
) -> str:
    if settings.MOCK_MODE:
        ct = content_brief.content_type
        platform = content_brief.platform
        if ct == "poll":
            return _mock_poll(strategy_brief, platform)
        if ct == "single_tweet":
            return _mock_single_tweet(strategy_brief)
        if ct == "story":
            return _mock_story(strategy_brief)
        if platform == "twitter":
            return _mock_twitter(strategy_brief)
        if platform == "instagram":
            return _mock_instagram(strategy_brief)
        return _mock_linkedin_post(strategy_brief)

    try:
        spec = load_prompt("copywriting_v1")
        base = spec.system_prompt
    except FileNotFoundError:
        logger.warning("[copywriter] copywriting_v1.yaml not found — using inline fallback")
        base = (
            "You are a SaaS copywriting agent. Write platform-native marketing copy "
            "that executes the given strategy exactly. Return ONLY the raw copy text — "
            "no labels, no markdown, no explanation."
        )
    system = (
        f"Brand voice instruction (non-negotiable):\n{brand_profile.writing_instruction}\n\n"
        f"{base}"
    )
    slide_hint = ""
    if content_brief.content_type == "carousel" and content_brief.slide_count_target:
        slide_hint = (
            f"\nslide_count_target: {content_brief.slide_count_target} "
            "(write a distinct slide heading + 2-3 lines per slide)"
        )

    _STRUCTURED_TYPES = frozenset({"poll", "story"})

    def _content_type_hint(brief: ContentBrief) -> str:
        ct = brief.content_type
        if ct == "poll":
            intro_note = (
                "INTRO line is optional — omit it entirely for Twitter polls."
                if brief.platform == "twitter"
                else "INTRO line is optional context before the question (LinkedIn only)."
            )
            return (
                "\n\nFORMAT — POLL (write ONLY these lines, nothing else):\n"
                f"INTRO: [1-2 sentence context — {intro_note}]\n"
                "QUESTION: [poll question, max 150 chars]\n"
                "OPTION_1: [max 25 chars]\n"
                "OPTION_2: [max 25 chars]\n"
                "OPTION_3: [max 25 chars]\n"
                "OPTION_4: [max 25 chars]\n"
                "No narrative. No hashtags. No other text."
            )
        if ct == "single_tweet":
            return (
                "\n\nFORMAT — SINGLE TWEET:\n"
                "Write ONE tweet only. Maximum 260 characters including 1-2 hashtags at the end. "
                "Lead with the hook. No thread numbering. No line breaks."
            )
        if ct == "question_post":
            return (
                "\n\nFORMAT — QUESTION POST:\n"
                "Line 1: A compelling question (max 180 chars, ends with ?).\n"
                "Lines 2-4: 2-3 sentences of context that make the question worth answering.\n"
                "Do not write a CTA sentence — the question IS the engagement.\n"
                "Final line: 3-5 hashtags space-separated."
            )
        if ct == "story":
            return (
                "\n\nFORMAT — INSTAGRAM STORY (write ONLY these two lines, nothing else):\n"
                "HOOK: [main text overlay, max 80 chars, punchy complete thought]\n"
                "CTA: [action text, max 25 chars — e.g. 'Swipe up' or 'Link in bio']"
            )
        return ""

    ct_hint = _content_type_hint(content_brief)
    platform_hint = ""
    if content_brief.platform == "twitter":
        platform_hint = (
            "\n\nWrite a Twitter thread. Format as numbered tweets:\n"
            "1/ [tweet text]\n"
            "2/ [tweet text]\n"
            "...\n"
            "The Formatter will split these into individual tweets.\n"
            "Tweet 1 must be a standalone hook under 280 chars.\n"
            "Execute hook_direction in tweet 1—lead with the specific friction in lead_pain_point "
            "or the angle in hook_direction, not a vague productivity opener.\n"
            "Include proof_point as one full tweet, copied verbatim (same words).\n"
            "Thread should advance narrative_arc; final tweet matches cta_intent.\n"
            "Stay on primary_claim and differentiator—do not invent a different product story."
        )
    elif content_brief.platform == "instagram":
        platform_hint = (
            "\n\nWrite Instagram caption copy. The first sentence must be a "
            "complete emotional statement under 125 chars that stops the scroll. "
            "Write for a mobile reader. Short sentences. Emotional before rational. "
            "The Formatter will add hashtags separately.\n"
            "Ground the caption in lead_pain_point and primary_claim; include proof_point "
            "verbatim in the body (same wording).\n"
            "Match writing_instruction; no hashtag lines—you will not add #tags yourself."
        )
    research_line = ""
    if strategy_brief.research_proof_point_used:
        research_line = (
            f"\nresearch_proof_point_used: {strategy_brief.research_proof_point_used}"
            f"\nresearch_source: {strategy_brief.research_source}"
        )

    # Build research block for user message — sorted tier_1 first
    active_research = research_proof_points or []
    research_block = ""
    if active_research:
        tier_order = {"tier_1": 0, "tier_2": 1, "tier_3": 2}
        sorted_pts = sorted(
            active_research,
            key=lambda p: tier_order.get(getattr(p, "credibility_tier", "tier_3"), 2),
        )
        lines = []
        for i, pt in enumerate(sorted_pts[:3], 1):
            src = getattr(pt, "source_name", "Research")
            text = getattr(pt, "text", "")
            tier = getattr(pt, "credibility_tier", "")
            lines.append(f"  {i}. [{tier}] {src} — \"{text}\"")
        research_block = (
            "\n\nresearch_proof_points (use ONE in the AGITATE section — "
            "mandatory format: \"[Source] found that [stat].\" — do not paraphrase):\n"
            + "\n".join(lines)
        )

    linkedin_long_form_line = ""
    if content_brief.platform == "linkedin" and content_brief.content_depth == "long_form":
        linkedin_long_form_line = (
            "linkedin_word_range: 600-900 (hard minimum 600 before finishing)\n"
        )

    user_msg = (
        f"platform: {content_brief.platform}\n"
        f"narrative_arc: {strategy_brief.narrative_arc}\n"
        f"content_depth: {content_brief.content_depth}\n"
        f"{linkedin_long_form_line}"
        f"lead_pain_point: {strategy_brief.lead_pain_point}\n"
        f"primary_claim: {strategy_brief.primary_claim}\n"
        f"proof_point: {strategy_brief.proof_point}\n"
        f"cta_intent: {strategy_brief.cta_intent}\n"
        f"writing_instruction: {brand_profile.writing_instruction}\n"
        f"hook_direction: {strategy_brief.hook_direction}"
        + research_line
        + research_block
        + slide_hint
        + platform_hint
        + ct_hint
        + ("" if content_brief.content_type in _STRUCTURED_TYPES else _depth_instruction(content_brief.platform, content_brief.content_depth))
        + "\n\nWrite the copy. Return only the copy text. No JSON.\n"
        "No preamble. No explanation."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    copy = chat_completion(messages).strip()

    # FIX 2 — CTA validation: retry once with explicit injection if CTA signal absent.
    # Skip for structured types (poll, story, question_post) which have no free-form CTA.
    if content_brief.content_type not in _STRUCTURED_TYPES | {"question_post"} and not _validate_cta(copy, strategy_brief.cta_intent):
        logger.warning(
            "[copywriter] CTA signal absent for cta_intent=%s — retrying with explicit injection",
            strategy_brief.cta_intent,
        )
        signals = CTA_SIGNALS.get(strategy_brief.cta_intent, [])
        cta_retry_msg = (
            user_msg
            + f"\n\nCRITICAL: Your copy is missing a CTA. "
            f"cta_intent is '{strategy_brief.cta_intent}'. "
            f"The final section MUST include at least one of: {signals}. "
            f"Place it in the last 20% of the copy."
        )
        copy = chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": cta_retry_msg}]
        ).strip()

    # FIX 3 — Research validation: retry once with explicit stat if research stat absent
    if active_research and not _validate_research_usage(copy, active_research):
        tier_order = {"tier_1": 0, "tier_2": 1, "tier_3": 2}
        best = sorted(
            active_research,
            key=lambda p: tier_order.get(getattr(p, "credibility_tier", "tier_3"), 2),
        )[0]
        best_src = getattr(best, "source_name", "Research")
        best_text = getattr(best, "text", "")
        logger.warning(
            "[copywriter] Research stat absent — retrying with explicit stat injection: %s",
            best_text[:80],
        )
        research_retry_msg = (
            user_msg
            + f"\n\nCRITICAL: You MUST include this research stat in the AGITATE section. "
            f"Copy this exact phrase verbatim: "
            f"\"{best_src} found that {best_text}\" "
            f"Do not paraphrase. Do not omit it."
        )
        copy = chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": research_retry_msg},
            ]
        ).strip()

    return copy
