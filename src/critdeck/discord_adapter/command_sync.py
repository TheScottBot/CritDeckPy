"""Registering slash commands with Discord, only where and when asked.

Guild syncs update instantly and suit development servers. A global sync reaches
every server and is rate limited, so it runs only when explicitly requested,
never on every start: in the test server on 24 October 2026 a third guild sync
within three minutes waited 31 seconds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from discord import app_commands

sync_logger = logging.getLogger("critdeck.command_sync")


@dataclass(frozen=True)
class CommandSyncPlan:
    guild_ids: tuple[int, ...]
    sync_globally: bool


async def sync_application_commands(
    command_tree: app_commands.CommandTree[Any], command_sync_plan: CommandSyncPlan
) -> None:
    if not command_sync_plan.guild_ids and not command_sync_plan.sync_globally:
        # Said once at start, so commands missing from Discord are explained by
        # the log rather than a mystery.
        sync_logger.info("slash command sync not requested; Discord keeps the commands it already has")
        return

    for guild_id in command_sync_plan.guild_ids:
        target_guild = discord.Object(id=guild_id)
        command_tree.copy_global_to(guild=target_guild)
        try:
            synced_commands = await command_tree.sync(guild=target_guild)
        except discord.HTTPException as sync_error:
            # One wrong guild id, or a guild that invited the bot without the
            # applications.commands scope, should not stop the rest.
            sync_logger.warning(
                "slash command sync refused target=guild guild_id=%d status=%d discord_code=%d",
                guild_id,
                sync_error.status,
                sync_error.code,
            )
            continue
        sync_logger.info(
            "slash commands synced target=guild guild_id=%d command_count=%d", guild_id, len(synced_commands)
        )

    if command_sync_plan.sync_globally:
        synced_commands = await command_tree.sync()
        sync_logger.info("slash commands synced target=global command_count=%d", len(synced_commands))
