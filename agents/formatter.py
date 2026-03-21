"""
Step 8: Formatter.
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas.content_brief import ContentBrief
from schemas.formatted_content import FormattedContent
from schemas.strategy_brief import StrategyBrief
from agents._utils import utc_now_iso


def _load_rules() -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_hashtag(tag: str) -> str:
    tag = tag.strip()
    if not tag:
        return tag
    return tag if tag.startswith("#") else f"#{tag}"


def run(
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    raw_copy: str,
    visual_payload: dict,
    retry_count: int = 0,
    revision_hint: str | None = None,
) -> FormattedContent:
    _ = _load_rules()
    platform = content_brief.platform

    if revision_hint:
        raw_copy = f"{raw_copy}\n\nRevision target: {revision_hint}"

    if platform == "linkedin":
        lines = [x.strip() for x in raw_copy.splitlines() if x.strip()]
        hook = lines[0][:180] if lines else "SaaS teams need clearer go-to-market execution."
        hashtags = ["#saas", "#marketing", "#content"]
        body = "\n\n".join(lines[1:] if len(lines) > 1 else lines)
        return FormattedContent(
            run_id=content_brief.run_id,
            org_id=content_brief.org_id,
            created_at=utc_now_iso(),
            platform="linkedin",
            linkedin_content={
                "hook": hook,
                "body": body,
                "hashtags": hashtags,
                "full_post": f"{hook}\n\n{body}\n\n{' '.join(hashtags)}".strip(),
            },
            image_prompt=visual_payload.get("image_prompt"),
            suggested_format=visual_payload.get("suggested_format", "static"),
            video_script=visual_payload.get("video_script"),
            video_hook=visual_payload.get("video_hook"),
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    if platform == "twitter":
        tweets = [x.strip() for x in raw_copy.split("\n\n") if x.strip()]
        tweets = tweets[:8] if len(tweets) >= 4 else tweets + ["More details coming soon."] * (4 - len(tweets))
        tags = [_normalize_hashtag("saas")]
        tweets[-1] = f"{tweets[-1]} {' '.join(tags)}".strip()
        return FormattedContent(
            run_id=content_brief.run_id,
            org_id=content_brief.org_id,
            created_at=utc_now_iso(),
            platform="twitter",
            twitter_content={
                "tweets": tweets,
                "tweet_char_counts": [len(x) for x in tweets],
                "hashtags": tags,
            },
            image_prompt=visual_payload.get("image_prompt"),
            suggested_format=visual_payload.get("suggested_format", "carousel"),
            video_script=visual_payload.get("video_script"),
            video_hook=visual_payload.get("video_hook"),
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    if platform == "instagram":
        clean = raw_copy.strip()
        preview = clean[:125]
        hashtags = [_normalize_hashtag(f"tag{i}") for i in range(1, 21)]
        full_caption = f"{preview}\n\n{clean[125:]}\n\n\n\n\n{' '.join(hashtags)}"
        return FormattedContent(
            run_id=content_brief.run_id,
            org_id=content_brief.org_id,
            created_at=utc_now_iso(),
            platform="instagram",
            instagram_content={
                "preview_text": preview,
                "body": clean[125:],
                "hashtags": hashtags,
                "full_caption": full_caption,
            },
            image_prompt=visual_payload.get("image_prompt"),
            suggested_format=visual_payload.get("suggested_format", "static"),
            video_script=visual_payload.get("video_script"),
            video_hook=visual_payload.get("video_hook"),
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )

    body = raw_copy
    seo = content_brief.seo_keyword or "saas marketing automation"
    words = body.split()
    if seo.lower() not in " ".join(words[:100]).lower():
        body = f"{seo} helps teams ship better content.\n\n{body}"
    return FormattedContent(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        platform="blog",
        blog_content={
            "title": "SaaS Content Systems That Scale",
            "meta_title": "SaaS content system for faster GTM execution and consistency",
            "meta_description": (
                "Learn how SaaS teams use strategy-first workflows to generate "
                "brand-consistent content faster while grounding every claim in proof."
            ),
            "body": body,
            "word_count": len(body.split()),
            "internal_link_placeholders": ["[INTERNAL_LINK: brand messaging strategy]"],
            "seo_keyword": seo,
        },
        image_prompt=visual_payload.get("image_prompt"),
        suggested_format=visual_payload.get("suggested_format", "static"),
        video_script=visual_payload.get("video_script"),
        video_hook=visual_payload.get("video_hook"),
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )
