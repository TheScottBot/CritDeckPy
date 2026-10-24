"""The Discord client: intents, prefix, command registration and error handling."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from critdeck.discord_adapter.prefix_commands import PrefixCommands

if TYPE_CHECKING:
    from collections.abc import Callable

    from critdeck.core.catalogue import DeckCatalogue
    from critdeck.core.deck_registry import DeckRegistry

client_logger = logging.getLogger("critdeck.client")


class CritDeckBot(commands.Bot):
    def __init__(
        self,
        command_prefix: str,
        deck_registry: DeckRegistry,
        load_deck_catalogue: Callable[[], DeckCatalogue],
    ) -> None:
        bot_intents = discord.Intents.default()
        # Privileged, and needed only by the typed backup commands: without it
        # Discord delivers guild messages with empty content. It must also be
        # switched on in the Developer Portal.
        bot_intents.message_content = True
        super().__init__(
            command_prefix=command_prefix,
            intents=bot_intents,
            # The Go bot matched commands in any case, so `?Draw` keeps working.
            case_insensitive=True,
            help_command=None,
        )
        self._prefix_commands = PrefixCommands(deck_registry, load_deck_catalogue, command_prefix)

    async def setup_hook(self) -> None:
        await self.add_cog(self._prefix_commands)

    async def on_command_error(
        self, context: commands.Context[Any], exception: commands.CommandError, /
    ) -> None:
        # Every message that starts with the prefix but names no command lands
        # here. That is ordinary chat, not a fault, so it is not logged.
        if isinstance(exception, commands.CommandNotFound):
            return
        command_name = context.command.qualified_name if context.command is not None else "unknown"
        # The type only: framework error messages can quote what was typed.
        client_logger.error("command error error_type=%s command=%s", type(exception).__name__, command_name)


def build_bot(
    command_prefix: str,
    deck_registry: DeckRegistry,
    load_deck_catalogue: Callable[[], DeckCatalogue],
) -> CritDeckBot:
    return CritDeckBot(command_prefix, deck_registry, load_deck_catalogue)
