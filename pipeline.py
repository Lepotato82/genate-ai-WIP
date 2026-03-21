from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter
from typing import Generator

from agents import (
    copywriting,
    evaluator,
    formatter,
    input_processor,
    planner,
    product_analysis,
    strategy,
    ui_analyzer,
    visual_gen,
)
from config import settings
from knowledge import persist_run, query_context
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.evaluator_output import EvaluatorOutput
from schemas.formatted_content import FormattedContent
from schemas.knowledge_context import KnowledgeContext
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief

MAX_EVAL_RETRIES = 2


@dataclass
class RunArtifacts:
    run_id: str
    org_id: str | None
    brand_profile: BrandProfile
    product_knowledge: ProductKnowledge
    content_brief: ContentBrief
    strategy_brief: StrategyBrief
    formatted_content: FormattedContent
    evaluator_output: EvaluatorOutput


RUN_REGISTRY: dict[str, RunArtifacts] = {}


def _event(step: int, agent: str, status: str, started: float, message: str) -> dict:
    return {
        "step": step,
        "agent": agent,
        "status": status,
        "elapsed": round(perf_counter() - started, 3),
        "message": message,
    }


def run_pipeline(
    *,
    url: str,
    platform: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
) -> RunArtifacts:
    events = list(
        run_stream(
            url=url,
            platform=platform,
            org_id=org_id,
            user_image=user_image,
            user_document=user_document,
        )
    )
    final = events[-1]
    if final["agent"] != "pipeline" or final["status"] != "complete":
        raise RuntimeError("Pipeline did not complete")
    run_id = final["run_id"]
    return RUN_REGISTRY[run_id]


def run_stream(
    *,
    url: str,
    platform: str,
    org_id: str | None = None,
    user_image: bytes | None = None,
    user_document: str | None = None,
) -> Generator[dict, None, None]:
    run_id = str(uuid.uuid4())
    started = perf_counter()

    yield _event(1, "input_processor", "start", started, "Collecting inputs")
    input_pkg = input_processor.run(
        url=url,
        run_id=run_id,
        org_id=org_id,
        user_image=user_image,
        user_document=user_document,
    )
    yield _event(1, "input_processor", "complete", started, "Input package ready")

    yield _event(2, "ui_analyzer", "start", started, "Analyzing brand visuals")
    yield _event(3, "product_analysis", "start", started, "Analyzing product text")
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_ui = pool.submit(ui_analyzer.run, input_pkg)
        f_pa = pool.submit(product_analysis.run, input_pkg)
        brand = f_ui.result()
        product = f_pa.result()
    yield _event(2, "ui_analyzer", "complete", started, "Brand profile extracted")
    yield _event(3, "product_analysis", "complete", started, "Product knowledge extracted")

    knowledge_context: KnowledgeContext | None = None
    if settings.KNOWLEDGE_LAYER_ENABLED and org_id:
        yield _event(0, "knowledge_query", "start", started, "Querying memory")
        query_text = f"{product.product_name}: {product.tagline or ''}"
        knowledge_context = query_context(org_id=org_id, query_text=query_text)
        yield _event(0, "knowledge_query", "complete", started, "Memory query complete")

    yield _event(4, "planner", "start", started, "Planning content")
    content_brief = planner.run(platform=platform, product_knowledge=product, knowledge_context=knowledge_context)
    yield _event(4, "planner", "complete", started, "Content brief created")

    yield _event(5, "strategy", "start", started, "Building strategy")
    strategy_brief = strategy.run(content_brief=content_brief, product_knowledge=product, knowledge_context=knowledge_context)
    yield _event(5, "strategy", "complete", started, "Strategy brief created")

    yield _event(6, "copywriting", "start", started, "Generating raw copy")
    yield _event(7, "visual_gen", "start", started, "Generating visual directions")
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_copy = pool.submit(copywriting.run, content_brief, strategy_brief, brand)
        f_visual = pool.submit(visual_gen.run, brand, content_brief, strategy_brief)
        raw_copy = f_copy.result()
        visual_payload = f_visual.result()
    yield _event(6, "copywriting", "complete", started, "Raw copy generated")
    yield _event(7, "visual_gen", "complete", started, "Visual payload generated")

    retry = 0
    revision_hint: str | None = None
    formatted: FormattedContent | None = None
    evaluated: EvaluatorOutput | None = None
    while True:
        yield _event(8, "formatter", "start", started, "Applying platform formatting")
        formatted = formatter.run(
            content_brief=content_brief,
            strategy_brief=strategy_brief,
            raw_copy=raw_copy,
            visual_payload=visual_payload,
            retry_count=retry,
            revision_hint=revision_hint,
        )
        yield _event(8, "formatter", "complete", started, "Formatting complete")

        yield _event(9, "evaluator", "start", started, "Evaluating quality gate")
        evaluated = evaluator.run(formatted, strategy_brief, brand)
        yield _event(9, "evaluator", "complete", started, f"Evaluation pass={evaluated.passes}")
        if evaluated.passes:
            break
        if retry >= MAX_EVAL_RETRIES:
            break
        retry += 1
        revision_hint = evaluated.revision_hint

    assert formatted is not None and evaluated is not None
    artifacts = RunArtifacts(
        run_id=run_id,
        org_id=org_id,
        brand_profile=brand,
        product_knowledge=product,
        content_brief=content_brief,
        strategy_brief=strategy_brief,
        formatted_content=formatted,
        evaluator_output=evaluated,
    )
    RUN_REGISTRY[run_id] = artifacts

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
