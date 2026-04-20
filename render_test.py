"""
Render all 9 compositor layout archetypes using searchable.com brand data
from test_data/groq_linkedin_run2.json. Saves PNGs to test_previews/.

Usage: python render_test.py
No LLM calls. Hero image downloaded once from Pollinations and cached locally.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from agents.compositor import _compose_slide, _LAYOUT_FNS, _PHOTO_LAYOUTS
from schemas.brand_identity import BrandIdentity

DATA_FILE = ROOT / "test_data" / "groq_linkedin_run2.json"
OUT_DIR = ROOT / "test_previews"

# Hero image from last successful Pollinations run — cached to avoid re-fetching
_HERO_CACHE = OUT_DIR / "_hero_cache.bin"
_HERO_URL = (
    "https://image.pollinations.ai/prompt/Create%20a%20minimalist%20illustration%20with%20a%20subtle%20gradient%20"
    "background%20that%20transitions%20from%20a%20soft%2C%20creamy%20white%20to%20a%20light%20gray%2C%20"
    "representing%20a%20calm%20and%20serene%20atmosphere%2C%20with%20roughly%2060%25%20of%20the%20frame%20"
    "on%20the%20left%20side%20reserved%20as%20a%20clean%2C%20low-detail%20zone%20with%20a%20solid%20fill%20"
    "or%20very%20soft%20gradient%2C%20suitable%20for%20overlaid%20text%2C%20while%20the%20right%20side%20"
    "features%20gentle%2C%20abstract%20shapes%20and%20subtle%20light%20rays%20in%20the%20primary%20color%20"
    "%231a0f13%20and%20secondary%20color%20%2365454e%2C%20evoking%20a%20sense%20of%20quiet%20focus%20and%20"
    "productivity%2C%20with%20a%20hint%20of%20warm%20beige%20%23fdfbf9%20in%20the%20background%20to%20"
    "convey%20a%20sense%20of%20approachability%20and%20simplicity%2C%20all%20while%20maintaining%20an%20"
    "asymmetric%20composition%20that%20leans%20into%20the%20right%20side%20for%20visual%20interest%2C%20"
    "keeping%20the%20left%20side%20clear%20and%20uncluttered%20for%20easy%20readability%2C%20and%20"
    "capturing%20the%20essence%20of%20a%20quiet%20morning%20moment%20of%20contemplation%20and%20insight%2C%20"
    "free%20from%20distractions%20and%20clutter%2C%20with%20soft%20shadows%20and%20gentle%20texture%20to%20"
    "add%20depth%20and%20nuance%20to%20the%20scene%2C%20in%20a%20style%20that%20echoes%20editorial%20tech%20"
    "illustration%20with%20a%20minimalist%20aesthetic.?width=768&height=432"
)


def _load_hero() -> bytes | None:
    """Return cached hero bytes, downloading once if needed."""
    OUT_DIR.mkdir(exist_ok=True)
    if _HERO_CACHE.exists():
        return _HERO_CACHE.read_bytes()
    print("  Downloading hero image from Pollinations (once)...")
    try:
        import httpx
        r = httpx.get(_HERO_URL, follow_redirects=True, timeout=120)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            _HERO_CACHE.write_bytes(r.content)
            print(f"  Cached to {_HERO_CACHE} ({len(r.content) // 1024} KB)")
            return r.content
        print(f"  Hero download failed: HTTP {r.status_code}")
    except Exception as exc:
        print(f"  Hero download error: {exc}")
    return None


def _extract_identity(data: dict) -> BrandIdentity:
    bp = data["brand_profile"]

    _ACCENT_PRIORITY = ["--primary", "--ring", "--chart-1"]
    accent_color: str | None = None
    for key in _ACCENT_PRIORITY:
        raw = (bp.get("css_tokens") or {}).get(key)
        if raw:
            accent_color = raw
            break

    logo_path = ROOT / "logo_searchable.com.png"
    logo_bytes = logo_path.read_bytes() if logo_path.exists() else None
    logo_confidence = "high" if logo_bytes else None
    logo_url = "https://searchable.com#local-test-logo" if logo_bytes else None

    return BrandIdentity(
        product_name="Searchable",
        product_url="https://searchable.com",
        run_id=data["run_id"],
        primary_color=bp["primary_color"],
        secondary_color=bp.get("secondary_color"),
        accent_color=accent_color,
        background_color=bp["background_color"],
        design_category=bp["design_category"],
        tone=bp["tone"],
        writing_instruction=bp["writing_instruction"],
        logo_bytes=logo_bytes,
        logo_url=logo_url,
        logo_confidence=logo_confidence,
    )


def main() -> None:
    if not DATA_FILE.exists():
        sys.exit(f"[render_test] File not found: {DATA_FILE}")

    with DATA_FILE.open(encoding="utf-8") as f:
        data = json.load(f)

    identity = _extract_identity(data)
    hero_bytes = _load_hero()

    lc = data["formatted_content"]["linkedin_content"]
    headline = lc["hook"]
    paragraphs = lc["body"].split("\n\n")
    subtext = paragraphs[0] if paragraphs else ""

    OUT_DIR.mkdir(exist_ok=True)

    print(f"\nBrand:      {identity.product_name}")
    print(f"Colors:     primary={identity.primary_color}  accent={identity.accent_color}  bg={identity.background_color}")
    print(f"Category:   {identity.design_category}")
    logo_status = f"yes (compositing={'on' if identity.logo_compositing_enabled else 'off'})" if identity.logo_bytes else "no"
    print(f"Logo:       {logo_status}")
    print(f"Hero:       {'yes (' + str(len(hero_bytes) // 1024) + ' KB)' if hero_bytes else 'no (photo layouts use fallback)'}")
    print(f"Headline:   {headline[:70]}...")
    print()

    for layout in _LAYOUT_FNS:
        png_bytes = _compose_slide(
            headline=headline,
            subtext=subtext,
            slide_label="01 / 01",
            identity=identity,
            layout=layout,
            canvas_size=(1080, 1080),
            hero_bytes=hero_bytes if layout in _PHOTO_LAYOUTS else None,
        )
        out_path = OUT_DIR / f"searchable_{layout}.png"
        out_path.write_bytes(png_bytes)
        kb = len(png_bytes) // 1024
        photo_tag = " [photo]" if layout in _PHOTO_LAYOUTS else ""
        print(f"  [{layout:20s}]  {out_path.name}  ({kb} KB){photo_tag}")

    print(f"\nAll {len(_LAYOUT_FNS)} layouts written to {OUT_DIR}/")


if __name__ == "__main__":
    main()
