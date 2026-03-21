"""
Step 6: Copywriting — backwards-compatible entry; delegates to copywriter.
"""

from __future__ import annotations

from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief
from . import copywriter


def run(content_brief: ContentBrief, strategy_brief: StrategyBrief, brand_profile: BrandProfile) -> str:
    return copywriter.run(strategy_brief, content_brief, brand_profile)
