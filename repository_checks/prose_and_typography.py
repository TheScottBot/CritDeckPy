"""Prose and typography scan over every tracked text file (datum 0.8).

Run as ``python -m repository_checks.prose_and_typography``. Exits non zero and
lists every violation as path, line, column and reason.
"""

from __future__ import annotations

import enum
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Datum 0.8: vendored sources are exempt, listed explicitly by path rather than
# matched by pattern, because a pattern eventually excludes something that is not
# vendored. Nothing is vendored yet.
VENDORED_PATHS: tuple[Path, ...] = ()

EM_DASH = "\N{EM DASH}"
EN_DASH = "\N{EN DASH}"

HYPHEN_RUN_PATTERN = re.compile(r"-{2,}")
# Datum 0.8 exempts exactly two things from the hyphen run rule: a Markdown table
# separator row and a command line flag token.
TABLE_SEPARATOR_ROW_PATTERN = re.compile(r"\s*\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*")
FLAG_TOKEN_HYPHEN_COUNT = 2
FLAG_TOKEN_PATTERN = re.compile(r"(?:^|(?<=[\s\"'`(\[=]))-{2}[A-Za-z0-9]")

# A NUL byte in the first block is how git itself decides a file is binary.
BINARY_DETECTION_BLOCK_SIZE = 8000


class TypographyViolationReason(enum.Enum):
    EM_DASH = "em dash"
    EN_DASH = "en dash"
    HYPHEN_RUN = "hyphen run in prose"
    NOT_UTF8 = "not valid UTF-8"


@dataclass(frozen=True)
class TypographyViolation:
    line_number: int
    column_number: int
    reason: TypographyViolationReason


@dataclass(frozen=True)
class FileTypographyViolation:
    relative_path: Path
    line_number: int
    column_number: int
    reason: TypographyViolationReason


def find_typography_violations(text: str) -> list[TypographyViolation]:
    violations: list[TypographyViolation] = []
    for line_index, line in enumerate(text.splitlines()):
        line_number = line_index + 1
        violations.extend(
            TypographyViolation(line_number, column_index + 1, reason)
            for column_index, reason in _dash_violations_in_line(line)
        )
    return violations


def _dash_violations_in_line(line: str) -> list[tuple[int, TypographyViolationReason]]:
    line_violations: list[tuple[int, TypographyViolationReason]] = []
    for column_index, character in enumerate(line):
        if character == EM_DASH:
            line_violations.append((column_index, TypographyViolationReason.EM_DASH))
        elif character == EN_DASH:
            line_violations.append((column_index, TypographyViolationReason.EN_DASH))
    if not TABLE_SEPARATOR_ROW_PATTERN.fullmatch(line):
        flag_token_starts = {flag_match.start() for flag_match in FLAG_TOKEN_PATTERN.finditer(line)}
        line_violations.extend(
            (hyphen_run.start(), TypographyViolationReason.HYPHEN_RUN)
            for hyphen_run in HYPHEN_RUN_PATTERN.finditer(line)
            if not (
                hyphen_run.start() in flag_token_starts and len(hyphen_run.group()) == FLAG_TOKEN_HYPHEN_COUNT
            )
        )
    return sorted(line_violations, key=lambda violation_position: violation_position[0])


def scan_files(repository_root: Path, relative_paths: list[Path]) -> list[FileTypographyViolation]:
    file_violations: list[FileTypographyViolation] = []
    for relative_path in relative_paths:
        if relative_path in VENDORED_PATHS:
            continue
        file_bytes = (repository_root / relative_path).read_bytes()
        if b"\x00" in file_bytes[:BINARY_DETECTION_BLOCK_SIZE]:
            continue
        try:
            file_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            file_violations.append(
                FileTypographyViolation(relative_path, 1, 1, TypographyViolationReason.NOT_UTF8)
            )
            continue
        file_violations.extend(
            FileTypographyViolation(
                relative_path, violation.line_number, violation.column_number, violation.reason
            )
            for violation in find_typography_violations(file_text)
        )
    return file_violations


def list_repository_text_files(repository_root: Path) -> list[Path]:
    # Tracked files plus new files not yet added, so a violation is caught before
    # it is committed rather than after. Ignored files are not the repository's.
    git_listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],  # noqa: S607  # git is resolved from PATH on every platform the checks run on
        cwd=repository_root,
        capture_output=True,
        check=True,
    )
    listed_paths = git_listing.stdout.decode("utf-8").split("\0")
    return sorted(
        Path(listed_path)
        for listed_path in listed_paths
        if listed_path and (repository_root / listed_path).is_file()
    )


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    file_violations = scan_files(repository_root, list_repository_text_files(repository_root))
    for file_violation in file_violations:
        print(
            f"{file_violation.relative_path.as_posix()}:{file_violation.line_number}:"
            f"{file_violation.column_number}: {file_violation.reason.value}"
        )
    print(f"{len(file_violations)} prose and typography violations", file=sys.stderr)
    return 1 if file_violations else 0


if __name__ == "__main__":
    sys.exit(main())
