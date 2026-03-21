"""
Step 6: Copywriting Agent.

Writes raw marketing copy executing the StrategyBrief. The
BrandProfile.writing_instruction is injected verbatim as the first line of
the system prompt. Returns plain text — no JSON. The Formatter applies
platform-structural rules in the next step.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from prompts.loader import load_prompt
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief


# ---------------------------------------------------------------------------
# Mock — hardcoded realistic LinkedIn carousel copy using Linear as example
# ---------------------------------------------------------------------------

_MOCK_LINKEDIN_COPY = """\
Most engineering teams don't have a project management problem.
They have a status meeting problem.

Every Monday: 45 minutes to answer "what are you working on?"

Slide 1: The status meeting tax
Your team spends 3+ hours a week in ceremonies that exist only to answer
one question: what's the current state of each ticket?

Slide 2: The cost compounds
3 hours a week is 150 hours a year. That's nearly a full month of
engineering time spent on status — not shipping.

Slide 3: What automatic state means
When issue state moves with code activity, the standup becomes optional.
Push a branch — the issue moves to In Progress. Merge the PR — it closes.

Slide 4: The mechanism
Linear reads your Git activity and updates ticket state automatically.
No manual updates. No context switching. No ceremony.

Slide 5: Who stopped running standups
Vercel, Raycast, and Mercury don't run status meetings.
Their code runs the standup.

Slide 6: The before and after
Before: 45-minute Monday standup to move tickets manually.
After: tickets move when code moves. Meeting cancelled.

Slide 7: What this unlocks
Engineers stay in flow. PMs have real-time state without asking.
Stakeholders see progress without attending a ceremony.

Slide 8: Linear is free to start
Your next sprint planning is in 3 days.
Start before then — and cancel that meeting.

#engineeringmanagement #softwaredevelopment #productivity"""


def _mock_copy(
    strategy_brief: StrategyBrief,
    content_brief: ContentBrief,
) -> str:
    if content_brief.platform == "twitter":
        return (
            "1/ Your team is spending too long converting product truth into social copy.\n\n"
            "2/ The result is delayed launches and weak hooks.\n\n"
            "3/ Genate structures strategy first, then generates grounded messaging.\n\n"
            f"4/ Proof: {strategy_brief.proof_point}\n\n"
            "5/ Read more and adapt this workflow for your next campaign. #saas"
        )
    # Default: linkedin carousel copy for Linear
    return _MOCK_LINKEDIN_COPY


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    strategy_brief: StrategyBrief,
    content_brief: ContentBrief,
    brand_profile: BrandProfile,
) -> str:
    if settings.MOCK_MODE:
        return _mock_copy(strategy_brief, content_brief)

    # Load prompt from YAML if it exists, otherwise fall back to inline
    try:
        prompt = load_prompt("copywriting_v1")
        base_system = prompt.system_prompt
    except FileNotFoundError:
        base_system = (
            "You are a SaaS copywriting agent. Write platform-native marketing copy "
            "that executes the given strategy exactly. Return ONLY the raw copy text — "
            "no labels, no markdown, no explanation."
        )

    # Inject writing_instruction as FIRST line of system prompt (non-negotiable)
    system_prompt = (
        f"Brand voice instruction (follow exactly): {brand_profile.writing_instruction}\n\n"
        + base_system
    )

    # Build user message
    slide_hint = ""
    if content_brief.content_type == "carousel" and content_brief.slide_count_target:
        slide_hint = (
            f"\nslide_count_target: {content_brief.slide_count_target} "
            "(write a distinct slide heading + 2-3 lines per slide)"
        )

    user_msg = (
        f"platform: {content_brief.platform}\n"
        f"narrative_arc: {strategy_brief.narrative_arc}\n"
        f"lead_pain_point: {strategy_brief.lead_pain_point}\n"
        f"primary_claim: {strategy_brief.primary_claim}\n"
        f"proof_point: {strategy_brief.proof_point}\n"
        f"cta_intent: {strategy_brief.cta_intent}\n"
        f"hook_direction: {strategy_brief.hook_direction}"
        + slide_hint
    )

    return chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
    ).strip()
