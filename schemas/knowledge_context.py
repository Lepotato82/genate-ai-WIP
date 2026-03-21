"""
Knowledge context retrieved before planning when memory is enabled.
"""

from pydantic import BaseModel, Field


class KnowledgeContext(BaseModel):
    org_id: str
    strategy_summaries: list[str] = Field(default_factory=list)
    approved_copy_examples: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)

    @property
    def has_context(self) -> bool:
        return bool(
            self.strategy_summaries or self.approved_copy_examples or self.proof_points
        )
