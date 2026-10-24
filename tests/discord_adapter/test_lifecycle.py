"""Shutdown signal handling for a clean stop under systemd and at a terminal."""

from __future__ import annotations

import signal
from typing import TYPE_CHECKING, cast

from critdeck.discord_adapter.lifecycle import install_shutdown_signal_handlers

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable


class FakeEventLoop:
    """Records signal handlers, or refuses them as the Windows event loop does."""

    def __init__(self, *, supports_signal_handlers: bool) -> None:
        self.handlers_by_signal: dict[int, Callable[..., object]] = {}
        self._supports_signal_handlers = supports_signal_handlers

    def add_signal_handler(
        self, signal_number: int, handler: Callable[..., object], *handler_arguments: object
    ) -> None:
        if not self._supports_signal_handlers:
            raise NotImplementedError
        self.handlers_by_signal[signal_number] = lambda: handler(*handler_arguments)


def test_install_shutdown_signal_handlers_handles_interrupt_and_terminate() -> None:
    fake_event_loop = FakeEventLoop(supports_signal_handlers=True)
    requested_signal_names: list[str] = []

    installed_signal_names = install_shutdown_signal_handlers(
        cast("asyncio.AbstractEventLoop", fake_event_loop), requested_signal_names.append
    )
    fake_event_loop.handlers_by_signal[signal.SIGTERM]()

    assert installed_signal_names == ("SIGINT", "SIGTERM")
    assert requested_signal_names == ["SIGTERM"]


def test_install_shutdown_signal_handlers_installs_nothing_where_the_loop_cannot() -> None:
    # Windows: Ctrl+C still stops the bot through KeyboardInterrupt.
    installed_signal_names = install_shutdown_signal_handlers(
        cast("asyncio.AbstractEventLoop", FakeEventLoop(supports_signal_handlers=False)),
        lambda _signal_name: None,
    )

    assert installed_signal_names == ()
