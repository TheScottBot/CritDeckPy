"""The transport free command actions every surface calls."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from critdeck.commands.actions import (
    CommandOutcome,
    ResponseVisibility,
    answer_hidden_command,
    draw_card,
    show_help,
    start_new_deck,
    start_new_deck_from_text,
)
from critdeck.commands.response_strings import (
    BASE_DECK_UNAVAILABLE_TEXT,
    DECK_CREATED_TEXT,
    DIRECT_MESSAGE_TEXT,
    EXTENSIONS_LEFT_OUT_TEXT,
    HIDDEN_COMMAND_REPLIES,
    NO_DECK_TEXT,
    PARTY_LEVEL_OUT_OF_RANGE_TEXT,
)
from critdeck.core.card_formatting import format_card
from critdeck.core.catalogue import (
    BaseDeckRejectedError,
    DeckCatalogue,
    DeckFileRejectionReason,
    LeftOutDeckFile,
    StrengthTier,
)
from critdeck.core.deck_registry import DeckRegistry
from critdeck.core.party_levels import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL
from tests.conftest import (
    FakeCardShuffler,
    FakeDeckCatalogueLoader,
    build_deck_catalogue,
    build_synthetic_card,
)

GUILD_ID = 4004
ONE_CARD_PER_TIER = tuple(build_synthetic_card(tier, tier.strength_name) for tier in StrengthTier)
SPECIAL_CARD = build_synthetic_card(StrengthTier.DEADLY, "special")
STANDARD_CATALOGUE = build_deck_catalogue(ONE_CARD_PER_TIER, {666: (SPECIAL_CARD,), -1: (SPECIAL_CARD,)})


def catalogue_with_left_out_files(*left_out_files: LeftOutDeckFile) -> DeckCatalogue:
    return DeckCatalogue(
        tiered_cards=ONE_CARD_PER_TIER,
        special_level_decks={},
        loaded_files=(PurePosixPath("player-deck.json"),),
        left_out_files=left_out_files,
    )


def test_start_new_deck_builds_a_deck_and_replies_publicly_with_its_size() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())

    command_result = start_new_deck(GUILD_ID, 9, FakeDeckCatalogueLoader(STANDARD_CATALOGUE), deck_registry)

    assert command_result.outcome is CommandOutcome.DECK_CREATED
    assert command_result.response.text == DECK_CREATED_TEXT.format(card_count=3)
    assert command_result.response.text == "Crit deck created. It has: 3 cards"
    assert command_result.response.visibility is ResponseVisibility.PUBLIC
    assert deck_registry.draw_next_card(GUILD_ID).card.strength is StrengthTier.LIFE_THREATENING


def test_start_new_deck_in_a_direct_message_refuses_without_loading_anything() -> None:
    deck_catalogue_loader = FakeDeckCatalogueLoader(STANDARD_CATALOGUE)

    command_result = start_new_deck(None, 7, deck_catalogue_loader, DeckRegistry(FakeCardShuffler()))

    assert command_result.outcome is CommandOutcome.REJECTED_DIRECT_MESSAGE
    assert command_result.response.text == DIRECT_MESSAGE_TEXT
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL
    assert deck_catalogue_loader.load_count == 0


@pytest.mark.parametrize("party_level", [MINIMUM_PARTY_LEVEL, MAXIMUM_PARTY_LEVEL, 666, -1])
def test_start_new_deck_accepts_ordinary_bounds_and_loaded_special_levels(party_level: int) -> None:
    command_result = start_new_deck(
        GUILD_ID, party_level, FakeDeckCatalogueLoader(STANDARD_CATALOGUE), DeckRegistry(FakeCardShuffler())
    )

    assert command_result.outcome is CommandOutcome.DECK_CREATED


@pytest.mark.parametrize("party_level", [MINIMUM_PARTY_LEVEL - 1, MAXIMUM_PARTY_LEVEL + 1, 667, 10**30])
def test_start_new_deck_refuses_a_level_outside_the_range_and_keeps_the_current_deck(
    party_level: int,
) -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER)

    command_result = start_new_deck(
        GUILD_ID, party_level, FakeDeckCatalogueLoader(STANDARD_CATALOGUE), deck_registry
    )

    assert command_result.outcome is CommandOutcome.REJECTED_PARTY_LEVEL_OUT_OF_RANGE
    assert command_result.response.text == PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL
    assert deck_registry.draw_next_card(GUILD_ID).card == ONE_CARD_PER_TIER[-1]


def test_out_of_range_text_names_the_ordinary_range_and_no_special_level() -> None:
    # The same refusal for every unclaimed level, so it gives nothing away about
    # which special levels exist.
    assert str(MINIMUM_PARTY_LEVEL) in PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert str(MAXIMUM_PARTY_LEVEL) in PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert "666" not in PARTY_LEVEL_OUT_OF_RANGE_TEXT


def test_start_new_deck_with_an_unusable_base_refuses_and_keeps_the_current_deck() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER)
    failing_loader = FakeDeckCatalogueLoader(
        error=BaseDeckRejectedError(DeckFileRejectionReason.MALFORMED_JSON)
    )

    command_result = start_new_deck(GUILD_ID, 7, failing_loader, deck_registry)

    assert command_result.outcome is CommandOutcome.REJECTED_BASE_DECK_UNAVAILABLE
    assert command_result.response.text == BASE_DECK_UNAVAILABLE_TEXT
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL
    assert command_result.base_deck_rejection_reason is DeckFileRejectionReason.MALFORMED_JSON
    assert deck_registry.draw_next_card(GUILD_ID).card == ONE_CARD_PER_TIER[-1]


def test_start_new_deck_says_when_an_extension_was_left_out() -> None:
    left_out_extension = LeftOutDeckFile(
        PurePosixPath("extensions/halloween-extension.json"), DeckFileRejectionReason.MALFORMED_JSON
    )

    command_result = start_new_deck(
        GUILD_ID,
        MINIMUM_PARTY_LEVEL,
        FakeDeckCatalogueLoader(catalogue_with_left_out_files(left_out_extension)),
        DeckRegistry(FakeCardShuffler()),
    )

    assert command_result.response.text == (
        DECK_CREATED_TEXT.format(card_count=1) + "\n" + EXTENSIONS_LEFT_OUT_TEXT
    )
    assert command_result.left_out_files == (left_out_extension,)


def test_start_new_deck_says_when_the_whole_extensions_folder_was_left_out() -> None:
    left_out_folder = LeftOutDeckFile(PurePosixPath("extensions"), DeckFileRejectionReason.TOO_MANY_FILES)

    command_result = start_new_deck(
        GUILD_ID,
        MINIMUM_PARTY_LEVEL,
        FakeDeckCatalogueLoader(catalogue_with_left_out_files(left_out_folder)),
        DeckRegistry(FakeCardShuffler()),
    )

    assert command_result.response.text.endswith(EXTENSIONS_LEFT_OUT_TEXT)


@pytest.mark.parametrize(
    "quietly_left_out_file",
    [
        # A broken special level is not mentioned to the table: saying so would
        # reveal that special levels exist.
        LeftOutDeckFile(PurePosixPath("special-levels/beast.json"), DeckFileRejectionReason.MALFORMED_JSON),
        # A stray file is not a deck, so nothing a player expected is missing.
        LeftOutDeckFile(PurePosixPath("extensions/notes.txt"), DeckFileRejectionReason.UNEXPECTED_ENTRY),
        LeftOutDeckFile(PurePosixPath("desktop.ini"), DeckFileRejectionReason.UNEXPECTED_ENTRY),
    ],
)
def test_start_new_deck_does_not_tell_the_table_about_other_left_out_files(
    quietly_left_out_file: LeftOutDeckFile,
) -> None:
    command_result = start_new_deck(
        GUILD_ID,
        MINIMUM_PARTY_LEVEL,
        FakeDeckCatalogueLoader(catalogue_with_left_out_files(quietly_left_out_file)),
        DeckRegistry(FakeCardShuffler()),
    )

    assert command_result.response.text == DECK_CREATED_TEXT.format(card_count=1)
    assert command_result.left_out_files == (quietly_left_out_file,)


def test_draw_card_replies_publicly_with_the_formatted_card() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])

    command_result = draw_card(GUILD_ID, deck_registry)

    assert command_result.outcome is CommandOutcome.CARD_DRAWN
    assert command_result.response.text == format_card(ONE_CARD_PER_TIER[0])
    assert command_result.response.visibility is ResponseVisibility.PUBLIC
    assert not command_result.reshuffled


def test_draw_card_reports_a_reshuffle() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])
    draw_card(GUILD_ID, deck_registry)

    assert draw_card(GUILD_ID, deck_registry).reshuffled


def test_draw_card_with_no_deck_explains_how_to_make_one() -> None:
    command_result = draw_card(GUILD_ID, DeckRegistry(FakeCardShuffler()))

    assert command_result.outcome is CommandOutcome.REJECTED_NO_DECK
    assert command_result.response.text == NO_DECK_TEXT
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL


def test_draw_card_with_an_empty_deck_explains_how_to_make_one() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ())

    assert draw_card(GUILD_ID, deck_registry).outcome is CommandOutcome.REJECTED_NO_DECK


def test_draw_card_in_a_direct_message_refuses() -> None:
    command_result = draw_card(None, DeckRegistry(FakeCardShuffler()))

    assert command_result.outcome is CommandOutcome.REJECTED_DIRECT_MESSAGE
    assert command_result.response.text == DIRECT_MESSAGE_TEXT
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL


@pytest.mark.parametrize("command_prefix", ["?", "!", "cd!"])
def test_show_help_is_private_and_names_the_configured_prefix(command_prefix: str) -> None:
    command_result = show_help(command_prefix)

    assert command_result.outcome is CommandOutcome.HELP_SHOWN
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL
    assert f"{command_prefix}newdeck 7" in command_result.response.text
    for slash_command in ("/newdeck", "/draw", "/help"):
        assert slash_command in command_result.response.text
    assert f"{MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}" in command_result.response.text


def test_deck_created_and_direct_message_text_match_the_go_bot() -> None:
    assert DECK_CREATED_TEXT.format(card_count=50) == "Crit deck created. It has: 50 cards"
    assert DIRECT_MESSAGE_TEXT == "This command only works in a server, not in a direct message."


def test_show_help_names_each_tier_from_the_level_it_joins() -> None:
    help_text = show_help("?").response.text

    for tier in StrengthTier:
        if tier.minimum_party_level > MINIMUM_PARTY_LEVEL:
            assert f"{tier.strength_name} from {tier.minimum_party_level}" in help_text


def test_show_help_formats_commands_as_code() -> None:
    help_text = show_help("?").response.text

    for command_usage in ("`/newdeck level`", "`/draw`", "`/help`", "`?newdeck 7`"):
        assert command_usage in help_text


def test_start_new_deck_from_text_builds_a_deck_from_a_valid_level() -> None:
    command_result = start_new_deck_from_text(
        GUILD_ID, "9", FakeDeckCatalogueLoader(STANDARD_CATALOGUE), DeckRegistry(FakeCardShuffler())
    )

    assert command_result.outcome is CommandOutcome.DECK_CREATED


@pytest.mark.parametrize("level_text", ["", "nine", "1_2", "7 8"])
def test_start_new_deck_from_text_refuses_malformed_text_with_the_range_message(level_text: str) -> None:
    deck_catalogue_loader = FakeDeckCatalogueLoader(STANDARD_CATALOGUE)

    command_result = start_new_deck_from_text(
        GUILD_ID, level_text, deck_catalogue_loader, DeckRegistry(FakeCardShuffler())
    )

    assert command_result.outcome is CommandOutcome.REJECTED_MALFORMED_PARTY_LEVEL
    assert command_result.response.text == PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert command_result.response.visibility is ResponseVisibility.EPHEMERAL
    assert deck_catalogue_loader.load_count == 0


def test_start_new_deck_from_text_in_a_direct_message_refuses_before_reading_the_level() -> None:
    command_result = start_new_deck_from_text(
        None, "nine", FakeDeckCatalogueLoader(STANDARD_CATALOGUE), DeckRegistry(FakeCardShuffler())
    )

    assert command_result.outcome is CommandOutcome.REJECTED_DIRECT_MESSAGE


@pytest.mark.parametrize(("hidden_command_name", "expected_reply"), list(HIDDEN_COMMAND_REPLIES.items()))
def test_answer_hidden_command_replies_to_the_exact_message(
    hidden_command_name: str, expected_reply: str
) -> None:
    command_result = answer_hidden_command(f"?{hidden_command_name}", "?")

    assert command_result is not None
    assert command_result.outcome is CommandOutcome.HIDDEN_COMMAND_ANSWERED
    assert command_result.response.text == expected_reply
    assert command_result.response.visibility is ResponseVisibility.PUBLIC


@pytest.mark.parametrize("hidden_command_name", list(HIDDEN_COMMAND_REPLIES))
def test_answer_hidden_command_stays_silent_unless_the_message_is_exact(hidden_command_name: str) -> None:
    # The Go bot matched these exactly, case included, and nothing else.
    near_misses = [
        f"?{hidden_command_name.swapcase()}",
        f"?{hidden_command_name} now",
        f" ?{hidden_command_name}",
        f"!{hidden_command_name}",
    ]

    for near_miss in near_misses:
        assert answer_hidden_command(near_miss, "?") is None


def test_answer_hidden_command_follows_the_configured_prefix() -> None:
    hidden_command_name = next(iter(HIDDEN_COMMAND_REPLIES))

    assert answer_hidden_command(f"cd!{hidden_command_name}", "cd!") is not None
    assert answer_hidden_command(f"?{hidden_command_name}", "cd!") is None


def test_hidden_command_replies_match_the_go_bot() -> None:
    assert HIDDEN_COMMAND_REPLIES == {
        "mrbigdice": "Just pick a number and that's your roll",
        "drbigdice": "Your dice roll factorial!",
        "DMDICE": "25",
        "spray": "https://klipy.com/gifs/spray-bottle-3",
    }


def test_hidden_commands_never_appear_in_help() -> None:
    help_text = show_help("?").response.text

    for hidden_command_name in HIDDEN_COMMAND_REPLIES:
        assert hidden_command_name.lower() not in help_text.lower()
