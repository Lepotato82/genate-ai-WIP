"""
Step 4: Planner.

Selects content type, narrative arc, content pillar, and posting strategy.
Returns a ContentBrief consumed by the Strategy agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import ProductKnowledge
from agents._utils import parse_json_object, utc_now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_platform_rules() -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _platform_rules_summary(platform: str) -> list[str]:
    rules = _load_platform_rules()
    pr = rules.get(platform, {})
    if platform == "linkedin":
        return [
            f"Hook must be standalone in first {pr.get('hook_max_chars', 180)} characters",
            f"{pr.get('hashtags_min', 3)}-{pr.get('hashtags_max', 5)} hashtags at end only, never inline",
            "Short paragraphs with blank line between each",
        ]
    if platform == "twitter":
        return [
            f"Thread of {pr.get('thread_min', 4)}-{pr.get('thread_max', 8)} tweets ({pr.get('tweet_count', '4-8')})",
            f"Each tweet max {pr.get('max_chars_per_tweet', pr.get('tweet_max_chars', 280))} chars",
            f"Hashtags ({pr.get('hashtag_count', '1-2')}): {pr.get('hashtag_placement', 'final tweet only')}",
        ]
    if platform == "instagram":
        return [
            f"First {pr.get('first_chars', pr.get('preview_max_chars', 125))} chars: "
            f"{pr.get('first_chars_rule', 'complete emotional statement')}",
            (
                f"{pr.get('hashtag_count', '20-30')} hashtags; placement: "
                f"{pr.get('hashtag_placement', 'after 5 line breaks')}; "
                f"inline hashtags: {pr.get('hashtags_inline', False)}"
            ),
        ]
    if platform == "blog":
        return [
            f"Word count {pr.get('word_count_min', 1200)}-{pr.get('word_count_max', 2500)}",
            f"SEO keyword in first {pr.get('keyword_first_words', 100)} words",
            f"Meta title {pr.get('meta_title_min', 50)}-{pr.get('meta_title_max', 60)} chars",
        ]
    return ["Use platform-native structure", "Keep CTA singular"]


def _planner_signals(
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
) -> dict:
    return {
        "proof_point_count": len(product_knowledge.proof_points),
        "feature_count": len(product_knowledge.features),
        "pain_point_count": len(product_knowledge.pain_points),
        "brand_tone": brand_profile.tone,
        "has_strong_stat": any(p.proof_type == "stat" for p in product_knowledge.proof_points),
        "has_customer_name": any(
            p.proof_type == "customer_name" for p in product_knowledge.proof_points
        ),
    }


def _signal_block(signals: dict) -> str:
    lines = [f"{k}: {v}" for k, v in signals.items()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    platform: str,
) -> ContentBrief:
    signals = _planner_signals(brand_profile, product_knowledge)
    plat = platform if platform in ("linkedin", "twitter", "instagram", "blog") else "linkedin"

    if plat == "twitter":
        return ContentBrief(
            run_id=product_knowledge.run_id,
            org_id=product_knowledge.org_id,
            created_at=utc_now_iso(),
            platform="twitter",
            content_type="thread",
            narrative_arc="pain-agitate-solve-cta",
            content_pillar="education_and_insight",
            funnel_stage="tofu",
            slide_count_target=None,
            word_count_target=None,
            thread_length_target=5,
            posting_strategy={
                "recommended_frequency": "daily",
                "best_days": ["Tuesday", "Wednesday", "Thursday"],
                "best_time_window": "09:00-11:00 IST",
            },
            platform_rules_summary=_platform_rules_summary("twitter"),
            seo_keyword=None,
            knowledge_context_used=False,
            knowledge_context_summary=None,
            benchmark_reference=(
                "Threads earn higher bookmark and profile-click rates than single tweets "
                "for B2B SaaS when tweet 1 is a complete hook (platform norms 2025)."
            ),
            reasoning=(
                "Twitter/X always uses a thread (4–8 tweets). Signals: "
                f"feature_count={signals['feature_count']}, brand_tone={signals['brand_tone']} — "
                "thread fits explanatory SaaS narratives."
            ),
        )

    if plat == "instagram":
        return ContentBrief(
            run_id=product_knowledge.run_id,
            org_id=product_knowledge.org_id,
            created_at=utc_now_iso(),
            platform="instagram",
            content_type="carousel",
            narrative_arc="before-after-bridge-cta",
            content_pillar="product_and_solution",
            funnel_stage="tofu",
            slide_count_target=8,
            word_count_target=None,
            thread_length_target=None,
            posting_strategy={
                "recommended_frequency": "4x weekly",
                "best_days": ["Monday", "Wednesday", "Friday"],
                "best_time_window": "18:00-21:00 IST",
            },
            platform_rules_summary=_platform_rules_summary("instagram"),
            seo_keyword=None,
            knowledge_context_used=False,
            knowledge_context_summary=None,
            benchmark_reference=(
                "Instagram carousels drive higher saves and shares than single images "
                "for educational product breakdowns (social benchmark data)."
            ),
            reasoning=(
                "Carousel fits swipeable educational content; signals show "
                f"feature_count={signals['feature_count']} and "
                f"pain_point_count={signals['pain_point_count']} for multi-slide storytelling."
            ),
        )

    if plat == "blog":
        return ContentBrief(
            run_id=product_knowledge.run_id,
            org_id=product_knowledge.org_id,
            created_at=utc_now_iso(),
            platform="blog",
            content_type="thought_leadership",
            narrative_arc="stat-hook-problem-solution-cta",
            content_pillar="education_and_insight",
            funnel_stage="mofu",
            slide_count_target=None,
            word_count_target=1800,
            thread_length_target=None,
            posting_strategy={
                "recommended_frequency": "2x weekly",
                "best_days": ["Tuesday", "Thursday"],
                "best_time_window": "10:00-12:00 IST",
            },
            platform_rules_summary=_platform_rules_summary("blog"),
            seo_keyword="saas content operations",
            knowledge_context_used=False,
            knowledge_context_summary=None,
            benchmark_reference=(
                "Long-form SEO posts in the 1,500–2,000 word range rank for "
                "commercial-intent keywords in B2B SaaS (Ahrefs-style benchmarks)."
            ),
            reasoning="Blog mock: thought_leadership with SEO keyword for pipeline tests.",
        )

    # LinkedIn — vary away from default carousel
    ct: str = "text_post"
    sct = None
    reasoning = (
        f"text_post fits a single sharp idea given feature_count={signals['feature_count']}, "
        f"has_strong_stat={signals['has_strong_stat']}, brand_tone={signals['brand_tone']} — "
        "carousel reserved for 3+ distinct features or multi-step education."
    )
    if signals["feature_count"] >= 3 or signals["pain_point_count"] >= 3:
        ct = "carousel"
        sct = 8
        reasoning = (
            f"carousel for multi-step / educational breakdown: feature_count={signals['feature_count']}, "
            f"pain_point_count={signals['pain_point_count']}, has_strong_stat={signals['has_strong_stat']}."
        )
    if signals["has_strong_stat"] and ct != "carousel":
        ct = "single_image"
        reasoning = (
            "single_image anchors a stat-led or proof-forward visual; has_strong_stat=True, "
            f"brand_tone={signals['brand_tone']}."
        )

    return ContentBrief(
        run_id=product_knowledge.run_id,
        org_id=product_knowledge.org_id,
        created_at=utc_now_iso(),
        platform="linkedin",
        content_type=ct,  # type: ignore[arg-type]
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="pain_and_problem",
        funnel_stage="tofu",
        slide_count_target=sct,
        word_count_target=None,
        thread_length_target=None,
        posting_strategy={
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday", "Thursday"],
            "best_time_window": "10:00-12:00 IST",
        },
        platform_rules_summary=_platform_rules_summary("linkedin"),
        seo_keyword=None,
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference=(
            "LinkedIn carousel posts generate 3x more reach than text-only posts "
            "for B2B SaaS accounts (Socialinsider 2024 benchmark)."
        ),
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# System prompts (inline — YAML may extend later)
# ---------------------------------------------------------------------------

_SYSTEM_LINKEDIN = """You are a SaaS content strategist. Select the best LinkedIn content_type using the signals provided.

