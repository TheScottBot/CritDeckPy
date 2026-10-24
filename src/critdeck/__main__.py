"""Starting CritDeck: `python -m critdeck`, or the `critdeck` command.

Configuration is read first, then logging is set up, then the base deck is
checked, all before Discord is contacted, so a broken install fails at once with
a plain reason instead of on the first command.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import random
import sys
from pathlib import Path

import discord

from critdeck.configuration import ConfigurationError, load_configuration
from critdeck.core.catalogue import BaseDeckRejectedError, load_deck_catalogue
from critdeck.core.deck_registry import DeckRegistry
from critdeck.discord_adapter.client import build_bot
from critdeck.discord_adapter.command_logging import log_base_deck_rejection, log_left_out_deck_files
from critdeck.discord_adapter.command_sync import CommandSyncPlan
from critdeck.discord_adapter.lifecycle import run_until_stopped
from critdeck.logging_configuration import configure_logging

startup_logger = logging.getLogger("critdeck.startup")


def main() -> int:
    try:
        configuration = load_configuration(Path.cwd(), os.environ)
    except ConfigurationError as configuration_error:
        # Logging is not set up yet, because its own settings may be the problem.
        print(f"startup error: {configuration_error}", file=sys.stderr)  # noqa: T201  # no logger exists yet
        return 1

    file_logging_active = configure_logging(
        configuration.log_file, configuration.log_max_bytes, configuration.log_backups
    )
    startup_logger.info(
        "configuration env_file_found=%s command_prefix=%s deck_directory=%s log_file=%s "
        "guild_ids=%d sync_global_commands=%s",
        configuration.env_file_found,
        configuration.command_prefix,
        configuration.deck_directory,
        configuration.log_file,
        len(configuration.guild_ids),
        configuration.sync_global_commands,
    )
    startup_logger.info("file logging active=%s", file_logging_active)

    try:
        deck_catalogue = load_deck_catalogue(configuration.deck_directory)
    except BaseDeckRejectedError as base_rejection:
        log_base_deck_rejection(base_rejection.reason)
        return 1
    startup_logger.info(
        "deck catalogue loaded files=%d tiered_cards=%d special_levels=%d",
        len(deck_catalogue.loaded_files),
        len(deck_catalogue.tiered_cards),
        len(deck_catalogue.special_level_decks),
    )
    log_left_out_deck_files(deck_catalogue.left_out_files)

    critdeck_bot = build_bot(
        configuration.command_prefix,
        # Card order is not a security boundary, so the ordinary generator will do.
        DeckRegistry(random.Random()),  # noqa: S311
        functools.partial(load_deck_catalogue, configuration.deck_directory),
        CommandSyncPlan(configuration.guild_ids, configuration.sync_global_commands),
    )
    startup_logger.info("surfaces enabled slash=True prefix=True")
    startup_logger.info(
        "intents requested message_content=%s members=%s presences=%s",
        critdeck_bot.intents.message_content,
        critdeck_bot.intents.members,
        critdeck_bot.intents.presences,
    )

    try:
        asyncio.run(run_until_stopped(critdeck_bot, configuration.token))
    except KeyboardInterrupt:
        startup_logger.info("shutdown requested signal=SIGINT")
    except discord.LoginFailure:
        startup_logger.error("login failed: Discord rejected the token")  # noqa: TRY400  # the traceback would add nothing and the reason is known
        return 1
    except discord.PrivilegedIntentsRequired:
        startup_logger.error(  # noqa: TRY400  # the traceback would add nothing and the reason is known
            "login failed: switch on the Message Content Intent in the Discord Developer Portal"
        )
        return 1
    startup_logger.info("bot stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
