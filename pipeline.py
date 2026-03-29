from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter
from typing import Generator, Literal, cast

from agents import (
    copywriter,
    evaluator,
    formatter,
    image_gen,
    input_processor,
    planner,
    product_analysis,
    strategy,
    ui_analyzer,
)
from config import settings
from knowledge import persist_run, query_context
from schemas.brand_identity import BrandIdentity, _to_hex
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.evaluator_output import EvaluatorOutput
from schemas.formatted_content import FormattedContent
from schemas.input_package import InputPackage
from schemas.knowledge_context import KnowledgeContext
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief

MAX_EVAL_RETRIES = 2

PlatformName = Literal["linkedin", "twitter", "instagram", "blog"]


def _norm_platform(platform: str) -> PlatformName:
    p = platform.lower().strip()
    if p == "x":
        return "twitter"
    if p in ("linkedin", "twitter", "instagram", "blog"):
        return cast(PlatformName, p)
    return "linkedin"


@dataclass
class RunArtifacts:
    run_id: str
    org_id: str | None
    brand_profile: BrandProfile
    product_knowledge: ProductKnowledge
    content_brief: ContentBrief
    strategy_brief: StrategyBrief
    raw_copy: str
    formatted_content: FormattedContent
    evaluator_output: EvaluatorOutput
    images: dict | None = None


RUN_REGISTRY: dict[str, RunArtifacts] = {}


def _event(step: int, agent: str, status: str, started: float, message: str) -> dict:
    return {
        "step": step,
        "agent": agent,
        "status": status,
        "elapsed": round(perf_counter() - started, 3),
        "message": message,
    }


def build_brand_identity(
    pkg: InputPackage,
    brand: BrandProfile,
    product: ProductKnowledge,
) -> BrandIdentity:
    """
    Assemble BrandIdentity from Input Processor + UI Analyzer outputs.
    Deterministic — no LLM, no network calls.
    """
    # Extract mono font from raw css_tokens if present
    mono_font = None
    if pkg.css_tokens:
        for key, val in pkg.css_tokens.items():
            if "mono" in key.lower() and isinstance(val, str):
                mono_font = val.split(",")[0].strip().strip("\"'")
                break

    return BrandIdentity(
        product_name=product.product_name or "Unknown",
        product_url=str(pkg.url),
        run_id=pkg.run_id,
        logo_bytes=pkg.logo_bytes,
        logo_url=pkg.logo_url,
        logo_confidence=pkg.logo_confidence,
        og_image_url=getattr(pkg, "og_image_url", None),
        og_image_bytes=None,
        primary_color=_to_hex(brand.primary_color) or "#000000",
        secondary_color=_to_hex(brand.secondary_color),
        accent_color=None,
        background_color=_to_hex(brand.background_color) or "#ffffff",
        foreground_color=None,
        font_family_heading=brand.font_family,
        font_family_body=brand.font_family,
        font_family_mono=mono_font,
        font_weights=brand.font_weights or [],
        border_radius=brand.border_radius,
        spacing_unit=brand.spacing_unit,
        design_category=brand.design_category,
        tone=brand.tone,
        writing_instruction=brand.writing_instruction,
    )


def _run_stages_after_input(
    *,
    run_id: str,
    org_id: str | None,
    pkg: InputPackage,
    platform: str,
    started: float,
) -> tuple[
    BrandProfile,
    ProductKnowledge,
    BrandIdentity,
    ContentBrief,
    StrategyBrief,
    str,
    FormattedContent,
    EvaluatorOutput,
]:
    plat = _norm_platform(platform)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_ui = pool.submit(ui_analyzer.run, pkg)
        f_pa = pool.submit(product_analysis.run, pkg)
        brand = f_ui.result()
        product = f_pa.result()

    brand_identity = build_brand_identity(pkg, brand, product)

    knowledge_context: KnowledgeContext | None = None
    if settings.KNOWLEDGE_LAYER_ENABLED and org_id:
        query_text = f"{product.product_name}: {product.tagline or ''}"
        knowledge_context = query_context(org_id=org_id, query_text=query_text)
    _ = knowledge_context

    content_brief = planner.run(brand, product, plat)
    strategy_brief = strategy.run(content_brief, product, brand)
    raw_copy = copywriter.run(strategy_brief, content_brief, brand)

    formatted = formatter.run(
        raw_copy,
        content_brief,
        strategy_brief,
        brand,
        revision_hint=None,
        retry_count=0,
        product_knowledge=product,
    )
    retry = 0
    evaluated = evaluator.run(formatted, strategy_brief, brand, retry_count=retry)
    while not evaluated.passes and retry < MAX_EVAL_RETRIES:
        retry += 1
        formatted = formatter.run(
            raw_copy,
            content_brief,
            strategy_brief,
            brand,
            revision_hint=evaluated.revision_hint,
            retry_count=retry,
            product_knowledge=product,
        )
        evaluated = evaluator.run(formatted, strategy_brief, brand, retry_count=retry)

    return brand, product, brand_identity, content_brief, strategy_brief, raw_copy, formatted, evaluated


