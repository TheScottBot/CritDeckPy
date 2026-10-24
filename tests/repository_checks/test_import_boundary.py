"""The import boundary check fails on a planted violation.

`core` and `commands` must build and test with nothing but the language
toolchain, so they may not import discord or the adapter that wraps it.
"""

from __future__ import annotations

import pytest

from tests.conftest import run_development_tool

PORTABLE_MODULE_PATHS = (
    "src/critdeck/core/planted_violation.py",
    "src/critdeck/commands/planted_violation.py",
)

FORBIDDEN_IMPORT_STATEMENTS = (
    "import discord\n",
    "from discord import app_commands\n",
    "from discord.ext import commands\n",
    "import critdeck.discord_adapter\n",
    "from critdeck.discord_adapter import client\n",
)


def lint_planted_source(planted_path: str, planted_source: str) -> str:
    lint_result = run_development_tool(
        "ruff",
        "check",
        "--no-cache",
        "--select",
        "TID251",
        "--stdin-filename",
        planted_path,
        "-",
        standard_input_text=planted_source,
    )
    return lint_result.stdout + lint_result.stderr


@pytest.mark.parametrize("planted_path", PORTABLE_MODULE_PATHS)
@pytest.mark.parametrize("forbidden_import_statement", FORBIDDEN_IMPORT_STATEMENTS)
def test_import_boundary_rejects_discord_or_adapter_import_in_portable_module(
    planted_path: str, forbidden_import_statement: str
) -> None:
    lint_output = lint_planted_source(planted_path, forbidden_import_statement)

    assert "TID251" in lint_output, lint_output


@pytest.mark.parametrize("forbidden_import_statement", FORBIDDEN_IMPORT_STATEMENTS)
def test_import_boundary_allows_discord_import_in_adapter(forbidden_import_statement: str) -> None:
    lint_output = lint_planted_source(
        "src/critdeck/discord_adapter/planted_violation.py", forbidden_import_statement
    )

    assert "TID251" not in lint_output, lint_output
