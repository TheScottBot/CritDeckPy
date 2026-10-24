"""One deck per guild, held in memory only."""

from __future__ import annotations

import pytest

from critdeck.core.catalogue import StrengthTier
from critdeck.core.deck import NoDeckToDrawFromError
from critdeck.core.deck_registry import DeckRegistry
from tests.conftest import FakeCardShuffler, build_synthetic_card

FIRST_GUILD_ID = 1001
SECOND_GUILD_ID = 2002
THREE_CARDS = tuple(
    build_synthetic_card(StrengthTier.SETBACK, f"card {card_number}") for card_number in range(3)
)


def test_deck_registry_reports_the_card_count_of_a_new_deck() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())

    assert deck_registry.create_deck(FIRST_GUILD_ID, THREE_CARDS) == 3


def test_deck_registry_refuses_to_draw_for_a_guild_with_no_deck() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())

    with pytest.raises(NoDeckToDrawFromError):
        deck_registry.draw_next_card(FIRST_GUILD_ID)


def test_deck_registry_refuses_to_draw_from_an_empty_deck() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(FIRST_GUILD_ID, ())

    with pytest.raises(NoDeckToDrawFromError):
        deck_registry.draw_next_card(FIRST_GUILD_ID)


def test_deck_registry_new_deck_replaces_the_old_one_and_starts_from_its_first_card() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(FIRST_GUILD_ID, THREE_CARDS)
    deck_registry.draw_next_card(FIRST_GUILD_ID)

    deck_registry.create_deck(FIRST_GUILD_ID, THREE_CARDS)

    assert deck_registry.draw_next_card(FIRST_GUILD_ID).card == THREE_CARDS[-1]


def test_deck_registry_empty_new_deck_wipes_the_previous_deck() -> None:
    # The Go bot behaved this way for a negative level: the old deck was replaced
    # by an empty one, and the next draw reported no deck.
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(FIRST_GUILD_ID, THREE_CARDS)

    deck_registry.create_deck(FIRST_GUILD_ID, ())

    with pytest.raises(NoDeckToDrawFromError):
        deck_registry.draw_next_card(FIRST_GUILD_ID)


def test_deck_registry_keeps_each_guild_deck_separate() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(FIRST_GUILD_ID, THREE_CARDS)
    deck_registry.create_deck(SECOND_GUILD_ID, THREE_CARDS[:1])

    first_guild_draws = [deck_registry.draw_next_card(FIRST_GUILD_ID).card for _ in range(2)]
    second_guild_draw = deck_registry.draw_next_card(SECOND_GUILD_ID)

    assert first_guild_draws == [THREE_CARDS[2], THREE_CARDS[1]]
    assert second_guild_draw.card == THREE_CARDS[0]
    assert not second_guild_draw.reshuffled


def test_deck_registry_with_a_deck_in_one_guild_has_none_in_another() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(FIRST_GUILD_ID, THREE_CARDS)

    with pytest.raises(NoDeckToDrawFromError):
        deck_registry.draw_next_card(SECOND_GUILD_ID)