def run_pipeline(
    url: str,
    platform: str = "linkedin",
    user_image: bytes | None = None,
    user_document: str | None = None,
) -> dict:
    """
    End-to-end pipeline: input → brand + product (parallel) → planner → strategy →
    copywriter → formatter → evaluator (with formatter retries).
    """
    run_id = str(uuid.uuid4())
    started = perf_counter()
    pkg = input_processor.run(
        url=url,
        run_id=run_id,
        org_id=None,
        user_image=user_image,
        user_document=user_document,
    )
    brand, product, brand_identity, content_brief, strategy_brief, raw_copy, formatted, evaluated = _run_stages_after_input(
        run_id=run_id,
        org_id=None,
        pkg=pkg,
        platform=platform,
        started=started,
    )
    images = image_gen.run(formatted, brand_identity)
    artifacts = RunArtifacts(
        run_id=run_id,
        org_id=None,
        brand_profile=brand,
        product_knowledge=product,
        content_brief=content_brief,
        strategy_brief=strategy_brief,
        raw_copy=raw_copy,
        formatted_content=formatted,
        evaluator_output=evaluated,
        images=images,
    )
    RUN_REGISTRY[run_id] = artifacts
    return {
        "run_id": run_id,
        "url": url,
        "platform": platform,
        "brand_profile": brand.model_dump(),
        "brand_identity": brand_identity.model_dump(exclude={"logo_bytes", "og_image_bytes"}),
        "product_knowledge": product.model_dump(),
        "content_brief": content_brief.model_dump(),
        "strategy_brief": strategy_brief.model_dump(),
        "raw_copy": raw_copy,
        "formatted_content": formatted.model_dump(),
        "evaluator_output": evaluated.model_dump(),
        "passes": evaluated.passes,
        "overall_score": evaluated.overall_score,
        "images": images,
    }


def run_pipeline_artifacts(
    *,
    url: str,
    platform: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
    user_document_filename: str | None = None,
) -> RunArtifacts:
    events = list(
        run_stream(
            url=url,
            platform=platform,
            org_id=org_id,
            user_image=user_image,
            user_document=user_document,
            user_document_filename=user_document_filename,
        )
    )
    final = events[-1]
    if final["agent"] != "pipeline" or final["status"] != "complete":
        raise RuntimeError("Pipeline did not complete")
    run_id = final["run_id"]
    return RUN_REGISTRY[run_id]


# ---------------------------------------------------------------------------
# run_stream — SSE generator, full pipeline with knowledge layer
# ---------------------------------------------------------------------------

