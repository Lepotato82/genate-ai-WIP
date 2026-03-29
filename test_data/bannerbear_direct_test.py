# test_data/bannerbear_direct_test.py
# Run with: python test_data/bannerbear_direct_test.py
# No LLM calls. No Playwright. Just Bannerbear.

import os
import httpx
import json

BANNERBEAR_API_KEY = "bb_pr_3e7ef2085b6b86d2df0f4d8f2c3325"
if not BANNERBEAR_API_KEY:
    raise ValueError("BANNERBEAR_API_KEY is not set")
TEMPLATE_UID = "YJBpekZX8X9wZ2XPnO"

# ── Test cases — real brand data from previous pipeline runs ──────

test_cases = [

    {
        "name": "Linear — dark background, purple accent",
        "brand": {
            "background_color": "#08090a",
            "primary_color":    "#5e6ad2",   # real Linear purple
            "secondary_color":  "#7170ff",
            "logo_url": "https://linear.app/static/apple-touch-icon.png?v=2",
            "logo_compositing_enabled": True,
            "product_name": "Linear",
        },
        "slides": [
            {
                "slide_label": "01 / 04",
                "headline": "Your standup exists to answer one question nobody should have to ask.",
                "body_text": "When issue state lives in someone's head instead of the board, every sync becomes a status meeting.",
            },
            {
                "slide_label": "02 / 04",
                "headline": "Linear makes issue state automatic.",
                "body_text": "Push a branch — the issue moves. Merge the PR — it closes. No manual updates. No status meetings.",
            },
            {
                "slide_label": "03 / 04",
                "headline": "Used by Vercel, Raycast, and Mercury engineering teams.",
                "body_text": "Teams that ship fast don't run status meetings. Their code runs the standup.",
            },
            {
                "slide_label": "04 / 04",
                "headline": "Free to try. Your next sprint planning is in 3 days.",
                "body_text": "linear.app",
            },
        ],
    },

    {
        "name": "Chargebee — dark background, teal accent",
        "brand": {
            "background_color": "#000000",
            "primary_color":    "#012a38",
            "secondary_color":  "#00b4d8",   # Chargebee teal
            "logo_url": "https://www.chargebee.com/static/resources/brand/apple-touch-icon.png?v=1",
            "logo_compositing_enabled": True,
            "product_name": "Chargebee",
        },
        "slides": [
            {
                "slide_label": "01 / 03",
                "headline": "63% of failed payments are recoverable. Most SaaS teams write them off.",
                "body_text": "Failed payments are not churn. They are timing problems.",
            },
            {
                "slide_label": "02 / 03",
                "headline": "Smart dunning retries at the right bank window.",
                "body_text": "Tuesday 9am achieves 41% recovery. Untimed retries achieve 12%. Same customer. Same card. Just timing.",
            },
            {
                "slide_label": "03 / 03",
                "headline": "Free dunning audit — see what you are leaving on the table.",
                "body_text": "chargebee.com/dunning",
            },
        ],
    },

    {
        "name": "Searchable — light background, orange accent",
        "brand": {
            "background_color": "#fdfbf9",
            "primary_color":    "#c15f3c",   # warm orange
            "secondary_color":  "#2e1c22",
            "logo_url": None,                # no high-confidence logo
            "logo_compositing_enabled": False,
            "product_name": "Searchable",
        },
        "slides": [
            {
                "slide_label": "01 / 03",
                "headline": "You check five AI engines every morning to see if your brand shows up.",
                "body_text": "It takes an hour. It changes nothing. You have no idea why you rank where you rank.",
            },
            {
                "slide_label": "02 / 03",
                "headline": "206% share of voice improvements.",
                "body_text": "Searchable tracks your brand across ChatGPT, Claude, Perplexity, and Google AI — and shows you exactly what to fix.",
            },
            {
                "slide_label": "03 / 03",
                "headline": "Start your trial. See your AI search position today.",
                "body_text": "searchable.com",
            },
        ],
    },

    {
        "name": "Razorpay — dark background, blue accent",
        "brand": {
            "background_color": "#0f0f0f",
            "primary_color":    "#2d9cdb",   # Razorpay blue
            "secondary_color":  "#528ff0",
            "logo_url": "https://razorpay.com/favicon.ico",
            "logo_compositing_enabled": False,  # favicon = low confidence
            "product_name": "Razorpay",
        },
        "slides": [
            {
                "slide_label": "01 / 03",
                "headline": "₹1 in every ₹4 of digital payments in India moves through Razorpay.",
                "body_text": "8 million businesses. Every payment method Indians actually use.",
            },
            {
                "slide_label": "02 / 03",
                "headline": "UPI, cards, wallets, EMI — one integration.",
                "body_text": "No compliance overhead. No separate gateway for each method. One dashboard.",
            },
            {
                "slide_label": "03 / 03",
                "headline": "Start accepting payments in 2 minutes.",
                "body_text": "razorpay.com",
            },
        ],
    },

]

