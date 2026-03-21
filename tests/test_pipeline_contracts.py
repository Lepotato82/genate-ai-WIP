from agents.formatter import run as format_run
from prompts.loader import load_prompt
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief


def _content_brief(platform: str = "linkedin") -> ContentBrief:
    return ContentBrief(
        run_id="run-1",
        org_id=None,
        created_at="2026-03-21T00:00:00Z",
        platform=platform,  # type: ignore[arg-type]
        content_type="thread" if platform == "twitter" else "text_post",  # type: ignore[arg-type]
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="product_and_solution",
        funnel_stage="mofu",
        posting_strategy={
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday"],
            "best_time_window": "10:00-12:00 IST",
        },
        thread_length_target=4 if platform == "twitter" else None,
        platform_rules_summary=["Rule A", "Rule B"],
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="Benchmark source",
    )


def test_prompt_loader_reads_uploaded_prompts():
    cw = load_prompt("copywriting_v1")
    ev = load_prompt("evaluator_v1")
    assert cw.name == "copywriting_v1"
    assert ev.name == "evaluator_v1"


def test_strategy_proof_point_must_match_product_knowledge():
    pk = ProductKnowledge(
        run_id="run-1",
        org_id=None,
        created_at="2026-03-21T00:00:00Z",
        product_name="Genate",
        product_url="https://genate.ai",
        description=(
            "Genate helps SaaS teams build strategy-first content pipelines that stay "
            "aligned with product proof points and brand signals for better consistency "
            "across campaigns, formats, and recurring publishing cycles in fast "
            "moving growth organizations with strict brand requirements."
        ),
        product_category="marketing-content",
        features=[
            {"name": "Planner", "description": "Selects format and narrative arc"},
            {"name": "Evaluator", "description": "Scores quality with revision loop"},
        ],
        benefits=["Faster output", "Higher consistency"],
        proof_points=[{"text": "Used by over 10,000 engineering teams.", "proof_type": "user_count", "source": "scraped_page"}],
        pain_points=["Slow content iteration", "Weak message consistency"],
        messaging_angles=["Strategy first"],
    )
    brief = _content_brief()
    sb = StrategyBrief(
        run_id="run-1",
        org_id=None,
        created_at="2026-03-21T00:00:00Z",
        lead_pain_point="Teams spend hours turning product updates into content that still misses the core positioning.",
        primary_claim="Genate helps teams ship grounded content faster.",
        proof_point="Used by over 10,000 engineering teams.",
        proof_point_type="user_count",
        cta_intent="learn_more",
        appeal_type="rational",
        narrative_arc=brief.narrative_arc,
        target_icp_role="Growth lead",
        differentiator="Unlike generic generators, this workflow enforces strategy and proof-point grounding before formatting output.",
        hook_direction="Open with time-loss pain before introducing the workflow.",
        positioning_mode="category_creation",
        messaging_angle_used="Strategy first",
        knowledge_context_applied=False,
    )
    sb.validate_against_product_knowledge(pk)
    sb.validate_against_content_brief(brief)


def test_formatter_enforces_twitter_thread_shape():
    brief = _content_brief("twitter")
    strategy = StrategyBrief(
        run_id="run-1",
        org_id=None,
        created_at="2026-03-21T00:00:00Z",
        lead_pain_point="Teams spend hours rewriting content that repeatedly misses the positioning point.",
        primary_claim="Genate helps teams produce grounded content quickly.",
        proof_point="Used by over 10,000 engineering teams.",
        proof_point_type="user_count",
        cta_intent="learn_more",
        appeal_type="rational",
        narrative_arc="pain-agitate-solve-cta",
        target_icp_role="Growth lead",
        differentiator="Unlike generic tools, it enforces strategy-first workflow across every run.",
        hook_direction="Lead with friction and time loss.",
        positioning_mode="category_creation",
        messaging_angle_used="Strategy first",
        knowledge_context_applied=False,
    )
    out = format_run(
        content_brief=brief,
        strategy_brief=strategy,
            raw_copy=(
                "1/ Your team loses hours each week rewriting content that still misses positioning.\n\n"
                "2/ The cost is slower launches and weaker channel performance.\n\n"
                "3/ A strategy-first workflow maps pain, claim, and proof before drafting.\n\n"
                "4/ Start with one campaign and adapt the process across the quarter."
            ),
        visual_payload={"image_prompt": "x", "suggested_format": "carousel"},
    )
    assert out.twitter_content is not None
    assert 4 <= len(out.twitter_content.tweets) <= 8
