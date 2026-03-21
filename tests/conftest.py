"""
pytest configuration — applied before any test runs.

Reconfigures stdout/stderr to UTF-8 with error replacement so that
non-ASCII characters in model responses (e.g. tick/cross symbols from
Groq) never cause UnicodeEncodeError on Windows cp1252 terminals.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
