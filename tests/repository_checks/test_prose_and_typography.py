"""The prose and typography scan (datum 0.8) finds every planted violation."""

from __future__ import annotations

from pathlib import Path

import pytest

from repository_checks.prose_and_typography import (
    VENDORED_PATHS,
    TypographyViolationReason,
    find_typography_violations,
    scan_files,
)

EM_DASH = "\N{EM DASH}"
EN_DASH = "\N{EN DASH}"
# Built rather than written, so this file passes the scan it tests.
DOUBLE_HYPHEN = "-" * 2
TRIPLE_HYPHEN = "-" * 3


@pytest.mark.parametrize(
    ("planted_line", "expected_reason"),
    [
        (f"The deck {EM_DASH} shuffled", TypographyViolationReason.EM_DASH),
        (f"Levels 0{EN_DASH}20", TypographyViolationReason.EN_DASH),
        (f"The deck {DOUBLE_HYPHEN} shuffled", TypographyViolationReason.HYPHEN_RUN),
        (f"The deck {TRIPLE_HYPHEN} shuffled", TypographyViolationReason.HYPHEN_RUN),
        (f"ends with a run{DOUBLE_HYPHEN}", TypographyViolationReason.HYPHEN_RUN),
        (TRIPLE_HYPHEN, TypographyViolationReason.HYPHEN_RUN),
    ],
)
def test_find_typography_violations_reports_planted_violation(
    planted_line: str, expected_reason: TypographyViolationReason
) -> None:
    violations = find_typography_violations(f"First line\n{planted_line}\n")

    assert [violation.reason for violation in violations] == [expected_reason]
    assert violations[0].line_number == 2


@pytest.mark.parametrize(
    "clean_line",
    [
        "A plain sentence, with a comma; and a semicolon.",
        "| Phase | Status |",
        f"|{TRIPLE_HYPHEN}|{TRIPLE_HYPHEN}|",
        f"| {TRIPLE_HYPHEN} | :{TRIPLE_HYPHEN}: | {TRIPLE_HYPHEN}: |",
        "Run it with --guild-id and --env-file set.",
        'python -m pytest "--no-header"',
        "a single-hyphen compound and a -W flag",
    ],
)
def test_find_typography_violations_accepts_clean_line(clean_line: str) -> None:
    assert find_typography_violations(clean_line + "\n") == []


def test_find_typography_violations_reports_every_violation_with_its_column() -> None:
    violations = find_typography_violations(f"one {EM_DASH} two {EN_DASH} three {DOUBLE_HYPHEN} four\n")

    assert [(violation.column_number, violation.reason) for violation in violations] == [
        (5, TypographyViolationReason.EM_DASH),
        (11, TypographyViolationReason.EN_DASH),
        (19, TypographyViolationReason.HYPHEN_RUN),
    ]


def test_scan_files_reports_file_that_is_not_utf8(tmp_path: Path) -> None:
    undecodable_file_path = tmp_path / "notes.md"
    undecodable_file_path.write_bytes(b"caf\xe9\n")

    file_violations = scan_files(tmp_path, [Path("notes.md")])

    assert [violation.reason for violation in file_violations] == [TypographyViolationReason.NOT_UTF8]


def test_scan_files_skips_binary_file(tmp_path: Path) -> None:
    binary_file_path = tmp_path / "icon.png"
    binary_file_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00 " + DOUBLE_HYPHEN.encode() + b" \x00")

    assert scan_files(tmp_path, [Path("icon.png")]) == []


def test_scan_files_names_the_file_of_each_violation(tmp_path: Path) -> None:
    (tmp_path / "clean.md").write_text("Nothing wrong here.\n", encoding="utf-8")
    (tmp_path / "planted.md").write_text(f"Something {EM_DASH} wrong.\n", encoding="utf-8")

    file_violations = scan_files(tmp_path, [Path("clean.md"), Path("planted.md")])

    assert [(violation.relative_path, violation.line_number) for violation in file_violations] == [
        (Path("planted.md"), 1)
    ]


def test_vendored_paths_are_an_explicit_list_and_empty_until_something_is_vendored() -> None:
    # Datum 0.8: vendored code is excluded by an explicit list, never a pattern.
    assert VENDORED_PATHS == ()
