"""The bot: intents, cogs, slash command sync, logging, error replies, clean shutdown and main()."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from critdeck import config
from critdeck.cogs import COGS, decks
from critdeck.cogs.decks import log_left_out_files
from critdeck.lib.deck_files import BaseDeckRejectedError, load_deck_catalogue

log = logging.getLogger("critdeck")

SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def setup_logging() -> bool:
    """Log to the terminal (so journalctl still works) and to a rolling log file, as ktdi does.

    The file is best effort: if it cannot be opened the bot says so and carries on.
    """
    formatter = logging.Formatter("[{asctime}] [{levelname:<7}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    try:
        config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES, backupCount=config.LOG_BACKUPS, encoding="utf-8"
        )
    except OSError as error:
        log.warning("file logging unavailable, logging to stderr only error_type=%s", type(error).__name__)
        return False
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    return True


async def sync_application_commands(command_tree, guild_ids: tuple[int, ...], *, sync_globally: bool) -> None:
    """Register the slash commands with Discord, only where and when asked.

    Discord keeps registered commands between restarts, and rate limits repeated
    syncs (a third guild sync in three minutes waited 31 seconds when tested), so
    nothing is synced unless GUILD_IDS or SYNC_GLOBAL_COMMANDS asks.
    """
    if not guild_ids and not sync_globally:
        log.info("slash command sync not requested; Discord keeps the commands it already has")
        return
    for guild_id in guild_ids:
        guild = discord.Object(id=guild_id)
        command_tree.copy_global_to(guild=guild)
        try:
            synced_commands = await command_tree.sync(guild=guild)
        except discord.HTTPException as error:
            # A wrong id, or a server that invited the bot without the
            # applications.commands scope, should not stop the rest.
            log.warning(
                "slash command sync refused guild_id=%d status=%d discord_code=%d", guild_id, error.status, error.code
            )
            continue
        log.info("slash commands synced guild_id=%d command_count=%d", guild_id, len(synced_commands))
    if sync_globally:
        synced_commands = await command_tree.sync()
        log.info("slash commands synced globally command_count=%d", len(synced_commands))


class CritDeckBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        # Needed to read "?newdeck 7" from messages. Must also be switched on in the Developer Portal.
        intents.message_content = True
        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            # The Go bot matched commands in any case, so ?Draw keeps working.
            case_insensitive=True,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        for cog in COGS:
            await self.load_extension(cog)
        await sync_application_commands(self.tree, config.GUILD_IDS, sync_globally=config.SYNC_GLOBAL_COMMANDS)

    async def on_command(self, ctx: commands.Context) -> None:
        # Fires for both /commands and typed commands. What was typed is never
        # logged: only which command, and how it arrived.
        log.info("command=%s surface=%s", ctx.command.qualified_name, "slash" if ctx.interaction else "prefix")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # Every message starting with the prefix but naming no command lands here.
        # That is ordinary chat, not a fault.
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.NoPrivateMessage):
            log.info("command refused reason=direct_message")
            await ctx.send(decks.DIRECT_MESSAGE_TEXT, ephemeral=True)
            return
        # Only /newdeck takes input, so every input error is a mistyped level:
        # ?newdeck nine, ?newdeck 7 8, or ?newdeck on its own.
        if isinstance(error, commands.UserInputError):
            log.info("command refused reason=malformed_party_level")
            await ctx.send(decks.PARTY_LEVEL_OUT_OF_RANGE_TEXT, ephemeral=True)
            return
        if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
            log.warning("reply failed status=%d discord_code=%d", error.original.status, error.original.code)
            return
        # The type only: framework error messages can quote what was typed.
        log.error("command error error_type=%s", type(error).__name__)


def install_shutdown_signal_handlers(event_loop, request_shutdown) -> tuple[str, ...]:
    """Have SIGINT and SIGTERM call request_shutdown, where the event loop can.

    discord.py's own run() handles Ctrl+C but not SIGTERM, which is how systemd
    stops a service. The Windows event loop cannot install either; Ctrl+C still
    arrives there as KeyboardInterrupt.
    """
    installed_signal_names = []
    for shutdown_signal in SHUTDOWN_SIGNALS:
        try:
            event_loop.add_signal_handler(shutdown_signal, request_shutdown, shutdown_signal.name)
        except NotImplementedError:
            continue
        installed_signal_names.append(shutdown_signal.name)
    return tuple(installed_signal_names)


async def run_until_stopped(critdeck_bot: CritDeckBot, token: str) -> None:
    event_loop = asyncio.get_running_loop()
    # Held so a closing task is not garbage collected before it finishes.
    closing_tasks: set[asyncio.Task] = set()

    def request_shutdown(signal_name: str) -> None:
        log.info("shutdown requested signal=%s", signal_name)
        closing_task = event_loop.create_task(critdeck_bot.close())
        closing_tasks.add(closing_task)
        closing_task.add_done_callback(closing_tasks.discard)

    async with critdeck_bot:
        installed_signal_names = install_shutdown_signal_handlers(event_loop, request_shutdown)
        log.info("shutdown signals handled signals=%s", ",".join(installed_signal_names) or "keyboard_interrupt_only")
        await critdeck_bot.start(token)


def main() -> int:
    """Check everything that can be checked before contacting Discord, then run the bot."""
    if config.PROBLEMS:
        # Logging is not set up yet, because its own settings may be the problem.
        for problem in config.PROBLEMS:
            print(f"startup error: {problem}", file=sys.stderr)
        return 1

    file_logging_active = setup_logging()
    log.info(
        "configuration env_file_found=%s command_prefix=%s deck_directory=%s log_file=%s "
        "guild_ids=%d sync_global_commands=%s",
        config.ENV_FILE_FOUND,
        config.COMMAND_PREFIX,
        config.DECK_DIRECTORY.as_posix(),
        config.LOG_FILE.as_posix(),
        len(config.GUILD_IDS),
        config.SYNC_GLOBAL_COMMANDS,
    )
    log.info("file logging active=%s", file_logging_active)

    try:
        deck_catalogue = load_deck_catalogue(config.DECK_DIRECTORY)
    except BaseDeckRejectedError as base_rejection:
        log.error("base deck rejected reason=%s", base_rejection.reason.name.lower())
        return 1
    log.info(
        "deck catalogue loaded files=%d tiered_cards=%d special_levels=%d",
        len(deck_catalogue.loaded_files),
        len(deck_catalogue.tiered_cards),
        len(deck_catalogue.special_level_decks),
    )
    log_left_out_files(deck_catalogue.left_out_files)

    critdeck_bot = CritDeckBot()
    log.info(
        "intents requested message_content=%s members=%s presences=%s",
        critdeck_bot.intents.message_content,
        critdeck_bot.intents.members,
        critdeck_bot.intents.presences,
    )
    try:
        asyncio.run(run_until_stopped(critdeck_bot, config.DISCORD_TOKEN))
    except KeyboardInterrupt:
        log.info("shutdown requested signal=SIGINT")
    except discord.LoginFailure:
        log.error("login failed: Discord rejected the token")
        return 1
    except discord.PrivilegedIntentsRequired:
        log.error("login failed: switch on the Message Content Intent in the Discord Developer Portal")
        return 1
    log.info("bot stopped")
    return 0