# ── Helpers (copied from image_gen.py) ───────────────────────────

def _is_dark(hex_color: str) -> bool:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return (0.299*r + 0.587*g + 0.114*b) / 255 < 0.5

def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    def _lin(c):
        c /= 255.0
        return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
    return 0.2126*_lin(r) + 0.7152*_lin(g) + 0.0722*_lin(b)

def _contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la,lb), min(la,lb)
    return (lighter+0.05)/(darker+0.05)

def _pick_accent(brand: dict) -> str:
    bg = brand["background_color"]
    for color in [brand["primary_color"], brand.get("secondary_color")]:
        if color and _contrast_ratio(color, bg) > 1.5:
            return color
    return "#ffffff" if _is_dark(bg) else "#000000"

def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    t = text[:max_chars]
    last_space = t.rfind(" ")
    if last_space > max_chars // 2:
        t = t[:last_space]
    return t.rstrip(".,;:") + "…"

def _build_modifications(slide: dict, brand: dict) -> list[dict]:
    bg = brand["background_color"]
    text_primary   = "#ffffff" if _is_dark(bg) else "#111111"
    text_secondary = "#cccccc" if _is_dark(bg) else "#444444"
    label_color    = "#888888"
    accent         = _pick_accent(brand)

    mods = [
        {"name": "background_color", "color": bg},
        {"name": "accent_bar",       "color": accent},
        {"name": "slide_label",      "text": slide["slide_label"],
                                     "color": label_color},
        {"name": "headline",         "text": _truncate(slide["headline"], 120),
                                     "color": text_primary},
        {"name": "body_text",        "text": _truncate(slide["body_text"], 280),
                                     "color": text_secondary},
    ]

    if brand.get("logo_url") and brand.get("logo_compositing_enabled"):
        mods.append({"name": "logo", "image_url": brand["logo_url"]})

    return mods

def call_bannerbear(modifications: list[dict]) -> str | None:
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://api.bannerbear.com/v2/images",
            headers={
                "Authorization": f"Bearer {BANNERBEAR_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "template": TEMPLATE_UID,
                "modifications": modifications,
                "synchronous": True,
            },
        )
        if resp.status_code not in (200, 201, 202):
            print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        return data.get("image_url") or data.get("image_url_png")

# ── Run all test cases ────────────────────────────────────────────

results = {}

for case in test_cases:
    name   = case["name"]
    brand  = case["brand"]
    slides = case["slides"]

    print(f"\n=== {name} ===")
    print(f"  background: {brand['background_color']}  "
          f"accent: {_pick_accent(brand)}  "
          f"logo: {'yes' if brand.get('logo_compositing_enabled') else 'no'}")

    urls = []
    for i, slide in enumerate(slides, 1):
        mods = _build_modifications(slide, brand)
        url  = call_bannerbear(mods)
        if url:
            print(f"  slide {i}: {url}")
            urls.append(url)
        else:
            print(f"  slide {i}: FAILED")

    results[name] = urls

# ── Save results ──────────────────────────────────────────────────

with open("test_data/bannerbear_direct_test_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n\nDone. Results saved to test_data/bannerbear_direct_test_results.json")
print("Open the image URLs in your browser to review.")