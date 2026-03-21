from schemas.brand_profile import BrandProfile


def test_brand_profile_accepts_required_fields():
    profile = BrandProfile(
        run_id="run-1",
        org_id="org-1",
        created_at="2026-03-21T00:00:00Z",
        design_category="developer-tool",
        primary_color="#5e6ad2",
        secondary_color="#7170ff",
        background_color="#ffffff",
        font_family="Inter",
        font_weights=[400.0, 510.0],
        border_radius="6px",
        spacing_unit="4px",
        tone="technical",
        writing_instruction=(
            "Use a direct technical SaaS voice, lead with concrete friction, and "
            "ground claims in specific product signals and proof."
        ),
        css_tokens={"--color-brand-bg": "#5e6ad2"},
        confidence=0.9,
    )
    assert profile.design_category == "developer-tool"


def test_brand_profile_writing_instruction_minimum_words():
    try:
        BrandProfile(
            run_id="run-1",
            org_id=None,
            created_at="2026-03-21T00:00:00Z",
            design_category="minimal-saas",
            primary_color="#5e6ad2",
            tone="minimal",
            writing_instruction="too short instruction for this schema",
            confidence=0.7,
        )
    except Exception:
        assert True
        return
    raise AssertionError("Expected validation failure for short instruction")
