"""Choosing the cards for a party level, and drawing from a shuffled deck."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from critdeck.core.catalogue import Card, DeckCatalogue


class CardShuffler(Protocol):
    # Injected so tests can predict the order. The standard library's
    # random.Random satisfies this as it stands.
    def shuffle(self, cards_to_shuffle: list[Card], /) -> None: ...


class NoDeckToDrawFromError(Exception):
    def __init__(self) -> None:
        super().__init__("no deck to draw from")


@dataclass(frozen=True)
class DrawnCard:
    card: Card
    reshuffled: bool


def select_cards_for_party_level(deck_catalogue: DeckCatalogue, party_level: int) -> tuple[Card, ...]:
    special_level_cards = deck_catalogue.special_level_decks.get(party_level)
    if special_level_cards is not None:
        return special_level_cards
    return tuple(
        card for card in deck_catalogue.tiered_cards if card.strength.minimum_party_level <= party_level
    )


class ShuffledDeck:
    def __init__(self, cards: Sequence[Card], card_shuffler: CardShuffler) -> None:
        self._card_shuffler = card_shuffler
        self._cards_in_play = list(cards)
        self._next_card_index = 0
        self._card_shuffler.shuffle(self._cards_in_play)

    @property
    def card_count(self) -> int:
        return len(self._cards_in_play)

    def draw_next_card(self) -> DrawnCard:
        if not self._cards_in_play:
            raise NoDeckToDrawFromError
        # As in the Go bot, an exhausted deck is reshuffled on the next draw rather
        # than after the last card, so the last card is always seen before it.
        reshuffled = self._next_card_index >= len(self._cards_in_play)
        if reshuffled:
            self._card_shuffler.shuffle(self._cards_in_play)
            self._next_card_index = 0
        drawn_card = self._cards_in_play[self._next_card_index]
        self._next_card_index += 1
        return DrawnCard(drawn_card, reshuffled)
