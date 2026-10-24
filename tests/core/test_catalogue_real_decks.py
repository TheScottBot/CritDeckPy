"""Card counts of the real base deck, which is gitignored third party data.

These run only where `decks/player-deck.json` has been supplied, so they skip in
continuous integration and run on the author's machine.
"""

from __future__ import annotations

import pytest

from critdeck.core.catalogue import StrengthTier, parse_tiered_deck_file
from tests.conftest import REAL_DECK_DIRECTORY

REAL_BASE_DECK_PATH = REAL_DECK_DIRECTORY / "player-deck.json"

pytestmark = pytest.mark.skipif(
    not REAL_BASE_DECK_PATH.is_file(),
    reason="decks/player-deck.json is third party data, gitignored and not supplied here",
)


def test_real_base_deck_card_count_per_strength_tier() -> None:
    real_cards = parse_tiered_deck_file(REAL_BASE_DECK_PATH.read_bytes())

    assert {tier: sum(card.strength is tier for card in real_cards) for tier in StrengthTier} == {
        StrengthTier.SETBACK: 15,
        StrengthTier.DANGEROUS: 15,
        StrengthTier.LIFE_THREATENING: 16,
        StrengthTier.DEADLY: 4,
    }


@pytest.mark.parametrize(
    ("party_level", "expected_card_count"),
    [(0, 15), (4, 15), (5, 30), (8, 30), (9, 46), (12, 46), (13, 50), (20, 50)],
)
def test_real_base_deck_cards_available_at_party_level(party_level: int, expected_card_count: int) -> None:
    real_cards = parse_tiered_deck_file(REAL_BASE_DECK_PATH.read_bytes())

    available_card_count = sum(card.strength.minimum_party_level <= party_level for card in real_cards)

    assert available_card_count == expected_card_count
