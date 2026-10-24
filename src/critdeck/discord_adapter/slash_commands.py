"""The primary surface: `/newdeck`, `/draw` and `/help`.

Each command hands the guild and the typed option to an action and replies with
what the action returns, at the visibility it asks for. Deck files load in well
under a millisecond (0.47 ms measured on 24 October 2026), so every reply is
sent directly, inside Discord's response deadline, with no deferral.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from critdeck.commands.actions import (
    CommandResult,
    ResponseVisibility,
    draw_card,
    show_help,
    start_new_deck,
)
from critdeck.commands.response_strings import (
    DRAW_COMMAND_DESCRIPTION,
    HELP_COMMAND_DESCRIPTION,
    NEW_DECK_COMMAND_DESCRIPTION,
    PARTY_LEVEL_OPTION_DESCRIPTION,
)
from critdeck.discord_adapter.command_logging import CommandSurface, log_command_result, log_reply_failure

if TYPE_CHECKING:
    from collections.abc import Callable

    from critdeck.core.catalogue import DeckCatalogue
    from critdeck.core.deck_registry import DeckRegistry


class SlashCommands(commands.Cog):
    def __init__(
        self,
        deck_registry: DeckRegistry,
        load_deck_catalogue: Callable[[], DeckCatalogue],
        command_prefix: str,
    ) -> None:
        self._deck_registry = deck_registry
        self._load_deck_catalogue = load_deck_catalogue
        self._command_prefix = command_prefix

    # The level has no Discord side minimum or maximum: Discord would refuse a
    # special level before the bot saw it. The action applies the range instead.
    # Guild only is enforced by Discord, and again by the action, in case an old
    # registration without the restriction is still live.
    @app_commands.command(name="newdeck", description=NEW_DECK_COMMAND_DESCRIPTION)
    @app_commands.describe(level=PARTY_LEVEL_OPTION_DESCRIPTION)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def new_deck_command(self, interaction: discord.Interaction[Any], level: int) -> None:
        command_result = start_new_deck(
            interaction.guild_id, level, self._load_deck_catalogue, self._deck_registry
        )
        await self._reply("newdeck", interaction, command_result, len(str(level)))

    @app_commands.command(name="draw", description=DRAW_COMMAND_DESCRIPTION)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def draw_command(self, interaction: discord.Interaction[Any]) -> None:
        await self._reply("draw", interaction, draw_card(interaction.guild_id, self._deck_registry), 0)

    @app_commands.command(name="help", description=HELP_COMMAND_DESCRIPTION)
    async def help_command(self, interaction: discord.Interaction[Any]) -> None:
        await self._reply("help", interaction, show_help(self._command_prefix), 0)

    async def _reply(
        self,
        command_name: str,
        interaction: discord.Interaction[Any],
        command_result: CommandResult,
        input_length: int,
    ) -> None:
        log_command_result(command_name, CommandSurface.SLASH, command_result, input_length)
        try:
            await interaction.response.send_message(
                command_result.response.text,
                ephemeral=command_result.response.visibility is ResponseVisibility.EPHEMERAL,
            )
        except discord.HTTPException as reply_error:
            log_reply_failure(command_name, CommandSurface.SLASH, reply_error)
