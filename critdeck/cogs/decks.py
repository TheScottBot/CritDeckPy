"""/newdeck and /draw: one shuffled crit deck per server, built from the deck files.

Decks live in memory only. A restart wiping every deck is deliberate: it is the
guaranteed full reset when something misbehaves.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from discord import app_commands
from discord.ext import commands

from critdeck import config
from critdeck.lib.deck_files import (
    EXTENSIONS_DIRECTORY_NAME,
    MAXIMUM_PARTY_LEVEL,
    MINIMUM_PARTY_LEVEL,
    BaseDeckRejectedError,
    Card,
    DeckCatalogue,
    DeckFileRejectionReason,
    LeftOutDeckFile,
    is_ordinary_party_level,
    load_deck_catalogue,
)

log = logging.getLogger("critdeck")

# From the Go bot, word for word.
DIRECT_MESSAGE_TEXT = "This command only works in a server, not in a direct message."
DECK_CREATED_TEXT = "Crit deck created. It has: {card_count} cards"

NO_DECK_TEXT = "No deck here yet. Create one with /newdeck and the party level, for example /newdeck 7"
# The same text for every refused level, so it gives nothing away about which
# special levels exist.
PARTY_LEVEL_OUT_OF_RANGE_TEXT = (
    f"Please give the party level as a whole number from {MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}."
)
BASE_DECK_UNAVAILABLE_TEXT = (
    "The deck files could not be loaded, so no new deck was made. The current deck is unchanged."
)
EXTENSIONS_LEFT_OUT_TEXT = "Some deck extensions could not be loaded and were left out."

NEW_DECK_DESCRIPTION = "Shuffle a fresh crit deck for this server at a party level."
PARTY_LEVEL_OPTION_DESCRIPTION = f"The party's level, {MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}."
DRAW_DESCRIPTION = "Flip the next card from this server's crit deck."

EXTENSIONS_DIRECTORY_PATH = PurePosixPath(EXTENSIONS_DIRECTORY_NAME)


class CardShuffler(Protocol):
    """Injected so tests can predict the order; random.Random satisfies it as it stands."""

    def shuffle(self, cards_to_shuffle: list[Card], /) -> None: ...


@dataclass(frozen=True)
class DrawnCard:
    card: Card
    reshuffled: bool


def select_cards_for_party_level(deck_catalogue: DeckCatalogue, party_level: int) -> tuple[Card, ...]:
    special_level_cards = deck_catalogue.special_level_decks.get(party_level)
    if special_level_cards is not None:
        return special_level_cards
    return tuple(card for card in deck_catalogue.tiered_cards if card.strength.minimum_party_level <= party_level)


class ShuffledDeck:
    def __init__(self, cards: tuple[Card, ...], card_shuffler: CardShuffler) -> None:
        self.card_shuffler = card_shuffler
        self.cards_in_play = list(cards)
        self.next_card_index = 0
        self.card_shuffler.shuffle(self.cards_in_play)

    @property
    def card_count(self) -> int:
        return len(self.cards_in_play)

    def draw_next_card(self) -> DrawnCard:
        # As in the Go bot, an exhausted deck is reshuffled on the next draw rather
        # than after the last card, so the last card is always seen.
        reshuffled = self.next_card_index >= len(self.cards_in_play)
        if reshuffled:
            self.card_shuffler.shuffle(self.cards_in_play)
            self.next_card_index = 0
        drawn_card = self.cards_in_play[self.next_card_index]
        self.next_card_index += 1
        return DrawnCard(drawn_card, reshuffled)


def format_card(card: Card) -> str:
    # Byte for byte the Go bot's output, trailing blank line included.
    return "".join(f"Damage Type: {effect.damage_type}\n{effect.value}\n\n" for effect in card.effects)


def any_extension_left_out(left_out_files: tuple[LeftOutDeckFile, ...]) -> bool:
    # Only extensions are mentioned to the table. A broken special level stays
    # quiet, because naming it would reveal special levels exist, and a stray
    # non deck file was never something a player expected.
    return any(
        left_out_file.reason is not DeckFileRejectionReason.UNEXPECTED_ENTRY
        and EXTENSIONS_DIRECTORY_PATH in {left_out_file.relative_path, left_out_file.relative_path.parent}
        for left_out_file in left_out_files
    )


def log_left_out_files(left_out_files: tuple[LeftOutDeckFile, ...]) -> None:
    for left_out_file in left_out_files:
        log.warning(
            "deck file left out path=%s reason=%s",
            left_out_file.relative_path.as_posix(),
            left_out_file.reason.name.lower(),
        )


class Decks(commands.Cog):
    def __init__(self, card_shuffler: CardShuffler, deck_directory: Path) -> None:
        self.card_shuffler = card_shuffler
        self.deck_directory = deck_directory
        # No lock: discord.py runs every command on one event loop, and nothing
        # here awaits between reading and writing a server's deck.
        self.decks_by_guild_id: dict[int, ShuffledDeck] = {}

    # The level has no Discord side bounds, which would stop special levels before
    # the bot saw them; the range is checked here instead. Typed, `?newdeck 7 8`
    # is refused rather than read as 7.
    @commands.hybrid_command(name="newdeck", description=NEW_DECK_DESCRIPTION, ignore_extra=False)
    @app_commands.describe(level=PARTY_LEVEL_OPTION_DESCRIPTION)
    # Both are needed: the first makes Discord offer the slash command in servers
    # only, the second refuses the typed command in a direct message.
    @app_commands.guild_only()
    @commands.guild_only()
    async def new_deck(self, ctx: commands.Context, level: int) -> None:
        # Read on every new deck, so an extension added mid campaign is picked up
        # by the next deck without a restart. Loading takes well under a
        # millisecond, far inside Discord's reply deadline.
        try:
            deck_catalogue = load_deck_catalogue(self.deck_directory)
        except BaseDeckRejectedError as base_rejection:
            log.error("base deck rejected reason=%s", base_rejection.reason.name.lower())
            await ctx.send(BASE_DECK_UNAVAILABLE_TEXT, ephemeral=True)
            return
        log_left_out_files(deck_catalogue.left_out_files)

        if not is_ordinary_party_level(level) and level not in deck_catalogue.special_level_decks:
            log.info("command=newdeck refused reason=party_level_out_of_range")
            await ctx.send(PARTY_LEVEL_OUT_OF_RANGE_TEXT, ephemeral=True)
            return

        guild_deck = ShuffledDeck(select_cards_for_party_level(deck_catalogue, level), self.card_shuffler)
        self.decks_by_guild_id[ctx.guild.id] = guild_deck
        log.info("command=newdeck outcome=deck_created card_count=%d", guild_deck.card_count)
        reply_text = DECK_CREATED_TEXT.format(card_count=guild_deck.card_count)
        if any_extension_left_out(deck_catalogue.left_out_files):
            reply_text += "\n" + EXTENSIONS_LEFT_OUT_TEXT
        await ctx.send(reply_text)

    @commands.hybrid_command(name="draw", description=DRAW_DESCRIPTION)
    @app_commands.guild_only()
    @commands.guild_only()
    async def draw(self, ctx: commands.Context) -> None:
        guild_deck = self.decks_by_guild_id.get(ctx.guild.id)
        # A negative level used to build an empty deck in the Go bot; either way
        # there is nothing to draw.
        if guild_deck is None or guild_deck.card_count == 0:
            log.info("command=draw refused reason=no_deck")
            await ctx.send(NO_DECK_TEXT, ephemeral=True)
            return
        drawn_card = guild_deck.draw_next_card()
        if drawn_card.reshuffled:
            log.info("deck reshuffled card_count=%d", guild_deck.card_count)
        await ctx.send(format_card(drawn_card.card))


async def setup(bot: commands.Bot) -> None:
    # Card order is not a security boundary, so the ordinary generator will do.
    await bot.add_cog(Decks(random.Random(), config.DECK_DIRECTORY))  # noqa: S311
