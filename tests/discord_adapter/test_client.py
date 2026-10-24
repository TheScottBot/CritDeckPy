"""The bot is built with the prefix surface, its intents and its error handling."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

from discord.ext import commands

from critdeck.core.catalogue import StrengthTier
from critdeck.core.deck_registry import DeckRegistry
from critdeck.discord_adapter.client import build_bot
from critdeck.discord_adapter.command_sync import CommandSyncPlan
from tests.conftest import (
    FakeCardShuffler,
    FakeDeckCatalogueLoader,
    FakePrefixContext,
    build_deck_catalogue,
    build_synthetic_card,
)

if TYPE_CHECKING:
    import pytest

ONE_CARD_PER_TIER = tuple(build_synthetic_card(tier, tier.strength_name) for tier in StrengthTier)


def build_test_bot(command_prefix: str = "?") -> commands.Bot:
    return build_bot(
        command_prefix,
        DeckRegistry(FakeCardShuffler()),
        FakeDeckCatalogueLoader(build_deck_catalogue(ONE_CARD_PER_TIER)),
        CommandSyncPlan(guild_ids=(), sync_globally=False),
    )


def test_build_bot_requests_message_content_and_no_other_privileged_intent() -> None:
    critdeck_bot = build_test_bot()

    assert critdeck_bot.intents.message_content
    assert not critdeck_bot.intents.members
    assert not critdeck_bot.intents.presences


def test_build_bot_uses_the_configured_prefix_case_insensitively_with_no_default_help() -> None:
    critdeck_bot = build_test_bot("cd!")

    assert critdeck_bot.command_prefix == "cd!"
    assert critdeck_bot.case_insensitive
    assert critdeck_bot.help_command is None


def test_build_bot_registers_the_prefix_commands_when_set_up() -> None:
    critdeck_bot = build_test_bot()

    asyncio.run(critdeck_bot.setup_hook())

    visible_command_names = {command.name for command in critdeck_bot.commands if not command.hidden}
    assert visible_command_names == {"newdeck", "draw", "help"}
    assert critdeck_bot.get_command("NEWDECK") is critdeck_bot.get_command("newdeck")


def test_unknown_prefix_command_is_ignored_without_an_error_log(caplog: pytest.LogCaptureFixture) -> None:
    critdeck_bot = build_test_bot()
    caplog.set_level(logging.DEBUG)

    asyncio.run(
        critdeck_bot.on_command_error(
            cast("commands.Context[Any]", FakePrefixContext(1, "?roll d20")),
            commands.CommandNotFound('Command "roll" is not found'),
        )
    )

    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_unexpected_command_error_is_logged_by_type_without_content(caplog: pytest.LogCaptureFixture) -> None:
    critdeck_bot = build_test_bot()
    caplog.set_level(logging.DEBUG)

    asyncio.run(
        critdeck_bot.on_command_error(
            cast("commands.Context[Any]", FakePrefixContext(1, "?newdeck private-content")),
            commands.CommandError("private-content"),
        )
    )

    assert "command error error_type=CommandError" in caplog.text
    assert "private-content" not in caplog.text