def run_stream(
    *,
    url: str,
    platform: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
    user_document_filename: str | None = None,
) -> Generator[dict, None, None]:
    run_id = str(uuid.uuid4())
    started = perf_counter()

    # Step 1 — Input Processor
    yield _event(1, "input_processor", "start", started, "Collecting inputs")
    input_pkg = input_processor.run(
        url=url,
        run_id=run_id,
        org_id=org_id,
        user_image=user_image,
        user_document=user_document,
        user_document_filename=user_document_filename,
    )
    yield _event(1, "input_processor", "complete", started, "Input package ready")

    # Steps 2+3 — UI Analyzer + Product Analysis (parallel)
    yield _event(2, "ui_analyzer", "start", started, "Analyzing brand visuals")
    yield _event(3, "product_analysis", "start", started, "Analyzing product text")
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_ui = pool.submit(ui_analyzer.run, input_pkg)
        f_pa = pool.submit(product_analysis.run, input_pkg)
        brand = f_ui.result()
        product = f_pa.result()
    yield _event(2, "ui_analyzer", "complete", started, "Brand profile extracted")
    yield _event(3, "product_analysis", "complete", started, "Product knowledge extracted")

    brand_identity = build_brand_identity(input_pkg, brand, product)

    # Step K — Knowledge Layer query (optional)
    knowledge_context: KnowledgeContext | None = None
    if settings.KNOWLEDGE_LAYER_ENABLED and org_id:
        yield _event(0, "knowledge_query", "start", started, "Querying memory")
        query_text = f"{product.product_name}: {product.tagline or ''}"
        knowledge_context = query_context(org_id=org_id, query_text=query_text)
        yield _event(0, "knowledge_query", "complete", started, "Memory query complete")
    _ = knowledge_context

    # Step 4 — Planner
    yield _event(4, "planner", "start", started, "Planning content")
    content_brief = planner.run(brand, product, _norm_platform(platform))
    yield _event(4, "planner", "complete", started, "Content brief created")

    # Step 5 — Strategy
    yield _event(5, "strategy", "start", started, "Building strategy")
    strategy_brief = strategy.run(content_brief, product, brand)
    yield _event(5, "strategy", "complete", started, "Strategy brief created")

    # Steps 6+7 — Copywriter + Visual Gen (parallel)
    yield _event(6, "copywriting", "start", started, "Generating raw copy")
    raw_copy = copywriter.run(strategy_brief, content_brief, brand)
    yield _event(6, "copywriting", "complete", started, "Raw copy generated")

    yield _event(8, "formatter", "start", started, "Applying platform formatting")
    formatted = formatter.run(
        raw_copy,
        content_brief,
        strategy_brief,
        brand,
        revision_hint=None,
        retry_count=0,
        product_knowledge=product,
    )
    yield _event(8, "formatter", "complete", started, "Formatting complete")

    # Phase 2 — Image generation
    images = image_gen.run(formatted, brand_identity)
    if images.get("generation_enabled"):
        yield _event(7, "image_gen", "complete", started,
                     f"Generated {len(images['image_urls'])} slides")

    # Steps 8+9 — Formatter → Evaluator with retry loop
    retry = 0
    yield _event(9, "evaluator", "start", started, "Evaluating quality gate")
    evaluated = evaluator.run(formatted, strategy_brief, brand, retry_count=retry)
    yield _event(9, "evaluator", "complete", started, f"Evaluation pass={evaluated.passes}")

    while not evaluated.passes and retry < MAX_EVAL_RETRIES:
        retry += 1
        yield _event(8, "formatter", "start", started, "Applying revision")
        formatted = formatter.run(
            raw_copy,
            content_brief,
            strategy_brief,
            brand,
            revision_hint=evaluated.revision_hint,
            retry_count=retry,
            product_knowledge=product,
        )
        yield _event(8, "formatter", "complete", started, "Formatting complete")
        yield _event(9, "evaluator", "start", started, "Re-evaluating")
        evaluated = evaluator.run(formatted, strategy_brief, brand, retry_count=retry)
        yield _event(9, "evaluator", "complete", started, f"Evaluation pass={evaluated.passes}")

    artifacts = RunArtifacts(
        run_id=run_id,
        org_id=org_id,
        brand_profile=brand,
        product_knowledge=product,
        content_brief=content_brief,
        strategy_brief=strategy_brief,
        raw_copy=raw_copy,
        formatted_content=formatted,
        evaluator_output=evaluated,
        images=images,
    )
    RUN_REGISTRY[run_id] = artifacts

    # Step K (post) — Knowledge Layer persist
    if evaluated.passes and settings.KNOWLEDGE_LAYER_ENABLED and org_id:
        yield _event(0, "knowledge_persist", "start", started, "Persisting approved memory")
        persist_run(
            org_id=org_id,
            brand_profile=brand,
            product_knowledge=product,
            strategy_brief=strategy_brief,
            approved_copy=_approved_copy(formatted),
        )
        yield _event(0, "knowledge_persist", "complete", started, "Memory persisted")

    done = _event(10, "pipeline", "complete", started, "Pipeline complete")
    done["run_id"] = run_id
    done["passes"] = evaluated.passes
    yield done


