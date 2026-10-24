"""The typed backup surface: `?newdeck 7`, `?draw`, `?help` and the hidden commands.

Each command hands the guild and the typed text to an action and sends what the
action returns. Prefix replies cannot be ephemeral, so visibility is ignored
here; everything the slash surface shows privately is shown in the channel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from critdeck.commands.actions import (
    CommandResult,
    answer_hidden_command,
    draw_card,
    show_help,
    start_new_deck_from_text,
)
from critdeck.commands.response_strings import HIDDEN_COMMAND_REPLIES
from critdeck.discord_adapter.command_logging import CommandSurface, log_command_result, log_reply_failure

if TYPE_CHECKING:
    from collections.abc import Callable

    from critdeck.core.catalogue import DeckCatalogue
    from critdeck.core.deck_registry import DeckRegistry

HIDDEN_COMMAND_NAMES = tuple(HIDDEN_COMMAND_REPLIES)


def guild_id_of(command_context: commands.Context[Any]) -> int | None:
    return command_context.guild.id if command_context.guild is not None else None


class PrefixCommands(commands.Cog):
    def __init__(
        self,
        deck_registry: DeckRegistry,
        load_deck_catalogue: Callable[[], DeckCatalogue],
        command_prefix: str,
    ) -> None:
        self._deck_registry = deck_registry
        self._load_deck_catalogue = load_deck_catalogue
        self._command_prefix = command_prefix

    # Keyword only, so the whole rest of the message reaches the grammar: the
    # framework would otherwise read `7 8` as 7 and silently drop the 8.
    @commands.command(name="newdeck")
    async def new_deck_command(self, command_context: commands.Context[Any], *, level_text: str = "") -> None:
        command_result = start_new_deck_from_text(
            guild_id_of(command_context), level_text, self._load_deck_catalogue, self._deck_registry
        )
        await self._reply("newdeck", command_context, command_result, len(level_text))

    @commands.command(name="draw")
    async def draw_command(self, command_context: commands.Context[Any]) -> None:
        command_result = draw_card(guild_id_of(command_context), self._deck_registry)
        await self._reply("draw", command_context, command_result, 0)

    @commands.command(name="help")
    async def help_command(self, command_context: commands.Context[Any]) -> None:
        await self._reply("help", command_context, show_help(self._command_prefix), 0)

    @commands.command(name=HIDDEN_COMMAND_NAMES[0], aliases=list(HIDDEN_COMMAND_NAMES[1:]), hidden=True)
    async def hidden_command(self, command_context: commands.Context[Any]) -> None:
        command_result = answer_hidden_command(command_context.message.content, self._command_prefix)
        if command_result is not None:
            await self._reply("hidden", command_context, command_result, 0)

    async def _reply(
        self,
        command_name: str,
        command_context: commands.Context[Any],
        command_result: CommandResult,
        input_length: int,
    ) -> None:
        log_command_result(command_name, CommandSurface.PREFIX, command_result, input_length)
        try:
            await command_context.send(command_result.response.text)
        except discord.HTTPException as reply_error:
            log_reply_failure(command_name, CommandSurface.PREFIX, reply_error)
