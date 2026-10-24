"""One shuffled deck per guild, in memory only.

Nothing here is persisted. A restart wiping every deck is deliberate: it is the
author's guaranteed full reset when something misbehaves.

There is no lock. discord.py runs every event and command handler as a task on
one asyncio event loop (discord.py 2.7.1, client.py and app_commands/tree.py),
and no method here awaits, so two calls can never interleave. A caller that
moves this onto a thread must add a lock first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from critdeck.core.deck import CardShuffler, DrawnCard, NoDeckToDrawFromError, ShuffledDeck

if TYPE_CHECKING:
    from collections.abc import Sequence

    from critdeck.core.catalogue import Card


class DeckRegistry:
    def __init__(self, card_shuffler: CardShuffler) -> None:
        self._card_shuffler = card_shuffler
        self._decks_by_guild_id: dict[int, ShuffledDeck] = {}

    def create_deck(self, guild_id: int, cards: Sequence[Card]) -> int:
        new_deck = ShuffledDeck(cards, self._card_shuffler)
        self._decks_by_guild_id[guild_id] = new_deck
        return new_deck.card_count

    def draw_next_card(self, guild_id: int) -> DrawnCard:
        guild_deck = self._decks_by_guild_id.get(guild_id)
        if guild_deck is None:
            raise NoDeckToDrawFromError
        return guild_deck.draw_next_card()
