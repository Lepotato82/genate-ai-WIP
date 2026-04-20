"""
Run a carousel pipeline test and save all outputs:
  - carousel_samples/<host>/slide_01.png ... slide_N.png
  - carousel_samples/<host>/post.txt          (full post text)
  - carousel_samples/<host>/agent_trace.json  (every agent's input/output)

Usage:
    python run_carousel_test.py https://datapret.ai
    python run_carousel_test.py https://datapret.ai --no-hero   # skip Pollinations (faster)
"""

import argparse
import base64
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

# ── parse args before importing pipeline (so env overrides take effect) ──
parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("--no-hero", action="store_true",
                    help="Disable hero image generation (avoids Pollinations wait)")
parser.add_argument("--no-research", action="store_true",
                    help="Disable research augmentation (faster)")
args = parser.parse_args()

os.environ["MOCK_MODE"] = "false"
if args.no_hero:
    os.environ["HERO_IMAGE_ENABLED"] = "false"
if args.no_research:
    os.environ["RESEARCH_AUGMENTATION_ENABLED"] = "false"

from config import settings
from pipeline import run_stream


def _safe(obj):
    """JSON-serialisable: drop raw bytes, keep everything else."""
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
    out_dir = Path("carousel_samples") / host.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  URL       : {url}")
    print(f"  Platform  : linkedin")
    print(f"  Content   : carousel (forced)")
    print(f"  Mock mode : {settings.MOCK_MODE}")
    print(f"  Research  : {settings.RESEARCH_AUGMENTATION_ENABLED}")
    print(f"  Hero img  : {settings.HERO_IMAGE_ENABLED} ({settings.HERO_IMAGE_PROVIDER})")
    print(f"  Output dir: {out_dir}")
    print(f"{'='*60}\n")

    events: list[dict] = []
    done_event: dict = {}
    t0 = time.monotonic()

    try:
        for raw_event in run_stream(
            url=url,
            platform="linkedin",
            force_content_type="carousel",
        ):
            elapsed = time.monotonic() - t0
            step = raw_event.get("step", "?")
            agent = raw_event.get("agent", "?")
            status = raw_event.get("status", "?")
            msg = raw_event.get("message", "")

            print(f"  [{elapsed:6.1f}s] step={step:>2} {agent:<22} {status:<10} {msg[:80]}")

            events.append(_safe(raw_event))
            if raw_event.get("agent") == "pipeline" and raw_event.get("status") == "complete":
                done_event = raw_event

    except KeyboardInterrupt:
        print("\n[run] interrupted by user")
    except Exception as exc:
        print(f"\n[run] pipeline error: {exc}")
        import traceback
        traceback.print_exc()

    total = time.monotonic() - t0
    print(f"\n  Total time: {total:.1f}s")

    if not done_event:
        print("[run] Pipeline did not complete — no outputs to save.")
        # Still save the partial trace
        trace_path = out_dir / "agent_trace_partial.json"
        trace_path.write_text(json.dumps({"events": events}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[run] Partial trace saved -> {trace_path}")
        return

    # ── 1. Save carousel slide PNGs ──
    composed = done_event.get("composed_images", {})
    slides = composed.get("composed_images", [])
    slide_paths = []
    if slides:
        print(f"\n  Saving {len(slides)} carousel slides...")
        for slide in slides:
            idx = slide.get("slide_index", 0)
            png_b64 = slide.get("png_b64", "")
            if png_b64:
                fname = f"slide_{idx + 1:02d}.png"
                fpath = out_dir / fname
                fpath.write_bytes(base64.b64decode(png_b64))
                slide_paths.append(str(fpath))
                layout = slide.get("layout", "?")
                print(f"    {fname}  ({slide.get('width', '?')}x{slide.get('height', '?')}, layout={layout})")
    else:
        print("\n  No composed slides in output (compositor may be disabled or content type mismatch).")

    # ── 2. Save full post text ──
    fc = done_event.get("formatted_content", {})
    li = fc.get("linkedin_content")
    post_text = ""
    if li:
        post_text = li.get("full_post", "")
    if not post_text:
        # Fallback: try other platforms
        for key in ("twitter_content", "instagram_content", "blog_content"):
            c = fc.get(key)
            if c:
                post_text = c.get("full_post", "") or c.get("caption", "") or c.get("body", "") or ""
                if post_text:
                    break

    post_path = out_dir / "post.txt"
    post_path.write_text(post_text or "(no post text captured)", encoding="utf-8")
    print(f"\n  Post text saved -> {post_path} ({len(post_text)} chars)")

    # ── 3. Save full agent trace JSON ──
    # Build a structured trace with per-agent sections
    trace = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "platform": "linkedin",
        "content_type": done_event.get("content_type", "?"),
        "run_id": done_event.get("run_id"),
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
        "results": {
            "passes": done_event.get("passes"),
            "design_category": done_event.get("design_category"),
            "logo_confidence": done_event.get("logo_confidence"),
            "logo_compositing_enabled": done_event.get("logo_compositing_enabled"),
            "image_prompt": done_event.get("image_prompt"),
            "background_hero_url": done_event.get("background_hero_url"),
            "hero_error": done_event.get("hero_error"),
        },
        "formatted_content": _safe(fc),
        "evaluator_output": _safe(done_event.get("evaluator_output", {})),
        "compositor": {
            "slide_count": composed.get("slide_count", 0),
            "layout": composed.get("layout"),
            "compositor_enabled": composed.get("compositor_enabled"),
            "error": composed.get("error"),
            "slides": [
                {
                    "slide_index": s.get("slide_index"),
                    "width": s.get("width"),
                    "height": s.get("height"),
                    "layout": s.get("layout"),
                }
                for s in slides
            ],
        },
        "events": events,
    }

    trace_path = out_dir / "agent_trace.json"
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Agent trace saved -> {trace_path}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  Content type     : {done_event.get('content_type', '?')}")
    print(f"  Design category  : {done_event.get('design_category', '?')}")
    print(f"  Evaluator passes : {done_event.get('passes', '?')}")
    print(f"  Carousel slides  : {len(slides)}")
    print(f"  Post length      : {len(post_text)} chars")
    print(f"  Output directory  : {out_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
