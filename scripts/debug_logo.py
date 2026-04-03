"""
One-off logo extraction smoke test (real browser + optional local CLIP).

Usage (repo root):
  uv run python scripts/debug_logo.py https://linear.app
  uv run python scripts/debug_logo.py https://example.com -o logo_out.png

Requires MOCK_MODE=false in .env (this script forces real scrape).
LOGO_CLIP_ENABLED is read from settings / .env (default true).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import input_processor
from config import settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape one URL and print logo / CLIP diagnostics; optionally save PNG."
    )
    parser.add_argument("url", help="Page URL to scrape")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("logo_out.png"),
        help="Write logo PNG bytes here when present (default: ./logo_out.png)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logging for agents.input_processor (e.g. CLIP screenshot count)",
    )
    args = parser.parse_args()

    settings.MOCK_MODE = False
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
        logging.getLogger("agents.input_processor").setLevel(logging.DEBUG)

    pkg = input_processor.run(url=args.url, run_id=str(uuid4()))

    clip_used = bool(pkg.logo_url and "clip-header-nav-logo" in pkg.logo_url)
    print(f"scrape_error: {pkg.scrape_error!r}")
    print(f"LOGO_CLIP_ENABLED: {settings.LOGO_CLIP_ENABLED}")
    print(
        f"LOGO_CLIP_MIN_BOX_PX: {settings.LOGO_CLIP_MIN_BOX_PX} "
        f"LOGO_CLIP_MAX_BOX_W: {settings.LOGO_CLIP_MAX_BOX_W} "
        f"LOGO_CLIP_MAX_BOX_H: {settings.LOGO_CLIP_MAX_BOX_H}"
    )
    print(
        f"LOGO_OG_IMAGE_MAX_BYTES: {settings.LOGO_OG_IMAGE_MAX_BYTES} "
        f"LOGO_OG_IMAGE_MAX_EDGE_PX: {settings.LOGO_OG_IMAGE_MAX_EDGE_PX}"
    )
    print(f"logo_url: {pkg.logo_url!r}")
    print(f"logo_confidence: {pkg.logo_confidence!r}")
    print(f"logo_bytes_len: {len(pkg.logo_bytes or b'')}")
    print(f"clip_path_used: {clip_used}")

    if pkg.logo_bytes and pkg.logo_bytes.startswith(b"\x89PNG"):
        args.output.write_bytes(pkg.logo_bytes)
        print(f"wrote PNG: {args.output.resolve()}")
    elif pkg.logo_bytes:
        print("logo_bytes present but not PNG — not writing to file")
    else:
        print("no logo_bytes — skip write")


if __name__ == "__main__":
    main()