LinkedIn content_type rules:
- carousel: educational, step-by-step, feature comparisons, "X things you didn't know". Prefer when the product has 3+ distinct features OR 3+ pain points to show.
- text_post: opinion / thought leadership, founder voice, one sharp insight, contrarian takes. Prefer when brand_tone is technical or minimal and the story is one strong idea.
- single_image: stat-led, before/after, customer quotes. Prefer when has_strong_stat OR has_customer_name supports a visual anchor.
- poll: engagement / audience research ONLY if content_pillar is education_and_insight OR founder_team_voice. Use sparingly.
- short_video: not supported — if you would pick short_video, output content_type "carousel" instead.

Also return: narrative_arc, content_pillar, funnel_stage, slide_count_target (6-10 only for carousel), reasoning, benchmark_reference.

reasoning MUST explicitly reference: proof_point_count, feature_count, pain_point_count, brand_tone, has_strong_stat, has_customer_name.

Return ONLY valid JSON."""

_SYSTEM_TWITTER = """You are a SaaS content strategist planning for Twitter/X.

MANDATORY: content_type MUST be exactly "thread". No exceptions.

Return ONLY valid JSON with:
- content_type: "thread"
- narrative_arc, content_pillar, funnel_stage
- thread_length_target: integer 4-8
- reasoning (must reference the numeric signals provided)
- benchmark_reference"""

_SYSTEM_INSTAGRAM = """You are a SaaS content strategist planning for Instagram.

