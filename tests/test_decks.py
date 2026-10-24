"""/newdeck and /draw, the deck they build and the cards they draw (critdeck.cogs.decks)."""

from __future__ import annotations

import logging
import random
from pathlib import PurePosixPath

import discord
import pytest
from discord import app_commands

from critdeck.bot import CritDeckBot
from critdeck.cogs import decks
from critdeck.cogs.decks import Decks, ShuffledDeck, format_card, select_cards_for_party_level
from critdeck.lib.deck_files import (
    MAXIMUM_PARTY_LEVEL,
    MINIMUM_PARTY_LEVEL,
    Card,
    CardEffect,
    DeckFileRejectionReason,
    LeftOutDeckFile,
    StrengthTier,
)
from tests.fakes import (
    ONE_CARD_PER_TIER,
    Ctx,
    FakeCardShuffler,
    Guild,
    build_deck_catalogue,
    build_special_level_deck_bytes,
    build_synthetic_card,
    build_tiered_deck_bytes,
    run,
    write_deck_directory,
)

GUILD = Guild(4004)
OTHER_GUILD = Guild(5005)
# Discord refuses a longer description when commands are synced.
MAXIMUM_DISCORD_DESCRIPTION_LENGTH = 100


@pytest.fixture
def deck_directory(tmp_path):
    return write_deck_directory(
        tmp_path / "decks",
        build_tiered_deck_bytes(["Setback", "Dangerous", "Life Threatening", "Deadly"]),
        special_level_files={"beast.json": build_special_level_deck_bytes(666)},
    )


@pytest.fixture
def decks_cog(deck_directory):
    return Decks(FakeCardShuffler(), deck_directory)


def new_deck(decks_cog: Decks, ctx: Ctx, level: int) -> None:
    run(Decks.new_deck.callback(decks_cog, ctx, level))


def draw(decks_cog: Decks, ctx: Ctx) -> None:
    run(Decks.draw.callback(decks_cog, ctx))


# --- Choosing and drawing cards ---


@pytest.mark.parametrize(
    ("party_level", "expected_tier_count"),
    [(1, 1), (4, 1), (5, 2), (8, 2), (9, 3), (12, 3), (13, 4), (20, 4)],
)
def test_select_cards_includes_every_tier_at_or_below_the_level(party_level, expected_tier_count):
    selected_cards = select_cards_for_party_level(build_deck_catalogue(ONE_CARD_PER_TIER), party_level)

    assert [card.strength for card in selected_cards] == list(StrengthTier)[:expected_tier_count]


def test_select_cards_deals_a_special_level_deck_whole():
    special_cards = (build_synthetic_card(StrengthTier.DEADLY, "the beast"),)

    assert select_cards_for_party_level(build_deck_catalogue(ONE_CARD_PER_TIER, {666: special_cards}), 666) == special_cards


def test_shuffled_deck_draws_every_card_once_then_reshuffles_in_place():
    card_shuffler = FakeCardShuffler()
    shuffled_deck = ShuffledDeck(ONE_CARD_PER_TIER, card_shuffler)

    first_pass = [shuffled_deck.draw_next_card() for _ in ONE_CARD_PER_TIER]
    first_draw_after_exhaustion = shuffled_deck.draw_next_card()

    assert [drawn.card for drawn in first_pass] == list(reversed(ONE_CARD_PER_TIER))
    assert not any(drawn.reshuffled for drawn in first_pass)
    # As in the Go bot: reshuffled on the draw after the last card, from the order in play.
    assert first_draw_after_exhaustion.reshuffled
    assert first_draw_after_exhaustion.card == ONE_CARD_PER_TIER[0]
    assert card_shuffler.shuffle_count == 2


def test_shuffled_deck_leaves_the_cards_it_was_given_alone():
    given_cards = list(ONE_CARD_PER_TIER)

    ShuffledDeck(given_cards, FakeCardShuffler())

    assert given_cards == list(ONE_CARD_PER_TIER)


def test_standard_library_random_can_shuffle_a_deck():
    shuffled_deck = ShuffledDeck(ONE_CARD_PER_TIER, random.Random(7))  # noqa: S311

    assert {shuffled_deck.draw_next_card().card for _ in ONE_CARD_PER_TIER} == set(ONE_CARD_PER_TIER)


