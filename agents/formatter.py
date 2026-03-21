"""
Step 8: Formatter — platform rules via LLM, then structured FormattedContent in Python.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.formatted_content import (
    BlogContent,
    FormattedContent,
    InstagramContent,
    LinkedInContent,
    TwitterContent,
)
from schemas.strategy_brief import StrategyBrief
from agents._utils import utc_now_iso

_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "platform_rules.json"


def _load_platform_rules() -> dict:
    if not _RULES_PATH.exists():
        return {}
    return json.loads(_RULES_PATH.read_text(encoding="utf-8"))


def _normalize_tag(t: str) -> str:
    t = t.strip()
    if not t:
        return t
    return t if t.startswith("#") else f"#{t}"


def _linkedin_from_text(text: str) -> LinkedInContent:
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    tag_idx: int | None = None
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        toks = s.split()
        if toks and all(t.startswith("#") for t in toks):
            tag_idx = i
            break
    if tag_idx is not None:
        main = "\n".join(lines[:tag_idx]).strip()
        hashtags = [_normalize_tag(t) for t in lines[tag_idx].split()]
    else:
        main = "\n".join(lines).strip()
        hashtags = ["#productmanagement", "#engineering", "#saas"]

    if len(hashtags) < 3:
        extra = ["#saas", "#b2b", "#startup", "#software", "#tech"]
        for e in extra:
            if len(hashtags) >= 3:
                break
            if e not in hashtags:
                hashtags.append(e)
    hashtags = hashtags[:5]

    hook = main[:180]
    body = main[180:].strip()
    if not body:
        body = "Read the full post above for the setup — then share what your team would change first."

    full_post = f"{hook}\n\n{body}\n\n{' '.join(hashtags)}".strip()
    return LinkedInContent(hook=hook[:180], body=body, hashtags=hashtags, full_post=full_post)


def _twitter_from_text(text: str) -> TwitterContent:
    numbered = re.split(r"(?m)^(?:Tweet\s*\d+\s*of\s*\d+|\d+\s*/)\s*", text.strip())
    chunks = [c.strip() for c in numbered if c.strip()]
    if len(chunks) < 2:
        chunks = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
    if len(chunks) < 4:
        while len(chunks) < 4:
            chunks.append("More context on why this workflow matters for SaaS teams.")
    chunks = chunks[:8]
    pad = " This shows up every sprint until the workflow changes."
    if len(chunks[0]) < 60:
        chunks[0] = (chunks[0] + pad)[:280]
    tags = ["#saas"]
    chunks[-1] = f"{chunks[-1]} {' '.join(tags)}".strip()
    return TwitterContent(tweets=chunks, tweet_char_counts=[len(t) for t in chunks], hashtags=tags)


def _instagram_from_text(text: str) -> InstagramContent:
    parts = text.split("\n\n\n\n\n")
    if len(parts) >= 2:
        main, tag_block = parts[0], parts[-1]
    else:
        main = text.strip()
        tag_block = ""
    prev = main[:125] if len(main) >= 125 else main
    body = main[125:] if len(main) > 125 else ""
    tags_raw = [w for w in tag_block.split() if w.startswith("#")]
    if len(tags_raw) < 20:
        base = ["#saas", "#startup", "#product", "#engineering", "#design", "#tech", "#b2b", "#software"]
        tags_raw = tags_raw + [f"#{base[i % len(base)]}{i}" for i in range(20 - len(tags_raw))]
    tags = [_normalize_tag(t) for t in tags_raw[:30]]
    full_caption = f"{prev}\n\n{body}\n\n\n\n\n{' '.join(tags)}"
    return InstagramContent(
        preview_text=prev[:125],
        body=body,
        hashtags=tags,
        full_caption=full_caption,
    )


def _blog_meta_title(title: str) -> str:
    t = (title or "Product delivery playbook").strip()
    if len(t) > 60:
        t = t[:57].rstrip() + "..."
    suffix = " for SaaS product teams"
    while len(t) < 50:
        t = (t + suffix)[:60]
    return t[:60]


def _blog_meta_description(body: str, seo_keyword: str) -> str:
    snippet = " ".join(body.split()[:45])
    extra = f" Covers {seo_keyword}, practical steps, and tradeoffs for growing teams."
    desc = (snippet + extra)[:160]
    while len(desc) < 140:
        desc = (desc + " Includes examples you can apply this week.")[:160]
    return desc[:160]


def _blog_from_text(text: str, seo_keyword: str) -> BlogContent:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0][:120] if lines else "How to streamline product delivery"
    body = "\n\n".join(lines[1:]) if len(lines) > 1 else text.strip()
    filler_para = (
        "\n\n## Deeper dive\n\n"
        "Teams that standardize how they capture issues, prioritize, and communicate status "
        "see fewer surprises in sprint reviews. The goal is not more process — it is a single "
        "place where decisions, evidence, and ownership stay aligned as the product evolves.\n\n"
    )
    while len(body.split()) < 1200:
        body = body + filler_para
    words = body.split()
    if len(words) > 2500:
        body = " ".join(words[:2500])
        words = body.split()
    wc = len(words)
    first_100 = " ".join(words[:100]).lower()
    if seo_keyword.lower() not in first_100:
        body = f"{seo_keyword} is the anchor for this guide.\n\n{body}"
        words = body.split()
        wc = len(words)
    meta_title = _blog_meta_title(title)
    meta_desc = _blog_meta_description(body, seo_keyword)
    placeholders = re.findall(r"\[INTERNAL_LINK:\s*[^\]]+\]", body)
    return BlogContent(
        title=title,
        meta_title=meta_title,
        meta_description=meta_desc,
        body=body,
        word_count=wc,
        internal_link_placeholders=placeholders,
        seo_keyword=seo_keyword,
    )


def _mock_formatted(
    raw_copy: str,
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    retry_count: int,
    revision_hint: str | None,
) -> FormattedContent:
    platform = content_brief.platform
    run_id = strategy_brief.run_id
    org_id = strategy_brief.org_id
    if platform == "linkedin":
        li = _linkedin_from_text(raw_copy)
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="linkedin",
            linkedin_content=li,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )
    if platform == "twitter":
        tw = _twitter_from_text(raw_copy)
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="twitter",
            twitter_content=tw,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )
    if platform == "instagram":
        ig = _instagram_from_text(raw_copy)
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="instagram",
            instagram_content=ig,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )
    seo = content_brief.seo_keyword or "saas workflow"
    blog = _blog_from_text(raw_copy, seo)
    return FormattedContent(
        run_id=run_id,
        org_id=org_id,
        created_at=utc_now_iso(),
        platform="blog",
        blog_content=blog,
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )


def run(
    raw_copy: str,
    content_brief: ContentBrief,
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    revision_hint: str | None = None,
    retry_count: int = 0,
) -> FormattedContent:
    _ = brand_profile
    platform = content_brief.platform
    run_id = strategy_brief.run_id
    org_id = strategy_brief.org_id

    if settings.MOCK_MODE:
        return _mock_formatted(raw_copy, content_brief, strategy_brief, retry_count, revision_hint)

    rules = _load_platform_rules().get(platform, {})
    spec = load_prompt("formatter_v1")
    user_msg = (
        f"Platform: {platform}\n\n"
        f"Rules to enforce mechanically:\n{json.dumps(rules, indent=2)}\n\n"
        f"Raw copy to format:\n{raw_copy}\n\n"
        f"{f'Revision instruction: {revision_hint}' if revision_hint else ''}\n\n"
        "Apply the platform rules exactly. Return the formatted copy only.\n"
        "No JSON. No explanation."
    )
    formatted_text = chat_completion(
        [
            {"role": "system", "content": spec.system_prompt},
            {"role": "user", "content": user_msg},
        ]
    ).strip()

    if platform == "linkedin":
        li = _linkedin_from_text(formatted_text)
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="linkedin",
            linkedin_content=li,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )
    if platform == "twitter":
        tw = _twitter_from_text(formatted_text)
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="twitter",
            twitter_content=tw,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )
    if platform == "instagram":
        ig = _instagram_from_text(formatted_text)
        return FormattedContent(
            run_id=run_id,
            org_id=org_id,
            created_at=utc_now_iso(),
            platform="instagram",
            instagram_content=ig,
            retry_count=retry_count,
            revision_hint_applied=revision_hint,
        )
    seo = content_brief.seo_keyword or "saas"
    blog = _blog_from_text(formatted_text, seo)
    return FormattedContent(
        run_id=run_id,
        org_id=org_id,
        created_at=utc_now_iso(),
        platform="blog",
        blog_content=blog,
        retry_count=retry_count,
        revision_hint_applied=revision_hint,
    )
