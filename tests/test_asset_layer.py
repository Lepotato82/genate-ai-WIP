"""
tests/test_asset_layer.py
Unit tests for agents/asset_layer.py — deterministic decoration picker.

All tests are offline and require no API keys.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from agents import asset_layer


def _write_png(path: Path, color: tuple[int, int, int, int]) -> None:
    """Create a minimal RGBA PNG so byte content differs per file."""
    img = Image.new("RGBA", (10, 10), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())


def _seed_assets(
    tmp_path: Path, category: str, colors: list[tuple[int, int, int, int]]
) -> Path:
    """Create a fake category dir with N PNGs and point asset_layer at it."""
    cat_dir = tmp_path / category
    cat_dir.mkdir(parents=True)
    for i, color in enumerate(colors):
        _write_png(cat_dir / f"asset_{i:02d}.png", color)
    return cat_dir


def _install_tmp_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(asset_layer, "_DECORATIONS_DIR", tmp_path)
    asset_layer._list_category_assets.cache_clear()


def test_fetch_pack_returns_bytes_for_each_slide(monkeypatch, tmp_path):
    _seed_assets(
        tmp_path, "consumer-friendly",
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)],
    )
    _install_tmp_dir(monkeypatch, tmp_path)

    pack = asset_layer.fetch_pack("consumer-friendly", "run-abc123xyz", 5)

    assert len(pack) == 5
    assert all(item is not None for item in pack)
    assert all(isinstance(item, bytes) for item in pack)
    for item in pack:
        # Confirm each item is a decodable PNG
        Image.open(io.BytesIO(item)).verify()


def test_fetch_pack_is_deterministic(monkeypatch, tmp_path):
    _seed_assets(
        tmp_path, "consumer-friendly",
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)],
    )
    _install_tmp_dir(monkeypatch, tmp_path)

    pack_a = asset_layer.fetch_pack("consumer-friendly", "run-abc123xyz", 6)
    pack_b = asset_layer.fetch_pack("consumer-friendly", "run-abc123xyz", 6)

    assert pack_a == pack_b


def test_fetch_pack_varies_with_run_id(monkeypatch, tmp_path):
    _seed_assets(
        tmp_path, "consumer-friendly",
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)],
    )
    _install_tmp_dir(monkeypatch, tmp_path)

    pack_a = asset_layer.fetch_pack("consumer-friendly", "run-aaaaaaaa", 6)
    pack_b = asset_layer.fetch_pack("consumer-friendly", "run-bbbbbbbb", 6)

    # Different run_ids should not all pick the same asset across all slides.
    # With 4 assets and 6 slides the chance of a full match is 1/4^6 ≈ 0.02%.
    assert pack_a != pack_b


def test_fetch_pack_rotates_across_slides(monkeypatch, tmp_path):
    _seed_assets(
        tmp_path, "consumer-friendly",
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)],
    )
    _install_tmp_dir(monkeypatch, tmp_path)

    pack = asset_layer.fetch_pack("consumer-friendly", "run-varied-id", 6)
    distinct = {bytes(item) for item in pack if item is not None}
    # 6 slides with 3 assets should almost always hit ≥2 distinct picks.
    assert len(distinct) >= 2


def test_fetch_pack_missing_category_returns_nones(monkeypatch, tmp_path):
    _install_tmp_dir(monkeypatch, tmp_path)

    pack = asset_layer.fetch_pack("nonexistent-category", "run-abc", 3)

    assert pack == [None, None, None]


def test_fetch_pack_empty_category_returns_nones(monkeypatch, tmp_path):
    (tmp_path / "consumer-friendly").mkdir()  # exists but no files
    _install_tmp_dir(monkeypatch, tmp_path)

    pack = asset_layer.fetch_pack("consumer-friendly", "run-abc", 3)

    assert pack == [None, None, None]


def test_fetch_pack_zero_slides_returns_empty(monkeypatch, tmp_path):
    _install_tmp_dir(monkeypatch, tmp_path)

    assert asset_layer.fetch_pack("consumer-friendly", "run-abc", 0) == []


def test_list_category_assets_caches_result(monkeypatch, tmp_path):
    _seed_assets(tmp_path, "consumer-friendly", [(255, 0, 0, 255)])
    _install_tmp_dir(monkeypatch, tmp_path)

    first = asset_layer._list_category_assets("consumer-friendly")
    # Add a new file after the first call — cached result should not pick it up
    _write_png(tmp_path / "consumer-friendly" / "asset_99.png", (0, 255, 0, 255))
    second = asset_layer._list_category_assets("consumer-friendly")

    assert first == second
    assert len(first) == 1
