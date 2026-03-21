"""
pytest configuration — applied before any test runs.

Reconfigures stdout/stderr to UTF-8 with error replacement so that
non-ASCII characters in model responses (e.g. tick/cross symbols from
Groq) never cause UnicodeEncodeError on Windows cp1252 terminals.
"""
import sys


def pytest_configure(config):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
