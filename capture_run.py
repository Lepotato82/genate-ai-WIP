"""
Capture a full pipeline run to test_data/<filename>.json.

Usage:
    python capture_run.py https://example.com
    python capture_run.py https://example.com --platform instagram --content-type carousel
    python capture_run.py https://example.com --no-research   # skip Tavily (faster, offline)

Output file: test_data/pipeline_real_<host>_<timestamp>.json

Notes:
  - HERO_IMAGE_ENABLED is off by default (.env); compositor handles backgrounds locally.
  - RESEARCH_AUGMENTATION_ENABLED is on by default (.env); use --no-research to skip.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

# ── parse args early so we can tweak env before importing pipeline ──
parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("--platform", default="linkedin")
parser.add_argument("--content-type", default=None, dest="content_type")
parser.add_argument("--no-research", action="store_true",
                    help="Disable research augmentation (faster)")
parser.add_argument("--no-hero", action="store_true",
                    help="Disable hero image generation (avoids Pollinations wait)")
args = parser.parse_args()

# Apply overrides before config is imported
if args.no_research:
    os.environ["RESEARCH_AUGMENTATION_ENABLED"] = "false"
if args.no_hero:
    os.environ["HERO_IMAGE_ENABLED"] = "false"

# ── now safe to import ──
from config import settings
from pipeline import run_stream

# ── helpers ──
def _safe(obj):
    """Make an object JSON-serialisable (drop raw bytes, keep everything else)."""
    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj


def main():
    url = args.url
    host = urlparse(url).netloc or url
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path("test_data") / f"pipeline_real_{host}_{ts}.json"

    print(f"\n{'='*60}")
    print(f"  URL      : {url}")
    print(f"  Platform : {args.platform}")
    print(f"  Content  : {args.content_type or 'auto'}")
    print(f"  Mock mode: {settings.MOCK_MODE}")
    print(f"  Research : {settings.RESEARCH_AUGMENTATION_ENABLED}")
    print(f"  Hero img : {settings.HERO_IMAGE_ENABLED} ({settings.HERO_IMAGE_PROVIDER})")
    print(f"  Output   : {out_path}")
    print(f"{'='*60}\n")

    events: list[dict] = []
    done_event: dict = {}
    t0 = time.monotonic()

    try:
        for raw_event in run_stream(
            url=url,
            platform=args.platform,
            force_content_type=args.content_type,
        ):
            elapsed = time.monotonic() - t0
            step = raw_event.get("step", "?")
            agent = raw_event.get("agent", "?")
            status = raw_event.get("status", "?")
            msg = raw_event.get("message", "")

            print(f"  [{elapsed:6.1f}s] step={step:>2} {agent:<22} {status:<10} {msg[:70]}")

            events.append(_safe(raw_event))
            # Final pipeline event carries the full result payload
            if raw_event.get("agent") == "pipeline" and raw_event.get("status") == "complete":
                done_event = raw_event

    except KeyboardInterrupt:
        print("\n[capture] interrupted")
    except Exception as exc:
        print(f"\n[capture] pipeline error: {exc}")
        import traceback
        traceback.print_exc()

    total = time.monotonic() - t0
    print(f"\n  Total: {total:.1f}s")
    print(f"  content_type         : {done_event.get('content_type', '?')}")
    print(f"  design_category      : {done_event.get('design_category', '?')}")
    print(f"  logo_confidence      : {done_event.get('logo_confidence', '?')}")
    print(f"  logo_compositing     : {done_event.get('logo_compositing_enabled', '?')}")
    hero_url = done_event.get('background_hero_url')
    hero_err = done_event.get('hero_error')
    if hero_url:
        print(f"  hero_image_url       : {hero_url}")
    elif hero_err:
        print(f"  hero_image_error     : {hero_err}")
    img_prompt = done_event.get('image_prompt')
    if img_prompt:
        print(f"  image_prompt         : {img_prompt[:120]}...")
    print()

    # ── assemble output ──
    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "platform": args.platform,
        "run_id": done_event.get("run_id") or (events[0].get("run_id") if events else None),
        "elapsed_seconds": round(total, 1),
        "settings": {
            "MOCK_MODE": settings.MOCK_MODE,
            "RESEARCH_AUGMENTATION_ENABLED": settings.RESEARCH_AUGMENTATION_ENABLED,
            "HERO_IMAGE_ENABLED": settings.HERO_IMAGE_ENABLED,
            "HERO_IMAGE_PROVIDER": settings.HERO_IMAGE_PROVIDER,
            "COMPOSITOR_ENABLED": settings.COMPOSITOR_ENABLED,
            "LLM_PROVIDER": settings.LLM_PROVIDER,
            "LLM_TEXT_MODEL": settings.LLM_TEXT_MODEL,
            "LLM_VISION_PROVIDER": settings.LLM_VISION_PROVIDER,
        },
        "events": events,
        "done": _safe(done_event),
    }

    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[capture] saved -> {out_path}")


if __name__ == "__main__":
    main()
