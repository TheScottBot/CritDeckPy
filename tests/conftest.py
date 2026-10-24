"""Shared fixtures and doubles for the CritDeck test suite.

Datum 0.7 requires fixtures and doubles to live in one place, so every test file
imports from here rather than defining its own.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def run_development_tool(
    *tool_arguments: str, standard_input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    # The tools run from the repository root so they read the real pyproject.toml,
    # which is the configuration under test.
    return subprocess.run(  # noqa: S603  # arguments are fixed by the tests, never external input
        [sys.executable, "-m", *tool_arguments],
        cwd=REPOSITORY_ROOT,
        input=standard_input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