def test_format_card_matches_the_go_bot_byte_for_byte():
    card = Card(StrengthTier.DANGEROUS, (CardEffect("Slashing", "First"), CardEffect("Magic", "  {verbatim} %s")))

    assert format_card(card) == "Damage Type: Slashing\nFirst\n\nDamage Type: Magic\n  {verbatim} %s\n\n"


# --- /newdeck ---


def test_newdeck_builds_the_server_deck_and_says_its_size_publicly(decks_cog):
    ctx = Ctx(GUILD)

    new_deck(decks_cog, ctx, 13)

    assert ctx.last.content == "Crit deck created. It has: 4 cards"
    assert not ctx.last.private


@pytest.mark.parametrize("party_level", [MINIMUM_PARTY_LEVEL, MAXIMUM_PARTY_LEVEL, 666])
def test_newdeck_accepts_the_ordinary_bounds_and_a_loaded_special_level(decks_cog, party_level):
    ctx = Ctx(GUILD)

    new_deck(decks_cog, ctx, party_level)

    assert ctx.last.content.startswith("Crit deck created.")


@pytest.mark.parametrize("party_level", [MINIMUM_PARTY_LEVEL - 1, MAXIMUM_PARTY_LEVEL + 1, 667, 10**30])
def test_newdeck_refuses_an_unclaimed_level_privately_and_keeps_the_deck(decks_cog, party_level):
    new_deck(decks_cog, Ctx(GUILD), 1)
    ctx = Ctx(GUILD)

    new_deck(decks_cog, ctx, party_level)
    draw(decks_cog, ctx)

    assert ctx.sent[0].content == decks.PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert ctx.sent[0].private
    assert ctx.sent[1].content.startswith("Damage Type:")


def test_out_of_range_text_names_the_range_and_no_special_level():
    assert f"from {MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}" in decks.PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert "666" not in decks.PARTY_LEVEL_OUT_OF_RANGE_TEXT


def test_newdeck_with_no_base_deck_refuses_privately_and_keeps_the_deck(decks_cog, deck_directory):
    new_deck(decks_cog, Ctx(GUILD), 1)
    (deck_directory / "player-deck.json").unlink()
    ctx = Ctx(GUILD)

    new_deck(decks_cog, ctx, 7)
    draw(decks_cog, ctx)

    assert ctx.sent[0].content == decks.BASE_DECK_UNAVAILABLE_TEXT
    assert ctx.sent[0].private
    assert ctx.sent[1].content.startswith("Damage Type:")


def test_newdeck_picks_up_an_extension_added_since_the_last_deck(decks_cog, deck_directory):
    new_deck(decks_cog, Ctx(GUILD), 13)
    write_deck_directory(deck_directory, None, extension_files={"halloween-extension.json": build_tiered_deck_bytes(["Deadly"])})
    ctx = Ctx(GUILD)

    new_deck(decks_cog, ctx, 13)

    assert ctx.last.content == "Crit deck created. It has: 5 cards"


def test_newdeck_tells_the_table_when_an_extension_was_left_out(decks_cog, deck_directory):
    write_deck_directory(deck_directory, None, extension_files={"broken-extension.json": b'{"cards": ['})
    ctx = Ctx(GUILD)

    new_deck(decks_cog, ctx, 1)

    assert ctx.last.content == "Crit deck created. It has: 1 cards\n" + decks.EXTENSIONS_LEFT_OUT_TEXT


@pytest.mark.parametrize(
    "quietly_left_out_file",
    [
        # Saying a special level file broke would reveal special levels exist.
        LeftOutDeckFile(PurePosixPath("special-levels/beast.json"), DeckFileRejectionReason.MALFORMED_JSON),
        # A stray file was never a deck anyone expected.
        LeftOutDeckFile(PurePosixPath("extensions/notes.txt"), DeckFileRejectionReason.UNEXPECTED_ENTRY),
    ],
)
def test_only_left_out_extensions_are_mentioned_to_the_table(quietly_left_out_file):
    extension_file = LeftOutDeckFile(PurePosixPath("extensions/a.json"), DeckFileRejectionReason.NO_CARDS)
    whole_folder = LeftOutDeckFile(PurePosixPath("extensions"), DeckFileRejectionReason.TOO_MANY_FILES)

    assert decks.any_extension_left_out((extension_file,))
    assert decks.any_extension_left_out((whole_folder,))
    assert not decks.any_extension_left_out((quietly_left_out_file,))


