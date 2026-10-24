"""The type checker and formatter fail on planted violations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import REPOSITORY_ROOT, run_development_tool

if TYPE_CHECKING:
    from pathlib import Path

# Each planted error carries the mypy error code it must produce, so a run that
# fails for some other reason (a missing configuration file, say) cannot pass.
PLANTED_TYPE_ERRORS = {
    "wrong_assignment_type": ("party_level: int = 'seven'\n", "[assignment]"),
    "untyped_function": ("def build_deck(party_level):\n    return party_level\n", "[no-untyped-def]"),
    "implicit_any_return": (
        "import json\n\n\ndef read_level(level_text: str) -> int:\n    return json.loads(level_text)\n",
        "[no-any-return]",
    ),
}


@pytest.mark.parametrize(
    ("planted_source", "expected_error_code"),
    PLANTED_TYPE_ERRORS.values(),
    ids=PLANTED_TYPE_ERRORS.keys(),
)
def test_type_checker_rejects_planted_type_error(
    planted_source: str, expected_error_code: str, tmp_path: Path
) -> None:
    planted_file_path = tmp_path / "planted_violation.py"
    planted_file_path.write_text(planted_source, encoding="utf-8")

    type_check_result = run_development_tool(
        "mypy",
        "--config-file",
        str(REPOSITORY_ROOT / "pyproject.toml"),
        "--no-incremental",
        str(planted_file_path),
    )
    type_check_output = type_check_result.stdout + type_check_result.stderr

    assert type_check_result.returncode != 0, type_check_output
    assert expected_error_code in type_check_result.stdout, type_check_output


def test_formatter_check_rejects_unformatted_source() -> None:
    format_check_result = run_development_tool(
        "ruff",
        "format",
        "--check",
        "--no-cache",
        "--stdin-filename",
        "src/critdeck/planted_violation.py",
        "-",
        standard_input_text="party_level   =  [ 1,2 ]\n",
    )

    assert format_check_result.returncode != 0, format_check_result.stdout
