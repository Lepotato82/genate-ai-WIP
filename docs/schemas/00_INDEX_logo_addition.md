# Logo Extraction — INDEX Entry

Add the following section to /docs/schemas/00_INDEX.md under InputPackage.

---

## InputPackage — Logo Extraction Fields (added March 2026)

Three fields added to the existing InputPackage model to support Phase 2 logo compositing.

| Field | Type | Description |
|---|---|---|
| logo_bytes | bytes \| None | Raw logo image bytes. None if extraction failed. |
| logo_url | str \| None | Source URL the logo was downloaded from. None if logo_bytes is None. |
| logo_confidence | Literal["high", "medium", "low"] \| None | Confidence level of the extraction. None if logo_bytes is None. |

**Cross-field contract:** All three fields are None together or all three are non-None together. A logo_bytes value with a None logo_confidence is a schema violation.

**Phase note:** These fields are extracted by the Input Processor in Phase 1. They are consumed by the Pillow compositing step in Phase 2. Phase 1 agents (UI Analyzer, Product Analysis, etc.) do not use these fields — they are pass-through until Phase 2.

**Full spec:** /docs/schemas/logo_extraction.md