def test_newdeck_logs_the_outcome_and_left_out_files_never_card_text(decks_cog, deck_directory, caplog):
    write_deck_directory(deck_directory, None, extension_files={"broken-extension.json": b"{"})
    caplog.set_level(logging.INFO)

    new_deck(decks_cog, Ctx(GUILD), 13)
    draw(decks_cog, Ctx(GUILD))

    assert "command=newdeck outcome=deck_created card_count=4" in caplog.text
    assert "deck file left out path=extensions/broken-extension.json reason=malformed_json" in caplog.text
    assert "Synthetic" not in caplog.text


# --- /draw ---


def test_draw_sends_the_next_card_publicly(decks_cog):
    new_deck(decks_cog, Ctx(GUILD), 1)
    ctx = Ctx(GUILD)

    draw(decks_cog, ctx)

    assert ctx.last.content.startswith("Damage Type: Bludgeoning\n")
    assert not ctx.last.private


def test_draw_with_no_deck_explains_how_to_make_one_privately(decks_cog):
    ctx = Ctx(GUILD)

    draw(decks_cog, ctx)

    assert ctx.last.content == decks.NO_DECK_TEXT
    assert ctx.last.private


def test_draw_logs_a_reshuffle(decks_cog, caplog):
    new_deck(decks_cog, Ctx(GUILD), 1)
    caplog.set_level(logging.INFO)

    draw(decks_cog, Ctx(GUILD))
    draw(decks_cog, Ctx(GUILD))

    assert caplog.text.count("deck reshuffled") == 1


def test_each_server_has_its_own_deck(decks_cog):
    new_deck(decks_cog, Ctx(GUILD), 1)
    ctx = Ctx(OTHER_GUILD)

    draw(decks_cog, ctx)

    assert ctx.last.content == decks.NO_DECK_TEXT


def test_go_bot_strings_are_kept_word_for_word():
    assert decks.DECK_CREATED_TEXT.format(card_count=50) == "Crit deck created. It has: 50 cards"
    assert decks.DIRECT_MESSAGE_TEXT == "This command only works in a server, not in a direct message."


# --- The frozen slash command contract ---


@pytest.fixture
def command_tree():
    critdeck_bot = CritDeckBot()
    run(critdeck_bot.setup_hook())
    return critdeck_bot.tree


def command_payload(command_tree, command_name):
    slash_command = command_tree.get_command(command_name)
    assert isinstance(slash_command, app_commands.Command)
    return slash_command.to_dict(command_tree)


def test_newdeck_level_is_a_required_integer_with_no_discord_side_bounds(command_tree):
    # A Discord side maximum would stop special levels before the bot saw them.
    (level_option,) = command_payload(command_tree, "newdeck")["options"]

    assert level_option["name"] == "level"
    assert level_option["type"] == discord.AppCommandOptionType.integer.value
    assert level_option["required"]
    assert "min_value" not in level_option
    assert "max_value" not in level_option


@pytest.mark.parametrize("command_name", ["newdeck", "draw"])
def test_deck_commands_are_for_servers_only(command_tree, command_name):
    assert command_payload(command_tree, command_name)["contexts"] == [app_commands.AppCommandContext.GUILD]


@pytest.mark.parametrize("command_name", ["newdeck", "draw", "help"])
def test_every_description_fits_discord_as_written(command_tree, command_name):
    payload = command_payload(command_tree, command_name)
    descriptions = [payload["description"]] + [option["description"] for option in payload.get("options", [])]

    for description in descriptions:
        assert 0 < len(description) <= MAXIMUM_DISCORD_DESCRIPTION_LENGTH
        assert not description.endswith("\N{HORIZONTAL ELLIPSIS}")
