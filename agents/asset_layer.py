"""
Decorative asset layer — deterministic picker over bundled PNG decorations.

Consumed by: compositor.run() to pre-fetch a per-slide decoration pack before
the slide loop. Zero network calls; all assets ship under assets/decorations/.
"""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DECORATIONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "decorations"


@lru_cache(maxsize=8)
def _list_category_assets(category: str) -> tuple[Path, ...]:
    """Return sorted tuple of PNG paths for a category, or () if none exist."""
    cat_dir = _DECORATIONS_DIR / category
    if not cat_dir.is_dir():
        return ()
    pngs = sorted(p for p in cat_dir.glob("*.png") if p.is_file())
    return tuple(pngs)


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError as exc:
        logger.warning("[asset_layer] failed to read %s: %s", path, exc)
        return None


def fetch_pack(
    design_category: str,
    run_id: str,
    slide_count: int,
) -> list[bytes | None]:
    """
    Return a deterministic list of ``slide_count`` decoration PNG byte-blobs
    (or ``None`` per slide when no asset is chosen for that slide).

    Selection is seeded by ``(run_id[:8] + design_category + slide_index)``,
    so the same run always produces the same visual outcome, and different
    runs rotate through the available assets.
    """
    if slide_count <= 0:
        return []
    assets = _list_category_assets(design_category)
    if not assets:
        return [None] * slide_count

    pack: list[bytes | None] = []
    for i in range(slide_count):
        seed = (run_id[:8] + design_category + str(i)).encode()
        idx = int(hashlib.md5(seed).hexdigest(), 16) % len(assets)
        pack.append(_read_bytes(assets[idx]))
    return pack
