"""
Dependency health checks.

Called by GET /health to surface missing external CLI tools at runtime.
Add new checks here when new external dependencies are introduced.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def _check_cli(command: str) -> bool:
    """
    Run a shell command and return True if it exits with code 0.
    Treats FileNotFoundError and TimeoutExpired as False (not installed).
    """
    parts = command.split()
    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except FileNotFoundError:
        logger.debug("CLI not found: %s", parts[0])
        return False
    except subprocess.TimeoutExpired:
        logger.debug("CLI check timed out: %s", command)
        return False
    except Exception as exc:
        logger.debug("CLI check failed for %r: %s", command, exc)
        return False


def check_dependencies() -> dict[str, bool]:
    """
    Check availability of all external CLI dependencies.

    Returns a dict of {dependency_name: is_available}.
    Used by the /health endpoint — a False value surfaces a missing dep
    to ops/developers without crashing the service.

    Currently checked:
      dembrandt  — Node.js CLI for CSS token extraction (npm install -g dembrandt)
      playwright — Playwright CLI for browser automation
    """
    return {
        "dembrandt": _check_cli("dembrandt --version"),
        "playwright": _check_cli("playwright --version"),
    }
