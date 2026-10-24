"""The slash surface: command definitions, translation to actions, replies."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import discord
import pytest
from discord import app_commands

from critdeck.commands.response_strings import (
    DIRECT_MESSAGE_TEXT,
    NO_DECK_TEXT,
    PARTY_LEVEL_OUT_OF_RANGE_TEXT,
)
from critdeck.core.card_formatting import format_card
from critdeck.core.catalogue import StrengthTier
from critdeck.core.deck_registry import DeckRegistry
from critdeck.core.party_levels import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL
from critdeck.discord_adapter.client import build_bot
from critdeck.discord_adapter.command_sync import CommandSyncPlan
from critdeck.discord_adapter.slash_commands import SlashCommands
from tests.conftest import (
    FakeCardShuffler,
    FakeDeckCatalogueLoader,
    FakeInteraction,
    build_deck_catalogue,
    build_fake_http_response,
    build_synthetic_card,
)

if TYPE_CHECKING:
    from discord.ext import commands

GUILD_ID = 6006
ONE_CARD_PER_TIER = tuple(build_synthetic_card(tier, tier.strength_name) for tier in StrengthTier)
SPECIAL_CARD = build_synthetic_card(StrengthTier.DEADLY, "special")
# Discord rejects a longer description when commands are synced, and discord.py
# silently shortens some, so every description must fit as written.
MAXIMUM_DISCORD_DESCRIPTION_LENGTH = 100


def build_set_up_bot(deck_registry: DeckRegistry | None = None) -> commands.Bot:
    critdeck_bot = build_bot(
        "?",
        deck_registry or DeckRegistry(FakeCardShuffler()),
        FakeDeckCatalogueLoader(build_deck_catalogue(ONE_CARD_PER_TIER, {666: (SPECIAL_CARD,)})),
        CommandSyncPlan(guild_ids=(), sync_globally=False),
    )
    asyncio.run(critdeck_bot.setup_hook())
    return critdeck_bot


def build_slash_commands(deck_registry: DeckRegistry | None = None) -> SlashCommands:
    return cast("SlashCommands", build_set_up_bot(deck_registry).get_cog(SlashCommands.__cog_name__))


def as_interaction(fake_interaction: FakeInteraction) -> discord.Interaction[Any]:
    # The double provides only what the cog uses; the cast says so to the type checker.
    return cast("discord.Interaction[Any]", fake_interaction)


async def call_slash_command(
    slash_command: app_commands.Command[Any, ..., Any], *callback_arguments: object
) -> None:
    # discord.py types an app command's callback as a union of its bound and
    # unbound forms, which mypy cannot match to either call; this is the one
    # place that says so.
    await slash_command.callback(*callback_arguments)  # type: ignore[arg-type]


def slash_command_payload(command_name: str) -> dict[str, Any]:
    critdeck_bot = build_set_up_bot()
    slash_command = critdeck_bot.tree.get_command(command_name)
    assert isinstance(slash_command, app_commands.Command)
    return slash_command.to_dict(critdeck_bot.tree)


def test_tree_holds_exactly_newdeck_draw_and_help() -> None:
    critdeck_bot = build_set_up_bot()

    assert {slash_command.name for slash_command in critdeck_bot.tree.get_commands()} == {
        "newdeck",
        "draw",
        "help",
    }


def test_newdeck_level_option_is_a_required_integer_with_no_discord_side_bounds() -> None:
    # A Discord side maximum would stop special levels before the bot sees them.
    (level_option,) = slash_command_payload("newdeck")["options"]

    assert level_option["name"] == "level"
    assert level_option["type"] == discord.AppCommandOptionType.integer.value
    assert level_option["required"]
    assert "min_value" not in level_option
    assert "max_value" not in level_option
    assert f"{MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}" in level_option["description"]


@pytest.mark.parametrize("command_name", ["newdeck", "draw"])
def test_deck_commands_are_allowed_in_guilds_only(command_name: str) -> None:
    assert slash_command_payload(command_name)["contexts"] == [app_commands.AppCommandContext.GUILD]


def test_help_is_allowed_everywhere() -> None:
    assert slash_command_payload("help").get("contexts") is None


@pytest.mark.parametrize("command_name", ["newdeck", "draw", "help"])
def test_every_description_fits_discord_without_being_shortened(command_name: str) -> None:
    command_payload = slash_command_payload(command_name)
    descriptions = [command_payload["description"]] + [
        option["description"] for option in command_payload.get("options", [])
    ]

    for description in descriptions:
        assert 0 < len(description) <= MAXIMUM_DISCORD_DESCRIPTION_LENGTH
        assert not description.endswith("\N{HORIZONTAL ELLIPSIS}")


def test_newdeck_builds_the_guild_deck_and_replies_publicly() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    slash_commands = build_slash_commands(deck_registry)
    fake_interaction = FakeInteraction(GUILD_ID)

    asyncio.run(
        call_slash_command(
            slash_commands.new_deck_command, slash_commands, as_interaction(fake_interaction), 13
        )
    )

    assert fake_interaction.response.sent_replies == [("Crit deck created. It has: 4 cards", False)]
    assert deck_registry.draw_next_card(GUILD_ID).card.strength is StrengthTier.DEADLY


def test_newdeck_accepts_a_loaded_special_level() -> None:
    slash_commands = build_slash_commands()
    fake_interaction = FakeInteraction(GUILD_ID)

    asyncio.run(
        call_slash_command(
            slash_commands.new_deck_command, slash_commands, as_interaction(fake_interaction), 666
        )
    )

    assert fake_interaction.response.sent_replies == [("Crit deck created. It has: 1 cards", False)]


@pytest.mark.parametrize("party_level", [MINIMUM_PARTY_LEVEL - 1, MAXIMUM_PARTY_LEVEL + 1, 667])
def test_newdeck_refuses_an_unclaimed_level_privately(party_level: int) -> None:
    slash_commands = build_slash_commands()
    fake_interaction = FakeInteraction(GUILD_ID)

    asyncio.run(
        call_slash_command(
            slash_commands.new_deck_command, slash_commands, as_interaction(fake_interaction), party_level
        )
    )

    assert fake_interaction.response.sent_replies == [(PARTY_LEVEL_OUT_OF_RANGE_TEXT, True)]


def test_newdeck_without_a_guild_replies_privately_with_the_server_only_notice() -> None:
    # Discord should never deliver this, since the command is guild only; the
    # action's own check is the defence for a stale command registration.
    slash_commands = build_slash_commands()
    fake_interaction = FakeInteraction(None)

    asyncio.run(
        call_slash_command(
            slash_commands.new_deck_command, slash_commands, as_interaction(fake_interaction), 7
        )
    )

    assert fake_interaction.response.sent_replies == [(DIRECT_MESSAGE_TEXT, True)]


def test_draw_replies_publicly_with_the_card() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])
    slash_commands = build_slash_commands(deck_registry)
    fake_interaction = FakeInteraction(GUILD_ID)

    asyncio.run(
        call_slash_command(slash_commands.draw_command, slash_commands, as_interaction(fake_interaction))
    )

    assert fake_interaction.response.sent_replies == [(format_card(ONE_CARD_PER_TIER[0]), False)]


def test_draw_with_no_deck_replies_privately() -> None:
    slash_commands = build_slash_commands()
    fake_interaction = FakeInteraction(GUILD_ID)

    asyncio.run(
        call_slash_command(slash_commands.draw_command, slash_commands, as_interaction(fake_interaction))
    )

    assert fake_interaction.response.sent_replies == [(NO_DECK_TEXT, True)]


def test_help_replies_privately_and_works_without_a_guild() -> None:
    slash_commands = build_slash_commands()
    fake_interaction = FakeInteraction(None)

    asyncio.run(
        call_slash_command(slash_commands.help_command, slash_commands, as_interaction(fake_interaction))
    )

    ((help_text, ephemeral),) = fake_interaction.response.sent_replies
    assert ephemeral
    assert "`?newdeck 7`" in help_text


def test_slash_commands_are_logged_by_name_outcome_and_input_length(caplog: pytest.LogCaptureFixture) -> None:
    slash_commands = build_slash_commands()
    caplog.set_level(logging.INFO)

    asyncio.run(
        call_slash_command(
            slash_commands.new_deck_command, slash_commands, as_interaction(FakeInteraction(GUILD_ID)), 13
        )
    )

    assert "command=newdeck surface=slash outcome=deck_created input_length=2" in caplog.text


def test_a_missed_response_deadline_is_logged_without_content(caplog: pytest.LogCaptureFixture) -> None:
    # Discord answers a reply sent after the deadline with 404 and code 10062,
    # as seen in the test server on 24 October 2026.
    deadline_missed = discord.NotFound(
        build_fake_http_response(404, "Not Found"), {"code": 10062, "message": "Unknown interaction"}
    )
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])
    slash_commands = build_slash_commands(deck_registry)
    caplog.set_level(logging.INFO)

    asyncio.run(
        call_slash_command(
            slash_commands.draw_command,
            slash_commands,
            as_interaction(FakeInteraction(GUILD_ID, send_error=deadline_missed)),
        )
    )

    assert "reply failed command=draw surface=slash status=404 discord_code=10062" in caplog.text
    assert ONE_CARD_PER_TIER[0].effects[0].value not in caplog.text
