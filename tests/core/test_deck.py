"""Card selection by party level, and drawing from a shuffled deck."""

from __future__ import annotations

import random

import pytest

from critdeck.core.catalogue import StrengthTier
from critdeck.core.deck import (
    CardShuffler,
    NoDeckToDrawFromError,
    ShuffledDeck,
    select_cards_for_party_level,
)
from tests.conftest import FakeCardShuffler, build_deck_catalogue, build_synthetic_card

ONE_CARD_PER_TIER = tuple(build_synthetic_card(tier, tier.strength_name) for tier in StrengthTier)


@pytest.mark.parametrize(
    ("party_level", "expected_tiers"),
    [
        (0, [StrengthTier.SETBACK]),
        (4, [StrengthTier.SETBACK]),
        (5, [StrengthTier.SETBACK, StrengthTier.DANGEROUS]),
        (8, [StrengthTier.SETBACK, StrengthTier.DANGEROUS]),
        (9, [StrengthTier.SETBACK, StrengthTier.DANGEROUS, StrengthTier.LIFE_THREATENING]),
        (12, [StrengthTier.SETBACK, StrengthTier.DANGEROUS, StrengthTier.LIFE_THREATENING]),
        (13, list(StrengthTier)),
        (99, list(StrengthTier)),
    ],
)
def test_select_cards_for_party_level_includes_every_tier_at_or_below_the_level(
    party_level: int, expected_tiers: list[StrengthTier]
) -> None:
    selected_cards = select_cards_for_party_level(build_deck_catalogue(ONE_CARD_PER_TIER), party_level)

    assert [card.strength for card in selected_cards] == expected_tiers


def test_select_cards_for_party_level_gives_no_cards_below_zero() -> None:
    # The Go bot built an empty deck for a negative level; the bound on levels is
    # applied before this point, by the command actions.
    assert select_cards_for_party_level(build_deck_catalogue(ONE_CARD_PER_TIER), -1) == ()


def test_select_cards_for_party_level_deals_a_special_level_deck_whole() -> None:
    special_cards = (build_synthetic_card(StrengthTier.DEADLY, "the beast"),)
    deck_catalogue = build_deck_catalogue(ONE_CARD_PER_TIER, {666: special_cards, -1: ONE_CARD_PER_TIER[:1]})

    assert select_cards_for_party_level(deck_catalogue, 666) == special_cards
    assert select_cards_for_party_level(deck_catalogue, -1) == ONE_CARD_PER_TIER[:1]


def test_shuffled_deck_shuffles_once_when_created_and_leaves_the_input_alone() -> None:
    card_shuffler = FakeCardShuffler()
    input_cards = list(ONE_CARD_PER_TIER)

    shuffled_deck = ShuffledDeck(input_cards, card_shuffler)

    assert card_shuffler.shuffle_count == 1
    assert shuffled_deck.card_count == len(ONE_CARD_PER_TIER)
    assert input_cards == list(ONE_CARD_PER_TIER)


def test_shuffled_deck_draws_every_card_once_then_reshuffles_and_starts_again() -> None:
    card_shuffler = FakeCardShuffler()
    shuffled_deck = ShuffledDeck(ONE_CARD_PER_TIER, card_shuffler)

    first_pass = [shuffled_deck.draw_next_card() for _ in ONE_CARD_PER_TIER]

    assert [drawn_card.card for drawn_card in first_pass] == list(reversed(ONE_CARD_PER_TIER))
    assert not any(drawn_card.reshuffled for drawn_card in first_pass)
    assert card_shuffler.shuffle_count == 1

    first_draw_after_exhaustion = shuffled_deck.draw_next_card()

    # The reshuffle happens on the draw after the last card, as in the Go bot,
    # and reshuffles the order already in play.
    assert first_draw_after_exhaustion.reshuffled
    assert card_shuffler.shuffle_count == 2
    assert first_draw_after_exhaustion.card == ONE_CARD_PER_TIER[0]


def test_shuffled_deck_of_one_card_reshuffles_on_every_draw_after_the_first() -> None:
    card_shuffler = FakeCardShuffler()
    shuffled_deck = ShuffledDeck(ONE_CARD_PER_TIER[:1], card_shuffler)

    drawn_cards = [shuffled_deck.draw_next_card() for _ in range(3)]

    assert [drawn_card.reshuffled for drawn_card in drawn_cards] == [False, True, True]
    assert {drawn_card.card for drawn_card in drawn_cards} == {ONE_CARD_PER_TIER[0]}


def test_shuffled_deck_with_no_cards_refuses_to_draw() -> None:
    empty_deck = ShuffledDeck((), FakeCardShuffler())

    with pytest.raises(NoDeckToDrawFromError):
        empty_deck.draw_next_card()


def test_standard_library_random_satisfies_the_card_shuffler_protocol() -> None:
    standard_random: CardShuffler = random.Random(7)  # noqa: S311  # card order is not a security boundary
    shuffled_deck = ShuffledDeck(ONE_CARD_PER_TIER, standard_random)

    drawn_cards = {shuffled_deck.draw_next_card().card for _ in ONE_CARD_PER_TIER}

    assert drawn_cards == set(ONE_CARD_PER_TIER)
