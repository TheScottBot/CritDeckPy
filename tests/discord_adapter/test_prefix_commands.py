"""The prefix surface translates messages to actions and results to replies."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import discord
import pytest

from critdeck.commands.response_strings import (
    DIRECT_MESSAGE_TEXT,
    HIDDEN_COMMAND_REPLIES,
    NO_DECK_TEXT,
    PARTY_LEVEL_OUT_OF_RANGE_TEXT,
)
from critdeck.core.card_formatting import format_card
from critdeck.core.catalogue import StrengthTier
from critdeck.core.deck_registry import DeckRegistry
from critdeck.discord_adapter.client import build_bot
from critdeck.discord_adapter.prefix_commands import PrefixCommands
from tests.conftest import (
    FakeCardShuffler,
    FakeDeckCatalogueLoader,
    FakeHttpResponse,
    FakePrefixContext,
    build_deck_catalogue,
    build_synthetic_card,
)

if TYPE_CHECKING:
    from discord.ext import commands

GUILD_ID = 5005
ONE_CARD_PER_TIER = tuple(build_synthetic_card(tier, tier.strength_name) for tier in StrengthTier)


def build_prefix_commands(
    deck_registry: DeckRegistry | None = None, command_prefix: str = "?"
) -> PrefixCommands:
    # Built through the real bot, because the framework attaches the cog to its
    # commands only when the cog is added to a bot.
    critdeck_bot = build_bot(
        command_prefix,
        deck_registry or DeckRegistry(FakeCardShuffler()),
        FakeDeckCatalogueLoader(build_deck_catalogue(ONE_CARD_PER_TIER)),
    )
    asyncio.run(critdeck_bot.setup_hook())
    return cast("PrefixCommands", critdeck_bot.get_cog(PrefixCommands.__cog_name__))


def as_command_context(fake_context: FakePrefixContext) -> commands.Context[Any]:
    # The double provides only what the cog uses; the cast says so to the type checker.
    return cast("commands.Context[Any]", fake_context)


def test_newdeck_builds_the_guild_deck_and_replies_with_its_size() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    prefix_commands = build_prefix_commands(deck_registry)
    fake_context = FakePrefixContext(GUILD_ID, "?newdeck 9")

    asyncio.run(prefix_commands.new_deck_command(as_command_context(fake_context), level_text="9"))

    assert fake_context.sent_texts == ["Crit deck created. It has: 3 cards"]
    assert deck_registry.draw_next_card(GUILD_ID).card.strength is StrengthTier.LIFE_THREATENING


@pytest.mark.parametrize("level_text", ["", "nine", "1 2", "1_2"])
def test_newdeck_with_a_malformed_level_replies_with_the_range(level_text: str) -> None:
    prefix_commands = build_prefix_commands()
    fake_context = FakePrefixContext(GUILD_ID, f"?newdeck {level_text}")

    asyncio.run(prefix_commands.new_deck_command(as_command_context(fake_context), level_text=level_text))

    assert fake_context.sent_texts == [PARTY_LEVEL_OUT_OF_RANGE_TEXT]


def test_newdeck_in_a_direct_message_replies_with_the_server_only_notice() -> None:
    prefix_commands = build_prefix_commands()
    fake_context = FakePrefixContext(None, "?newdeck 7")

    asyncio.run(prefix_commands.new_deck_command(as_command_context(fake_context), level_text="7"))

    assert fake_context.sent_texts == [DIRECT_MESSAGE_TEXT]


def test_draw_sends_the_formatted_card() -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])
    prefix_commands = build_prefix_commands(deck_registry)
    fake_context = FakePrefixContext(GUILD_ID, "?draw")

    asyncio.run(prefix_commands.draw_command(as_command_context(fake_context)))

    assert fake_context.sent_texts == [format_card(ONE_CARD_PER_TIER[0])]


def test_draw_with_no_deck_explains_how_to_make_one() -> None:
    prefix_commands = build_prefix_commands()
    fake_context = FakePrefixContext(GUILD_ID, "?draw")

    asyncio.run(prefix_commands.draw_command(as_command_context(fake_context)))

    assert fake_context.sent_texts == [NO_DECK_TEXT]


def test_help_names_the_configured_prefix_and_works_in_a_direct_message() -> None:
    prefix_commands = build_prefix_commands(command_prefix="cd!")
    fake_context = FakePrefixContext(None, "cd!help", prefix="cd!")

    asyncio.run(prefix_commands.help_command(as_command_context(fake_context)))

    assert len(fake_context.sent_texts) == 1
    assert "`cd!newdeck 7`" in fake_context.sent_texts[0]


@pytest.mark.parametrize(("hidden_command_name", "expected_reply"), list(HIDDEN_COMMAND_REPLIES.items()))
def test_hidden_command_replies_to_an_exact_message(hidden_command_name: str, expected_reply: str) -> None:
    prefix_commands = build_prefix_commands()
    fake_context = FakePrefixContext(GUILD_ID, f"?{hidden_command_name}")

    asyncio.run(prefix_commands.hidden_command(as_command_context(fake_context)))

    assert fake_context.sent_texts == [expected_reply]


def test_hidden_command_stays_silent_for_a_near_miss() -> None:
    prefix_commands = build_prefix_commands()
    hidden_command_name = next(iter(HIDDEN_COMMAND_REPLIES))
    fake_context = FakePrefixContext(GUILD_ID, f"?{hidden_command_name} please")

    asyncio.run(prefix_commands.hidden_command(as_command_context(fake_context)))

    assert fake_context.sent_texts == []


def test_hidden_command_is_registered_hidden_under_every_name() -> None:
    hidden_command = build_prefix_commands().hidden_command

    assert hidden_command.hidden
    assert {hidden_command.name, *hidden_command.aliases} == set(HIDDEN_COMMAND_REPLIES)


def test_every_command_is_logged_by_name_outcome_and_input_length_never_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])
    prefix_commands = build_prefix_commands(deck_registry)
    fake_context = FakePrefixContext(GUILD_ID, "?newdeck 13")
    caplog.set_level(logging.INFO)

    asyncio.run(prefix_commands.new_deck_command(as_command_context(fake_context), level_text="13"))
    asyncio.run(prefix_commands.draw_command(as_command_context(fake_context)))

    assert "command=newdeck surface=prefix outcome=deck_created input_length=2" in caplog.text
    assert "command=draw surface=prefix outcome=card_drawn input_length=0" in caplog.text
    assert "13" not in caplog.text.replace("input_length=2", "")
    for card in ONE_CARD_PER_TIER:
        for effect in card.effects:
            assert effect.value not in caplog.text


def test_a_failed_send_is_logged_by_status_and_code_without_content(caplog: pytest.LogCaptureFixture) -> None:
    send_error = discord.HTTPException(
        FakeHttpResponse(403, "Forbidden"), {"code": 50013, "message": "Missing Permissions"}
    )
    deck_registry = DeckRegistry(FakeCardShuffler())
    deck_registry.create_deck(GUILD_ID, ONE_CARD_PER_TIER[:1])
    prefix_commands = build_prefix_commands(deck_registry)
    fake_context = FakePrefixContext(GUILD_ID, "?draw", send_error=send_error)
    caplog.set_level(logging.INFO)

    asyncio.run(prefix_commands.draw_command(as_command_context(fake_context)))

    assert "reply failed command=draw surface=prefix status=403 discord_code=50013" in caplog.text
    assert ONE_CARD_PER_TIER[0].effects[0].value not in caplog.text
