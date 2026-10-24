"""Structured log lines for commands, shared by the slash and prefix surfaces.

Only the command name, the surface, the outcome category and lengths are logged.
Message content, card text and the token never are.
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

    from critdeck.commands.actions import CommandResult

command_logger = logging.getLogger("critdeck.commands")


class CommandSurface(enum.Enum):
    SLASH = "slash"
    PREFIX = "prefix"


def log_command_result(
    command_name: str, command_surface: CommandSurface, command_result: CommandResult, input_length: int
) -> None:
    command_logger.info(
        "command=%s surface=%s outcome=%s input_length=%d",
        command_name,
        command_surface.value,
        command_result.outcome.name.lower(),
        input_length,
    )
    if command_result.reshuffled:
        command_logger.info("deck reshuffled command=%s surface=%s", command_name, command_surface.value)
    if command_result.base_deck_rejection_reason is not None:
        command_logger.error(
            "base deck rejected reason=%s", command_result.base_deck_rejection_reason.name.lower()
        )
    for left_out_file in command_result.left_out_files:
        command_logger.warning(
            "deck file left out path=%s reason=%s",
            left_out_file.relative_path.as_posix(),
            left_out_file.reason.name.lower(),
        )


def log_reply_failure(
    command_name: str, command_surface: CommandSurface, reply_error: discord.HTTPException
) -> None:
    command_logger.warning(
        "reply failed command=%s surface=%s status=%d discord_code=%d",
        command_name,
        command_surface.value,
        reply_error.status,
        reply_error.code,
    )
