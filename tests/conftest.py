"""Shared fixtures and doubles for the CritDeck test suite.

Fixtures and doubles live here and nowhere else, so every test file imports
them rather than defining its own, and a change to one is a change to all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
REAL_DECK_DIRECTORY = REPOSITORY_ROOT / "decks"

# Synthetic card text only. The real card text is third party data and never
# appears in a fixture.
SYNTHETIC_EFFECTS = (
    {"damageType": "Bludgeoning", "value": "Synthetic bludgeoning effect"},
    {"damageType": "Piercing", "value": "Synthetic piercing effect"},
)


def build_card_record(
    strength: str = "Setback", effects: list[dict[str, object]] | None = None
) -> dict[str, object]:
    return {
        "strength": strength,
        "effects": list(SYNTHETIC_EFFECTS) if effects is None else effects,
    }


def encode_deck_document(deck_document: object) -> bytes:
    return json.dumps(deck_document).encode("utf-8")


def build_tiered_deck_bytes(strengths: list[str]) -> bytes:
    return encode_deck_document({"cards": [build_card_record(strength) for strength in strengths]})


def build_special_level_deck_bytes(level: int, card_count: int = 1) -> bytes:
    return encode_deck_document({"level": level, "cards": [build_card_record() for _ in range(card_count)]})


def write_deck_directory(
    deck_directory: Path,
    base_deck_bytes: bytes | None,
    extension_files: dict[str, bytes] | None = None,
    special_level_files: dict[str, bytes] | None = None,
) -> Path:
    deck_directory.mkdir(parents=True, exist_ok=True)
    if base_deck_bytes is not None:
        (deck_directory / "player-deck.json").write_bytes(base_deck_bytes)
    for subdirectory_name, named_files in (
        ("extensions", extension_files),
        ("special-levels", special_level_files),
    ):
        if named_files is None:
            continue
        subdirectory = deck_directory / subdirectory_name
        subdirectory.mkdir(exist_ok=True)
        for file_name, file_bytes in named_files.items():
            (subdirectory / file_name).write_bytes(file_bytes)
    return deck_directory


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