def _run_entry(
    url: str,
    platform: str,
    run_id: str | None,
    org_id: str | None,
) -> dict:
    """Sequential pipeline for CLI / validation (no visual gen, no SSE)."""
    max_retries = 2
    rid = run_id or str(uuid.uuid4())
    plat = _norm_platform(platform)

    pkg = input_processor.run(url=url, run_id=rid, org_id=org_id)
    brand = ui_analyzer.run(pkg)
    product = product_analysis.run(pkg)
    brand_identity = build_brand_identity(pkg, brand, product)
    brief = planner.run(brand, product, platform=plat)
    strategy_brief = strategy.run(brief, product, brand)
    raw_copy = copywriter.run(strategy_brief, brief, brand)
    formatted = formatter.run(
        raw_copy,
        brief,
        strategy_brief,
        brand,
        revision_hint=None,
        retry_count=0,
        product_knowledge=product,
    )

    # Phase 2 — Image generation (runs on first formatted output, before retry loop)
    images = image_gen.run(formatted, brand_identity)

    for attempt in range(max_retries + 1):
        evaluation = evaluator.run(formatted, strategy_brief, brand, retry_count=attempt)
        if evaluation.passes or attempt == max_retries:
            break
        formatted = formatter.run(
            raw_copy,
            brief,
            strategy_brief,
            brand,
            revision_hint=evaluation.revision_hint,
            retry_count=attempt + 1,
            product_knowledge=product,
        )

    return {
        "run_id": rid,
        "url": url,
        "brand_profile": brand.model_dump(),
        "brand_identity": brand_identity.model_dump(exclude={"logo_bytes", "og_image_bytes"}),
        "product_knowledge": product.model_dump(),
        "content_brief": brief.model_dump(),
        "strategy_brief": strategy_brief.model_dump(),
        "formatted_content": formatted.model_dump(),
        "evaluation": evaluation.model_dump(),
        "passes": evaluation.passes,
        "overall_score": evaluation.overall_score,
        "images": images,
    }


def run_linkedin(
    url: str,
    run_id: str | None = None,
    org_id: str | None = None,
) -> dict:
    return _run_entry(url, "linkedin", run_id, org_id)


def run_twitter(
    url: str,
    run_id: str | None = None,
    org_id: str | None = None,
) -> dict:
    return _run_entry(url, "twitter", run_id, org_id)


def run_instagram(
    url: str,
    run_id: str | None = None,
    org_id: str | None = None,
) -> dict:
    return _run_entry(url, "instagram", run_id, org_id)


def run(
    url: str,
    platform: str = "linkedin",
    run_id: str | None = None,
    org_id: str | None = None,
) -> dict:
    p = platform.lower().strip()
    dispatch = {
        "linkedin": run_linkedin,
        "twitter": run_twitter,
        "x": run_twitter,
        "instagram": run_instagram,
    }
    if p not in dispatch:
        raise ValueError(
            f"Unsupported platform: {platform!r}. Valid: {list(dispatch.keys())}"
        )
    return dispatch[p](url, run_id=run_id, org_id=org_id)


def _approved_copy(formatted: FormattedContent) -> str:
    if formatted.user_edited_copy:
        return formatted.user_edited_copy
    if formatted.linkedin_content:
        return formatted.linkedin_content.full_post
    if formatted.twitter_content:
        return "\n\n".join(formatted.twitter_content.tweets)
    if formatted.instagram_content:
        return formatted.instagram_content.full_caption
    if formatted.blog_content:
        return formatted.blog_content.body
    return ""


def approve_run(run_id: str, edited_copy: str | None = None) -> dict:
    if run_id not in RUN_REGISTRY:
        raise KeyError(f"Unknown run_id: {run_id}")
    artifacts = RUN_REGISTRY[run_id]
    if edited_copy:
        artifacts.formatted_content.user_edited_copy = edited_copy
        artifacts.formatted_content.approved = True
    if settings.KNOWLEDGE_LAYER_ENABLED and artifacts.org_id:
        persist_run(
            org_id=artifacts.org_id,
            brand_profile=artifacts.brand_profile,
            product_knowledge=artifacts.product_knowledge,
            strategy_brief=artifacts.strategy_brief,
            approved_copy=edited_copy or _approved_copy(artifacts.formatted_content),
        )
    return {"run_id": run_id, "approved": True}
