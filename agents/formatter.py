"""
Step 8: Formatter.

Applies platform-specific structural rules from platform_rules.json.
In real mode, uses an LLM to apply LinkedIn formatting rules and returns a
structured FormattedContent. In mock mode, returns a deterministic result.

If revision_hint is provided (retry path), it is prepended to the system
prompt so the LLM applies the specific fix before re-formatting.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from llm.client import chat_completion
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.formatted_content import (
    FormattedContent,
    InstagramContent,
    LinkedInContent,
    TwitterContent,
)
from schemas.strategy_brief import StrategyBrief
from schemas.product_knowledge import ProductKnowledge
from agents._utils import parse_json_object, utc_now_iso

logger = logging.getLogger(__name__)

_HASHTAG_TOKEN = re.compile(r"#\w[\w]*", re.UNICODE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_rules() -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _normalize_hashtag(tag: str) -> str:
    tag = tag.strip()
    if not tag:
        return tag
    return tag if tag.startswith("#") else f"#{tag}"


def _truncate_at_word_boundary(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    sp = cut.rfind(" ")
    if sp > max_len // 2:
        cut = cut[:sp]
    return cut.rstrip()


def _formatter_context_block(
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
) -> str:
    """Strategy + voice context so Twitter/Instagram formatters keep product truth (LinkedIn gets same in real mode)."""
    return (
        "Use this strategy and voice context when structuring output. Do not invent claims, stats, or customers "
        "not present below.\n\n"
        f"narrative_arc: {strategy_brief.narrative_arc}\n"
        f"hook_direction: {strategy_brief.hook_direction}\n"
        f"lead_pain_point: {strategy_brief.lead_pain_point}\n"
        f"primary_claim: {strategy_brief.primary_claim}\n"
        f"proof_point (use verbatim in one tweet or in caption body): {strategy_brief.proof_point}\n"
        f"cta_intent: {strategy_brief.cta_intent}\n"
        f"differentiator: {strategy_brief.differentiator}\n"
        f"writing_instruction: {brand_profile.writing_instruction}\n"
        f"content_type: {content_brief.content_type}\n"
    )


def _snippet_for_short_tweet(
    raw_copy: str,
    strategy_brief: StrategyBrief | None,
) -> str:
    """Expand a too-short tweet 1 using strategy or raw copy — avoid generic SaaS boilerplate."""
    if strategy_brief is not None:
        for candidate in (
            strategy_brief.lead_pain_point,
            strategy_brief.primary_claim,
            strategy_brief.hook_direction,
        ):
            c = (candidate or "").strip()
            if len(c) >= 35:
                return _truncate_at_word_boundary(c, 220)
    for line in raw_copy.splitlines():
        ln = line.strip()
        if not ln:
            continue
        ln = re.sub(r"^\d+\/\s*", "", ln)
        if len(ln) >= 35:
            return _truncate_at_word_boundary(ln, 220)
    return (
        "Name one specific daily friction your buyer feels—time lost, rework, or unclear ownership—"
        "not a vague productivity claim."
    )


def _parse_numbered_tweets(raw_copy: str) -> list[str]:
    """Split copywriter 1/ ... 2/ ... output into tweet bodies."""
    lines = [ln.strip() for ln in raw_copy.splitlines() if ln.strip()]
    tweets: list[str] = []
    buf: list[str] = []
    header = re.compile(r"^\d+\/\s*")

    for ln in lines:
        if header.match(ln):
            if buf:
                tweets.append(" ".join(buf).strip())
                buf = []
            buf.append(header.sub("", ln).strip())
        else:
            buf.append(ln)
    if buf:
        tweets.append(" ".join(buf).strip())
    return [t for t in tweets if t]


def _pad_tweets_to_four(
    tweets: list[str],
    raw_copy: str,
    strategy_brief: StrategyBrief | None = None,
) -> list[str]:
    out = list(tweets)
    safety = 0
    extras: list[str] = []
    if strategy_brief is not None:
        for blob in (
            strategy_brief.differentiator,
            strategy_brief.lead_pain_point,
            strategy_brief.primary_claim,
        ):
            b = (blob or "").strip()
            if len(b) < 25:
                continue
            for part in re.split(r"(?<=[.!?])\s+", b):
                p = part.strip()
                if len(p) >= 30 and p not in extras:
                    extras.append(p)
    raw_chunks = [x.strip() for x in raw_copy.split("\n\n") if x.strip()]
    safety = 0
    while len(out) < 4 and safety < 20:
        safety += 1
        if not out:
            chunks = raw_chunks[:4] if raw_chunks else []
            if len(chunks) < 4:
                for e in extras:
                    if len(chunks) >= 4:
                        break
                    chunks.append(e)
            while len(chunks) < 4:
                chunks.append("One concrete outcome buyers care about from the proof above.")
            out = chunks[:4]
            break
        idx = max(range(len(out)), key=lambda i: len(out[i]))
        chunk = out[idx]
        if len(chunk) < 40:
            fill = None
            if extras:
                fill = extras[len(out) % len(extras)]
            elif raw_chunks:
                fill = raw_chunks[len(out) % len(raw_chunks)]
            out.insert(idx + 1, fill or "Spell out why this changes a weekly workflow—not generic benefits.")
            continue
        mid = max(20, len(chunk) // 2)
        sp = chunk.rfind(" ", 0, mid)
        if sp < 10:
            sp = mid
        a, b = chunk[:sp].strip(), chunk[sp:].strip()
        if not b:
            b = extras[0] if extras else "Tie the takeaway to the proof_point—no new numbers."
        out = out[:idx] + [a, b] + out[idx + 1 :]
    ei = 0
    while len(out) < 4:
        out.append(extras[ei % len(extras)] if extras else "Bridge to the CTA using only claims already in the strategy block.")
        ei += 1
    return out[:8]


def _twitter_postprocess_llm(
    tweets: list[str],
    hashtags: list[str],
    raw_copy: str,
    strategy_brief: StrategyBrief | None = None,
) -> TwitterContent:
    # Normalize tweet strings
    tw = [str(t).strip() for t in tweets if str(t).strip()]
    tw = _pad_tweets_to_four(tw, raw_copy, strategy_brief)
    if len(tw) > 8:
        tw = tw[:8]

    tags = [_normalize_hashtag(str(h)) for h in hashtags if h]
    tags = [t for t in tags if t]

    # Collect inline hashtags from tweets 0..n-2 and strip them
    moved: list[str] = []
    for i in range(max(0, len(tw) - 1)):
        found = _HASHTAG_TOKEN.findall(tw[i])
        if found:
            moved.extend(found)
            tw[i] = _HASHTAG_TOKEN.sub("", tw[i]).strip()
    # Strip hashtags from last tweet body before re-append (we add canonical tags)
    if tw:
        moved.extend(_HASHTAG_TOKEN.findall(tw[-1]))
        tw[-1] = _HASHTAG_TOKEN.sub("", tw[-1]).strip()

    for t in tags:
        if t not in moved:
            moved.append(t)
    seen: set[str] = set()
    deduped: list[str] = []
    for t in moved:
        low = t.lower()
        if low not in seen:
            seen.add(low)
            deduped.append(t)
    tags = deduped[:2]
    if not tags:
        tags = ["#saas"]

    # Truncate each tweet (leave room for hashtags on final)
    for i in range(len(tw)):
        limit = 280 - (len(" ".join(tags)) + 1) if i == len(tw) - 1 else 280
        limit = max(40, limit)
        tw[i] = _truncate_at_word_boundary(tw[i], limit)

    suffix = " " + " ".join(tags)
    if len(tw[-1]) + len(suffix) > 280:
        tw[-1] = _truncate_at_word_boundary(tw[-1], 280 - len(suffix))
    tw[-1] = (tw[-1] + suffix).strip()
    tw[-1] = _truncate_at_word_boundary(tw[-1], 280)

    if tw[0] and len(tw[0]) < 60:
        tw[0] = (tw[0].rstrip(".") + " " + _snippet_for_short_tweet(raw_copy, strategy_brief)).strip()
        tw[0] = _truncate_at_word_boundary(tw[0], 280)

    counts = [len(x) for x in tw]
    return TwitterContent(
        tweets=tw,
        tweet_char_counts=counts,
        hashtags=tags,
    )


_CATEGORY_IG_TAGS: dict[str, list[str]] = {
    "developer-tool": ["#devtools", "#developers", "#engineering", "#buildinpublic", "#apis", "#techstartup"],
    "project-management": ["#projectmanagement", "#productivity", "#agile", "#workflow", "#teamwork"],
    "fintech-saas": ["#fintech", "#payments", "#b2bfinance", "#saasfinance", "#finops"],
    "hr-people": ["#hrtech", "#peopleops", "#recruiting", "#talentmanagement", "#workplaceculture"],
    "data-analytics": ["#dataanalytics", "#bi", "#datascience", "#insights", "#dashboards"],
    "customer-success": ["#customersuccess", "#crm", "#customerexperience", "#b2bsaas", "#supportops"],
    "marketing-content": ["#contentmarketing", "#saasmarketing", "#growthhacking", "#digitalmarketing", "#contentops"],
    "security-compliance": ["#cybersecurity", "#compliance", "#infosec", "#securitytools", "#cloudsecurity"],
    "vertical-saas": ["#verticalsaas", "#industrytech", "#specialistsoftware"],
    "other": ["#saas", "#b2bsoftware", "#software", "#startup"],
}

_GENERIC_IG_PAD_TAGS = [
    "#saas", "#b2b", "#startup", "#techstartup", "#productdesign", "#futureofwork",
    "#worksmarter", "#productivityhacks", "#automation", "#digitaltools",
    "#b2bmarketing", "#founders", "#startupgrowth", "#remoteteams", "#innovation",
    "#softwaredevelopment", "#techleaders", "#modernwork", "#scaleyourbusiness",
    "#workflowautomation",
]


def _instagram_pad_hashtags(
    hashtags: list[str],
    product_category: str,
    features: list,
    messaging_angles: list[str] | None = None,
) -> list[str]:
    out = [_normalize_hashtag(h) for h in hashtags if h]
    seen = {h.lower() for h in out}

    # 1. Category-specific tags
    for tag in _CATEGORY_IG_TAGS.get(product_category, _CATEGORY_IG_TAGS["other"]):
        if len(out) >= 25:
            break
        if tag.lower() not in seen:
            out.append(tag)
            seen.add(tag.lower())

    # 2. Messaging angle slugs (derive real tags from strategy angles)
    for angle in (messaging_angles or []):
        if len(out) >= 25:
            break
        slug = re.sub(r"[^\w]+", "", angle.lower())[:22]
        if len(slug) >= 3:
            tag = f"#{slug}"
            if tag.lower() not in seen:
                out.append(tag)
                seen.add(tag.lower())

    # 3. Feature name slugs
    for feat in features:
        if len(out) >= 25:
            break
        name = getattr(feat, "name", str(feat))
        slug = re.sub(r"[^\w]+", "", name.lower())[:20]
        if len(slug) < 2:
            continue
        tag = f"#{slug}"
        if tag.lower() not in seen:
            out.append(tag)
            seen.add(tag.lower())

    # 4. Generic SaaS pad tags (no placeholder #topic{n})
    for pad in _GENERIC_IG_PAD_TAGS:
        if len(out) >= 20:
            break
        if pad.lower() not in seen:
            out.append(pad)
            seen.add(pad.lower())

    return out[:30]


def _instagram_postprocess(
    preview_text: str,
    body: str,
    hashtags: list[str],
    product_knowledge: ProductKnowledge | None,
) -> InstagramContent:
    preview_text = _truncate_at_word_boundary(preview_text.strip(), 125)
    body = body.strip().rstrip("\n")
    pk = product_knowledge
    if pk is not None:
        tags = _instagram_pad_hashtags(
            hashtags, pk.product_category, pk.features, pk.messaging_angles
        )
    else:
        tags = _instagram_pad_hashtags(hashtags, "other", [], None)

    full_caption = f"{preview_text}\n{body}\n\n\n\n\n{' '.join(tags)}"
    return InstagramContent(
        preview_text=preview_text,
        body=body,
        hashtags=tags,
        full_caption=full_caption,
    )


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock_linkedin(
    raw_copy: str,
    content_brief: ContentBrief,
    retry_count: int,
    revision_hint: str | None,
) -> FormattedContent:
    lines = [x.strip() for x in raw_copy.splitlines() if x.strip()]
    hook_raw = lines[0] if lines else "Most engineering teams don't have a project management problem."
    hook = hook_raw[:180]

    body_lines = lines[1:] if len(lines) > 1 else ["Content generated by Genate pipeline."]
    body = "\n\n".join(body_lines)

    hashtags = ["#engineeringmanagement", "#softwaredevelopment", "#productivity"]
    full_post = f"{hook}\n\n{body}\n\n{' '.join(hashtags)}"

    return FormattedContent(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        platform="linkedin",
        linkedin_content=LinkedInContent(
            hook=hook,
            body=body,
            hashtags=hashtags,
            full_post=full_post,
        ),
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )


def _mock_twitter(
    raw_copy: str,
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    retry_count: int,
    revision_hint: str | None,
) -> FormattedContent:
    tw = _parse_numbered_tweets(raw_copy)
    tw = [x for x in tw if x]
    tw = _pad_tweets_to_four(tw, raw_copy, strategy_brief)
    tw = tw[:8]
    tags = ["#saas"]
    tc = _twitter_postprocess_llm(tw, tags, raw_copy, strategy_brief)
    return FormattedContent(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        platform="twitter",
        twitter_content=tc,
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )


def _mock_instagram(
    raw_copy: str,
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    retry_count: int,
    revision_hint: str | None,
    product_knowledge: ProductKnowledge | None = None,
) -> FormattedContent:
    raw = raw_copy.strip()
    if not raw:
        raw = (
            f"{strategy_brief.lead_pain_point}\n\n{strategy_brief.primary_claim}".strip()
            or "Caption body from Genate mock pipeline."
        )
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if lines:
        preview = _truncate_at_word_boundary(lines[0], 125)
        body = "\n\n".join(lines[1:]).strip()
    else:
        preview = _truncate_at_word_boundary(raw, 125)
        body = ""
    if not body:
        body = (
            f"{strategy_brief.primary_claim}\n\n{strategy_brief.proof_point}".strip()
            if strategy_brief
            else raw[len(preview) :].strip()
        )
    if not body:
        body = "See how teams apply this in one focused workflow—link in bio."
    tags = _instagram_pad_hashtags(
        [],
        product_knowledge.product_category if product_knowledge else "saas",
        product_knowledge.features if product_knowledge else [],
    )
    ic = _instagram_postprocess(preview, body, tags, product_knowledge)
    return FormattedContent(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        platform="instagram",
        instagram_content=ic,
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )


# ---------------------------------------------------------------------------
# Real-mode system prompts
# ---------------------------------------------------------------------------

_LINKEDIN_SYSTEM = (
    "You are a content formatter. Apply LinkedIn platform rules exactly.\n\n"
    "LinkedIn rules:\n"
    "- Hook must be a standalone statement in the first 180 characters\n"
    "- 3-5 hashtags at end only, never inline in the body\n"
    "- Short paragraphs with a blank line between each\n\n"
    "Return ONLY valid JSON with these exact fields:\n"
    "  hook: the standalone opening line (max 180 chars)\n"
    "  body: the full post body excluding the hook line and hashtags\n"
    "  hashtags: list of 3-5 hashtags, each starting with #\n"
    "  full_post: hook + two newlines + body + two newlines + hashtags space-joined"
)

_TWITTER_SYSTEM = (
    "For Twitter/X threads:\n"
    "- Output a JSON object with 'tweets' (list of strings) and "
    "'hashtags' (list of 1-2 strings starting with #)\n"
    "- Tweet 1 must work completely standalone — hook and core insight in one tweet, max 280 chars\n"
    "- Each tweet is one self-contained idea\n"
    "- Final tweet contains the CTA + hashtags\n"
    "- Never put hashtags in tweets 1 through N-1\n"
    "- Each tweet must be <= 280 characters\n"
    "- Thread length: 4 tweets minimum, 8 maximum\n"
    "- Follow hook_direction and narrative_arc from the user context; tweet 1 should reflect "
    "lead_pain_point or hook_direction, not a generic 'your team' opener unless it names that friction\n"
    "- Include the proof_point text verbatim in exactly one middle tweet (not tweet 1)\n"
    "- Do not rename the product or swap claims—stay aligned with primary_claim"
)

_INSTAGRAM_SYSTEM = (
    "For Instagram:\n"
    "- preview_text: first 125 chars must be a complete emotional statement — "
    "the sentence must end before 125 chars, not mid-word\n"
    "- body: the caption body after the preview\n"
    "- hashtags: 20-30 hashtags. Place after 5 blank lines in full_post.\n"
    "- Never put hashtags inline in body or preview_text\n"
    "- First line must make the reader stop scrolling\n"
    "- preview_text and body must reflect lead_pain_point, primary_claim, and proof_point from context; "
    "include proof_point verbatim in the body\n"
    "- Match writing_instruction (voice); emotional hook first, then rational support\n\n"
    "Return ONLY valid JSON with keys: preview_text, body, hashtags (list of strings with #)."
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    raw_copy: str,
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    revision_hint: str | None = None,
    retry_count: int = 0,
    product_knowledge: ProductKnowledge | None = None,
) -> FormattedContent:
    platform = content_brief.platform
    run_id = content_brief.run_id
    org_id = content_brief.org_id

    # ── Mock path ────────────────────────────────────────────────────────────
    if settings.MOCK_MODE:
        if platform == "linkedin":
            return _mock_linkedin(raw_copy, content_brief, retry_count, revision_hint)
        if platform == "twitter":
            return _mock_twitter(
                raw_copy, content_brief, strategy_brief, retry_count, revision_hint
            )
        if platform == "instagram":
            return _mock_instagram(
                raw_copy,
                content_brief,
                strategy_brief,
                retry_count,
                revision_hint,
                product_knowledge,
            )
        lines = [x.strip() for x in raw_copy.splitlines() if x.strip()]
        hook = lines[0][:180] if lines else "SaaS content pipeline output."
        body = "\n\n".join(lines[1:]) if len(lines) > 1 else raw_copy
        hashtags = ["#saas", "#marketing", "#content"]
        return FormattedContent(
            run_id=content_brief.run_id,
            org_id=content_brief.org_id,
            created_at=utc_now_iso(),
            platform="linkedin",
            linkedin_content=LinkedInContent(
                hook=hook,
                body=body,
                hashtags=hashtags,
                full_post=f"{hook}\n\n{body}\n\n{' '.join(hashtags)}",
            ),
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    # ── Real mode: LinkedIn ──────────────────────────────────────────────────
    if platform == "linkedin":
        system = _LINKEDIN_SYSTEM
        if revision_hint:
            system = (
                f"REVISION REQUIRED: {revision_hint}\n"
                "Apply this specific fix to the copy below before formatting.\n\n"
                + system
            )
        user_msg = (
            _formatter_context_block(content_brief, strategy_brief, brand_profile)
            + "\n---\nFormat this copy for LinkedIn:\n\n"
            + raw_copy
        )
        raw_response = chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
        )
        try:
            data = parse_json_object(raw_response)
        except ValueError:
            logger.warning("Formatter: LLM returned non-JSON; falling back to mechanical parse")
            return _mock_linkedin(raw_copy, content_brief, retry_count, revision_hint)

        hashtags_raw = data.get("hashtags", [])
        if isinstance(hashtags_raw, str):
            hashtags_raw = hashtags_raw.split()
        hashtags = [_normalize_hashtag(h) for h in hashtags_raw if h]
        if len(hashtags) < 3:
            hashtags += ["#saas", "#marketing", "#b2b"][: 3 - len(hashtags)]
        hashtags = hashtags[:5]

        hook = str(data.get("hook", "")).strip()[:180]
        if not hook:
            lines = [x.strip() for x in raw_copy.splitlines() if x.strip()]
            hook = lines[0][:180] if lines else "SaaS marketing copy."
        body = str(data.get("body", "")).strip()
        if not body:
            body = raw_copy
        # Strip inline hashtags from body — they belong at the end only
        body = _HASHTAG_TOKEN.sub("", body).strip()
        # Always rebuild full_post to prevent LLM from duplicating hashtags
        full_post = f"{hook}\n\n{body}\n\n{' '.join(hashtags)}"

        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="linkedin",
            linkedin_content=LinkedInContent(
                hook=hook,
                body=body,
                hashtags=hashtags,
                full_post=full_post,
            ),
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    # ── Real mode: Twitter ───────────────────────────────────────────────────
    if platform == "twitter":
        system = _TWITTER_SYSTEM
        if revision_hint:
            system = f"REVISION REQUIRED: {revision_hint}\n\n" + system
        user_msg = (
            _formatter_context_block(content_brief, strategy_brief, brand_profile)
            + "\n---\nFormat this thread from raw copy (may use 1/ 2/ numbering). "
            "Preserve substance from the strategy block; do not drift to a different product story.\n\n"
            + raw_copy
        )
        raw_response = chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
        )
        try:
            data = parse_json_object(raw_response)
        except ValueError:
            logger.warning("Formatter Twitter: non-JSON; falling back to parse of raw_copy")
            tw = _parse_numbered_tweets(raw_copy)
            tc = _twitter_postprocess_llm(tw, ["#saas"], raw_copy, strategy_brief)
        else:
            tweets_raw = data.get("tweets", [])
            if isinstance(tweets_raw, str):
                tweets_raw = [tweets_raw]
            tags_raw = data.get("hashtags", [])
            if isinstance(tags_raw, str):
                tags_raw = [tags_raw]
            tc = _twitter_postprocess_llm(
                list(tweets_raw), list(tags_raw), raw_copy, strategy_brief
            )
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="twitter",
            twitter_content=tc,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    # ── Real mode: Instagram ─────────────────────────────────────────────────
    if platform == "instagram":
        system = _INSTAGRAM_SYSTEM
        if revision_hint:
            system = f"REVISION REQUIRED: {revision_hint}\n\n" + system
        user_msg = (
            _formatter_context_block(content_brief, strategy_brief, brand_profile)
            + "\n---\nFormat this Instagram caption from raw copy:\n\n"
            + raw_copy
        )
        raw_response = chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
        )
        try:
            data = parse_json_object(raw_response)
        except ValueError:
            logger.warning("Formatter Instagram: non-JSON; mechanical split")
            preview = _truncate_at_word_boundary(raw_copy.strip(), 125)
            body = raw_copy.strip()[len(preview) :].strip() or " "
            ic = _instagram_postprocess(preview, body, [], product_knowledge)
        else:
            ht = data.get("hashtags", [])
            if isinstance(ht, str):
                ht = [ht]
            ic = _instagram_postprocess(
                str(data.get("preview_text", "")),
                str(data.get("body", "")),
                list(ht),
                product_knowledge,
            )
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="instagram",
            instagram_content=ic,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    # ── Real mode: Blog (programmatic) ──────────────────────────────────────
    body_text = raw_copy
    seo = content_brief.seo_keyword or "saas marketing"
    words = body_text.split()
    if seo.lower() not in " ".join(words[:100]).lower():
        body_text = f"{seo} helps teams produce brand-consistent content.\n\n{body_text}"
    return FormattedContent(
        run_id=run_id,
        org_id=org_id,
        created_at=utc_now_iso(),
        platform="blog",
        blog_content={
            "title": "SaaS Content Systems That Scale",
            "meta_title": "SaaS content system for faster GTM execution",
            "meta_description": (
                "Learn how SaaS teams use strategy-first workflows to generate "
                "brand-consistent content faster while grounding every claim in proof."
            ),
            "body": body_text,
            "word_count": len(body_text.split()),
            "internal_link_placeholders": ["[INTERNAL_LINK: brand messaging strategy]"],
            "seo_keyword": seo,
        },
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )
