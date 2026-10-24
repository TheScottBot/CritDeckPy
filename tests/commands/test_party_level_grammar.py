"""The typed party level grammar used by the prefix commands."""

from __future__ import annotations

import pytest

from critdeck.commands.party_level_grammar import MAXIMUM_PARTY_LEVEL_TEXT_LENGTH, parse_party_level_text


@pytest.mark.parametrize(
    ("level_text", "expected_level"),
    [("7", 7), ("20", 20), ("0", 0), ("-1", -1), ("666", 666), ("007", 7)],
)
def test_parse_party_level_text_reads_plain_ascii_integers(level_text: str, expected_level: int) -> None:
    assert parse_party_level_text(level_text) == expected_level


@pytest.mark.parametrize(
    "level_text",
    [
        "",
        "seven",
        "7.5",
        "+7",
        # Python's int() accepts each of these; the grammar deliberately does not.
        "1_2",
        "\N{ARABIC-INDIC DIGIT ONE}\N{ARABIC-INDIC DIGIT TWO}",
        "\N{FULLWIDTH DIGIT SEVEN}",
        " 7",
        "7\t",
        # The Go bot removed spaces, reading this as 12.
        "1 2",
        "7 8",
        "--1",
        "-",
    ],
)
def test_parse_party_level_text_refuses_anything_else(level_text: str) -> None:
    assert parse_party_level_text(level_text) is None


def test_parse_party_level_text_refuses_text_over_the_length_bound_rather_than_truncating() -> None:
    longest_accepted_text = "9" * MAXIMUM_PARTY_LEVEL_TEXT_LENGTH

    assert parse_party_level_text(longest_accepted_text) == int(longest_accepted_text)
    assert parse_party_level_text(longest_accepted_text + "9") is None
    assert parse_party_level_text("7" * 5000) is None
