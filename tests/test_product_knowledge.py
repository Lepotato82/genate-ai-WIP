from schemas.product_knowledge import ProductKnowledge


def test_product_knowledge_minimal_valid():
    model = ProductKnowledge(
        run_id="run-1",
        org_id=None,
        created_at="2026-03-21T00:00:00Z",
        product_name="Genate",
        product_url="https://genate.ai",
        tagline="Built for SaaS",
        description=(
            "Genate helps SaaS marketing teams convert product truth into platform "
            "content quickly while preserving brand voice and proof-point grounding "
            "through a structured multi-agent workflow and quality gates across "
            "teams, campaigns, and multiple channels."
        ),
        product_category="marketing-content",
        features=[
            {"name": "Structured planning", "description": "Creates strategy-first briefs"},
            {"name": "Formatter rules", "description": "Applies deterministic platform structure"},
        ],
        benefits=["Faster output", "More consistent voice"],
        proof_points=[
            {
                "text": "Used by over 10,000 engineering teams.",
                "proof_type": "user_count",
                "source": "scraped_page",
            }
        ],
        pain_points=["Slow content iteration", "Inconsistent messaging"],
        messaging_angles=["Strategy first"],
    )
    assert model.product_name == "Genate"


def test_product_knowledge_proof_point_too_short_rejected():
    try:
        ProductKnowledge(
            run_id="run-1",
            org_id=None,
            created_at="2026-03-21T00:00:00Z",
            product_name="Genate",
            product_url="https://genate.ai",
            description=(
                "Genate helps SaaS marketing teams convert product truth into platform "
                "content quickly while preserving brand voice and proof-point grounding "
                "through a structured multi-agent workflow and quality gates."
            ),
            product_category="marketing-content",
            features=[
                {"name": "A", "description": "B"},
                {"name": "C", "description": "D"},
            ],
            benefits=["Faster output", "More consistent voice"],
            proof_points=[{"text": "Too short", "proof_type": "stat", "source": "inferred"}],
            pain_points=["Slow content iteration", "Inconsistent messaging"],
            messaging_angles=["Strategy first"],
        )
    except Exception:
        assert True
        return
    raise AssertionError("Expected proof point validation error")
