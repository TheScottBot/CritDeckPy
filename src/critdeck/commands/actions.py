"""Command actions shared by the slash and prefix surfaces.

Each action takes the guild id (None in a direct message) and validated inputs,
decides everything, and returns what to send, how visibly, and the facts worth
logging. The surfaces only translate, so behaviour, strings and bounds are
defined once here and in the core.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from critdeck.commands.response_strings import (
    BASE_DECK_UNAVAILABLE_TEXT,
    DECK_CREATED_TEXT,
    DIRECT_MESSAGE_TEXT,
    EXTENSIONS_LEFT_OUT_TEXT,
    HELP_TEXT,
    NO_DECK_TEXT,
    PARTY_LEVEL_OUT_OF_RANGE_TEXT,
)
from critdeck.core.card_formatting import format_card
from critdeck.core.catalogue import (
    EXTENSIONS_DIRECTORY_NAME,
    BaseDeckRejectedError,
    DeckCatalogue,
    DeckFileRejectionReason,
    LeftOutDeckFile,
)
from critdeck.core.deck import NoDeckToDrawFromError, select_cards_for_party_level
from critdeck.core.party_levels import is_ordinary_party_level

if TYPE_CHECKING:
    from collections.abc import Callable

    from critdeck.core.deck_registry import DeckRegistry

EXTENSIONS_DIRECTORY_PATH = PurePosixPath(EXTENSIONS_DIRECTORY_NAME)


class ResponseVisibility(enum.Enum):
    # The table needs to see a deck being made and every card drawn; nobody needs
    # to see someone else's mistake or their request for help.
    PUBLIC = "public"
    EPHEMERAL = "ephemeral"


class CommandOutcome(enum.Enum):
    DECK_CREATED = "deck created"
    CARD_DRAWN = "card drawn"
    HELP_SHOWN = "help shown"
    REJECTED_DIRECT_MESSAGE = "rejected: direct message"
    REJECTED_PARTY_LEVEL_OUT_OF_RANGE = "rejected: party level out of range"
    REJECTED_BASE_DECK_UNAVAILABLE = "rejected: base deck unavailable"
    REJECTED_NO_DECK = "rejected: no deck"


@dataclass(frozen=True)
class CommandResponse:
    text: str
    visibility: ResponseVisibility


@dataclass(frozen=True)
class CommandResult:
    response: CommandResponse
    outcome: CommandOutcome
    reshuffled: bool = False
    left_out_files: tuple[LeftOutDeckFile, ...] = ()
    base_deck_rejection_reason: DeckFileRejectionReason | None = None


def start_new_deck(
    guild_id: int | None,
    party_level: int,
    load_deck_catalogue: Callable[[], DeckCatalogue],
    deck_registry: DeckRegistry,
) -> CommandResult:
    if guild_id is None:
        return _direct_message_refusal()
    # Read on every new deck, so an extension added mid campaign is picked up by
    # the next new deck without a restart.
    try:
        deck_catalogue = load_deck_catalogue()
    except BaseDeckRejectedError as base_rejection:
        return CommandResult(
            CommandResponse(BASE_DECK_UNAVAILABLE_TEXT, ResponseVisibility.EPHEMERAL),
            CommandOutcome.REJECTED_BASE_DECK_UNAVAILABLE,
            base_deck_rejection_reason=base_rejection.reason,
        )
    if not is_ordinary_party_level(party_level) and party_level not in deck_catalogue.special_level_decks:
        return CommandResult(
            CommandResponse(PARTY_LEVEL_OUT_OF_RANGE_TEXT, ResponseVisibility.EPHEMERAL),
            CommandOutcome.REJECTED_PARTY_LEVEL_OUT_OF_RANGE,
            left_out_files=deck_catalogue.left_out_files,
        )

    card_count = deck_registry.create_deck(
        guild_id, select_cards_for_party_level(deck_catalogue, party_level)
    )
    response_text = DECK_CREATED_TEXT.format(card_count=card_count)
    if _any_extension_left_out(deck_catalogue.left_out_files):
        response_text += "\n" + EXTENSIONS_LEFT_OUT_TEXT
    return CommandResult(
        CommandResponse(response_text, ResponseVisibility.PUBLIC),
        CommandOutcome.DECK_CREATED,
        left_out_files=deck_catalogue.left_out_files,
    )


def draw_card(guild_id: int | None, deck_registry: DeckRegistry) -> CommandResult:
    if guild_id is None:
        return _direct_message_refusal()
    try:
        drawn_card = deck_registry.draw_next_card(guild_id)
    except NoDeckToDrawFromError:
        return CommandResult(
            CommandResponse(NO_DECK_TEXT, ResponseVisibility.EPHEMERAL), CommandOutcome.REJECTED_NO_DECK
        )
    return CommandResult(
        CommandResponse(format_card(drawn_card.card), ResponseVisibility.PUBLIC),
        CommandOutcome.CARD_DRAWN,
        reshuffled=drawn_card.reshuffled,
    )


def show_help(command_prefix: str) -> CommandResult:
    return CommandResult(
        CommandResponse(HELP_TEXT.format(command_prefix=command_prefix), ResponseVisibility.EPHEMERAL),
        CommandOutcome.HELP_SHOWN,
    )


def _direct_message_refusal() -> CommandResult:
    return CommandResult(
        CommandResponse(DIRECT_MESSAGE_TEXT, ResponseVisibility.EPHEMERAL),
        CommandOutcome.REJECTED_DIRECT_MESSAGE,
    )


def _any_extension_left_out(left_out_files: tuple[LeftOutDeckFile, ...]) -> bool:
    # Only extensions are mentioned to the table. A broken special level stays
    # quiet because naming it would reveal special levels exist, and a stray
    # non deck file was never something a player expected.
    return any(
        left_out_file.reason is not DeckFileRejectionReason.UNEXPECTED_ENTRY
        and EXTENSIONS_DIRECTORY_PATH in {left_out_file.relative_path, left_out_file.relative_path.parent}
        for left_out_file in left_out_files
    )