Select content_type:
- carousel: step-by-step, educational, swipeable stories
- single_image: stat-led, quote, one strong visual moment
- reel: not supported — if you would pick reel, output "carousel" instead.

Also return: narrative_arc, content_pillar, funnel_stage, slide_count_target (6-10, required for carousel only), reasoning, benchmark_reference.

reasoning MUST reference: proof_point_count, feature_count, pain_point_count, brand_tone, has_strong_stat, has_customer_name.

Return ONLY valid JSON."""

_VALID_LINKEDIN_CONTENT_TYPES = frozenset(
    {
        "carousel",
        "text_post",
        "multi_image",
        "short_video",
        "poll",
        "question_post",
        "single_image",
    }
)


def _apply_linkedin_post_rules(
    data: dict,
    signals: dict,
) -> None:
    """Adjust content_type using signals so we do not always default to carousel."""
    ct = str(data.get("content_type", "text_post"))
    if ct == "short_video":
        ct = "carousel"
        data["content_type"] = ct
    pillar = str(data.get("content_pillar", ""))
    if ct == "poll" and pillar not in ("education_and_insight", "founder_team_voice"):
        data["content_type"] = "carousel"
        ct = "carousel"

    if ct not in _VALID_LINKEDIN_CONTENT_TYPES:
        data["content_type"] = "text_post"
        ct = "text_post"

    fc = signals["feature_count"]
    hss = signals["has_strong_stat"]
    hcn = signals["has_customer_name"]
    ppc = signals["pain_point_count"]

    if hss and ct == "carousel" and fc < 3:
        data["content_type"] = "single_image"
        ct = "single_image"
    if fc < 3 and not hss and not hcn and ct == "carousel":
        data["content_type"] = "text_post"
        ct = "text_post"
    if hss and ct in ("text_post",) and fc < 3:
        data["content_type"] = "single_image"
        ct = "single_image"

    if ct == "carousel" and fc < 3 and ppc < 3 and not hss:
        data["content_type"] = "text_post"


def _normalize_thread_length(data: dict) -> None:
    tlt = data.get("thread_length_target", 5)
    try:
        tlt = int(tlt)
    except (TypeError, ValueError):
        tlt = 5
    data["thread_length_target"] = max(4, min(8, tlt))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    platform: str = "linkedin",
) -> ContentBrief:
    if settings.MOCK_MODE:
        return _mock(brand_profile, product_knowledge, platform)

    signals = _planner_signals(brand_profile, product_knowledge)
    signal_text = _signal_block(signals)

    if platform == "linkedin":
        system = _SYSTEM_LINKEDIN
    elif platform == "twitter":
        system = _SYSTEM_TWITTER
    elif platform == "instagram":
        system = _SYSTEM_INSTAGRAM
    else:
        system = _SYSTEM_LINKEDIN

    user_msg = (
        f"product_name: {product_knowledge.product_name}\n"
        f"product_category: {product_knowledge.product_category}\n"
        f"pain_points: {product_knowledge.pain_points[:5]}\n"
        f"messaging_angles: {product_knowledge.messaging_angles}\n"
        f"platform: {platform}\n\n"
        "signals:\n"
        f"{signal_text}"
    )

    raw = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    data = parse_json_object(raw)

    # --- Platform coercion ---
    if platform == "twitter":
        data["content_type"] = "thread"
        _normalize_thread_length(data)
    elif platform == "instagram":
        ct = str(data.get("content_type", "carousel"))
        if ct == "reel":
            ct = "carousel"
        if ct not in ("carousel", "single_image"):
            ct = "carousel"
        data["content_type"] = ct
    elif platform == "linkedin":
        _apply_linkedin_post_rules(data, signals)

    # carousel requires slide_count_target (6–10)
    if data.get("content_type") == "carousel":
        sct = data.get("slide_count_target")
        try:
            sct = int(sct)
        except (TypeError, ValueError):
            sct = 8
        data["slide_count_target"] = max(6, min(10, sct))
    else:
        data.pop("slide_count_target", None)

    if data.get("content_type") == "thread":
        _normalize_thread_length(data)
    else:
        data.pop("thread_length_target", None)

    reasoning = str(data.get("reasoning", "")).strip()
    if len(reasoning) < 20:
        reasoning = (
            f"Chose {data.get('content_type')} using signals: "
            f"feature_count={signals['feature_count']}, "
            f"pain_point_count={signals['pain_point_count']}, "
            f"has_strong_stat={signals['has_strong_stat']}, "
            f"has_customer_name={signals['has_customer_name']}, "
            f"brand_tone={signals['brand_tone']}."
        )

    if not data.get("posting_strategy"):
        data["posting_strategy"] = {
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday", "Thursday"],
            "best_time_window": "10:00-12:00 IST",
        }

    _VALID_ARCS = frozenset({
        "pain-agitate-solve-cta", "before-after-bridge-cta", "stat-hook-problem-solution-cta"
    })
    _ARC_MAP = {
        "problem agitation solution": "pain-agitate-solve-cta",
        "problem-agitation-solution": "pain-agitate-solve-cta",
        "pas": "pain-agitate-solve-cta",
        "before after bridge": "before-after-bridge-cta",
        "before-after-bridge": "before-after-bridge-cta",
        "stat hook": "stat-hook-problem-solution-cta",
        "stat-hook": "stat-hook-problem-solution-cta",
    }
    arc_raw = data.get("narrative_arc")
    if not isinstance(arc_raw, str) or arc_raw not in _VALID_ARCS:
        arc_str = str(arc_raw or "").strip().lower()
        data["narrative_arc"] = _ARC_MAP.get(arc_str, "pain-agitate-solve-cta")

    _VALID_PILLARS = frozenset({
        "pain_and_problem", "education_and_insight", "product_and_solution",
        "social_proof", "founder_team_voice"
    })
    _PILLAR_MAP = {
        "pain": "pain_and_problem",
        "problem": "pain_and_problem",
        "education": "education_and_insight",
        "insight": "education_and_insight",
        "product": "product_and_solution",
        "solution": "product_and_solution",
        "product differentiation": "product_and_solution",
        "social": "social_proof",
        "proof": "social_proof",
        "founder": "founder_team_voice",
        "team": "founder_team_voice",
    }
    pillar_raw = data.get("content_pillar")
    if not isinstance(pillar_raw, str) or pillar_raw not in _VALID_PILLARS:
        pillar_str = str(pillar_raw or "").strip().lower()
        matched = next((v for k, v in _PILLAR_MAP.items() if k in pillar_str), None)
        data["content_pillar"] = matched or "product_and_solution"

    _VALID_STAGES = frozenset({"tofu", "mofu", "bofu"})
    _STAGE_MAP = {
        "awareness": "tofu",
        "top": "tofu",
        "consideration": "mofu",
        "middle": "mofu",
        "decision": "bofu",
        "conversion": "bofu",
        "bottom": "bofu",
    }
    stage_raw = data.get("funnel_stage")
    if not isinstance(stage_raw, str) or stage_raw not in _VALID_STAGES:
        stage_str = str(stage_raw or "").strip().lower()
        matched_stage = next((v for k, v in _STAGE_MAP.items() if k in stage_str), None)
        data["funnel_stage"] = matched_stage or "tofu"

    return ContentBrief(
        run_id=product_knowledge.run_id,
        org_id=product_knowledge.org_id,
        created_at=utc_now_iso(),
        platform=platform,  # type: ignore[arg-type]
        platform_rules_summary=_platform_rules_summary(platform),
        word_count_target=None,
        seo_keyword=None,
        knowledge_context_used=False,
        knowledge_context_summary=None,
        reasoning=reasoning,
        narrative_arc=data["narrative_arc"],
        content_pillar=data["content_pillar"],
        funnel_stage=data["funnel_stage"],
        content_type=data["content_type"],
        posting_strategy=data["posting_strategy"],
        benchmark_reference=str(
            data.get("benchmark_reference") or "SaaS engagement benchmarks for the selected format."
        ),
        slide_count_target=data.get("slide_count_target"),
        thread_length_target=data.get("thread_length_target"),
    )
