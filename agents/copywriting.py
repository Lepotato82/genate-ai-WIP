"""
Step 6: Copywriting Agent (alias).

The canonical implementation lives in `copywriter.py` (used by the pipeline).
This module re-exports `run` for backwards compatibility.
"""

from agents.copywriter import run

__all__ = ["run"]
