from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fix_control_chars_in_strings(text: str) -> str:
    """Replace literal control characters inside JSON string values with escape sequences.

    Weak LLMs often output writing_instruction values with real newlines instead of \\n,
    which breaks json.loads. This repairs the most common case before re-trying.
    """
    result: list[str] = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and in_string and i + 1 < n:
            # Valid escape sequence — copy both chars unchanged
            result.append(c)
            i += 1
            result.append(text[i])
        elif c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and c == "\n":
            result.append("\\n")
        elif in_string and c == "\r":
            result.append("\\r")
        elif in_string and c == "\t":
            result.append("\\t")
        else:
            result.append(c)
        i += 1
    return "".join(result)


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    # Find outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Recovery: escape literal control characters that weak LLMs put in string values
        try:
            obj = json.loads(_fix_control_chars_in_strings(text))
        except json.JSONDecodeError as exc2:
            raise ValueError(
                f"LLM returned non-JSON output ({exc2}). Preview: {raw[:300]!r}"
            ) from exc2
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
    return obj
