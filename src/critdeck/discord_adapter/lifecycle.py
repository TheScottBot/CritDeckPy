"""Running the bot until it is told to stop.

discord.py's own run() turns Ctrl+C into a clean exit but leaves SIGTERM, which
is how systemd stops a service, to kill the process without closing the
connection. Here both signals close the bot cleanly where the event loop can
handle them. The Windows event loop cannot, and there Ctrl+C still stops the bot
through KeyboardInterrupt.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord.ext import commands

SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)

lifecycle_logger = logging.getLogger("critdeck.lifecycle")


def install_shutdown_signal_handlers(
    event_loop: asyncio.AbstractEventLoop, request_shutdown: Callable[[str], None]
) -> tuple[str, ...]:
    installed_signal_names: list[str] = []
    for shutdown_signal in SHUTDOWN_SIGNALS:
        try:
            event_loop.add_signal_handler(shutdown_signal, request_shutdown, shutdown_signal.name)
        except NotImplementedError:
            continue
        installed_signal_names.append(shutdown_signal.name)
    return tuple(installed_signal_names)


async def run_until_stopped(critdeck_bot: commands.Bot, token: str) -> None:
    event_loop = asyncio.get_running_loop()
    # Held so the closing task is not garbage collected before it finishes.
    closing_tasks: set[asyncio.Task[None]] = set()

    def request_shutdown(signal_name: str) -> None:
        lifecycle_logger.info("shutdown requested signal=%s", signal_name)
        closing_task = event_loop.create_task(critdeck_bot.close())
        closing_tasks.add(closing_task)
        closing_task.add_done_callback(closing_tasks.discard)

    async with critdeck_bot:
        installed_signal_names = install_shutdown_signal_handlers(event_loop, request_shutdown)
        lifecycle_logger.info(
            "shutdown signals handled signals=%s",
            ",".join(installed_signal_names) or "keyboard_interrupt_only",
        )
        await critdeck_bot.start(token)
