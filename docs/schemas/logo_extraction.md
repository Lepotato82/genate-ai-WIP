# Logo Extraction — Schema Definition

**File:** /docs/schemas/logo_extraction.md  
**Owner:** Person D  
**Status:** Defined — ready for Person A to implement  
**Phase:** Fields added to InputPackage now. Compositing (Bannerbear/Pillow) is Phase 2.

---

## Context

Logo compositing is a Phase 2 feature. The InputPackage fields are defined now so the extraction is available when Phase 2 is built. The extracted `logo_bytes` feed directly into the Pillow compositing step — always the real logo, never AI-generated.

These are **additions to the existing InputPackage model**, not a new schema.

---

## Fields Added to InputPackage

| Field | Type | Required | Constraints | Example value |
|---|---|---|---|---|
| logo_bytes | bytes \| None | No | Valid image bytes if not None. Must start with a known image magic byte. Must be > 1000 bytes. None if extraction failed. | b'\x89PNG\r\n\x1a\n...' |
| logo_url | str \| None | No | The source URL the logo was downloaded from. None if logo_bytes is None. Stored for audit trail and debugging. | "https://linear.app/apple-touch-icon.png" |
| logo_confidence | Literal["high", "medium", "low"] \| None | No | None if logo_bytes is None. See confidence rules below. | "high" |

---

## Extraction Priority Order

The extractor must attempt each source in this order and stop at the first successful extraction.

| Priority | Source | Confidence | Notes |
|---|---|---|---|
| 1 | `<link rel="apple-touch-icon">` | high | Square, high resolution, most reliable signal for brand logo. |
| 2 | `<link rel="icon">` with size attribute ≥ 192px | high | Large enough to be usable. Size must be explicit in the tag — do not assume size from the file. |
| 3 | `<img>` inside `<header>` element where class, id, or alt attribute contains "logo" (case-insensitive) | high | Catches custom logo placements that do not use standard link tags. |
| 4 | `<meta property="og:image">` | medium | The OG card image often contains the logo but may also contain marketing imagery. Lower confidence because the image may not be the logo alone. |
| 5 | Favicon (`<link rel="icon">` or `/favicon.ico`) | low | Absolute last resort. Often 16px or 32px — too small to be useful for compositing. Only use if all higher-priority sources fail. |

---

## Validation Rules (for Person A to implement)

```python
# logo_bytes must be valid image bytes if not None
VALID_IMAGE_MAGIC_BYTES = [
    b'\x89PNG',    # PNG
    b'\xff\xd8\xff',  # JPEG
    b'RIFF',       # WebP
    b'GIF8',       # GIF
]

# logo_bytes must be > 1000 bytes — anything smaller is likely not a real logo
MIN_LOGO_BYTES = 1000

# If logo_bytes is None, logo_url and logo_confidence must also be None
# (all three fields are None together or all three are non-None together)

# Never crash the pipeline if logo extraction fails
# Return logo_bytes=None, logo_url=None, logo_confidence=None and continue
```

---

## Confidence Assignment Rules

| Condition | logo_confidence value |
|---|---|
| Extracted from `apple-touch-icon` | "high" |
| Extracted from `<link rel="icon">` with explicit size ≥ 192px | "high" |
| Extracted from `<img>` in `<header>` with "logo" in class/id/alt | "high" |
| Extracted from `og:image` | "medium" |
| Extracted from favicon (any size) | "low" |
| Extraction failed | None |

---

## Failure Behaviour

If logo extraction fails for any reason (network error, no matching element found, downloaded bytes fail validation):

- Log the failure with the URL and the reason
- Set `logo_bytes = None`, `logo_url = None`, `logo_confidence = None`
- Continue the pipeline — **never crash because logo extraction failed**
- Phase 2 image compositing must check `logo_bytes is not None` before attempting compositing
