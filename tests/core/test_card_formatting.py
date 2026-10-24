"""The text of a drawn card, byte for byte as the Go bot sent it."""

from __future__ import annotations

from critdeck.core.card_formatting import format_card
from critdeck.core.catalogue import Card, CardEffect, StrengthTier


def test_format_card_writes_each_effect_followed_by_a_blank_line() -> None:
    synthetic_card = Card(
        StrengthTier.DANGEROUS,
        (CardEffect("Slashing", "First synthetic effect"), CardEffect("Magic", "Second synthetic effect")),
    )

    assert format_card(synthetic_card) == (
        "Damage Type: Slashing\nFirst synthetic effect\n\nDamage Type: Magic\nSecond synthetic effect\n\n"
    )


def test_format_card_keeps_effect_text_verbatim() -> None:
    # Card text is third party data, sent exactly as written, typos included.
    synthetic_card = Card(StrengthTier.SETBACK, (CardEffect("Piercing", "  spaced {braces} %s\r\n"),))

    assert format_card(synthetic_card) == "Damage Type: Piercing\n  spaced {braces} %s\r\n\n\n"
