"""Logging to stderr and a size rotated file, as ktdi does."""

from __future__ import annotations

import logging
import logging.handlers
from typing import TYPE_CHECKING

import pytest

from critdeck.logging_configuration import LOG_FORMAT, configure_logging

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.usefixtures("restore_root_logging")
def test_configure_logging_writes_to_stderr_and_a_rotating_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "critdeck.log"

    file_logging_active = configure_logging(log_file, 2048, 3)
    logging.getLogger("critdeck.test").info("startup line")

    root_logger = logging.getLogger()
    rotating_handlers = [
        handler
        for handler in root_logger.handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]
    assert file_logging_active
    assert root_logger.level == logging.INFO
    assert len(rotating_handlers) == 1
    assert rotating_handlers[0].maxBytes == 2048
    assert rotating_handlers[0].backupCount == 3
    assert any(type(handler) is logging.StreamHandler for handler in root_logger.handlers)
    rotating_handlers[0].flush()
    assert "critdeck.test: startup line" in log_file.read_text(encoding="utf-8")


@pytest.mark.usefixtures("restore_root_logging")
def test_configure_logging_carries_on_with_stderr_when_the_file_cannot_be_opened(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A directory where the file should be makes opening it fail on every platform.
    unopenable_log_file = tmp_path / "critdeck.log"
    unopenable_log_file.mkdir()

    file_logging_active = configure_logging(unopenable_log_file, 2048, 3)

    assert not file_logging_active
    assert "file logging unavailable, logging to stderr only" in caplog.text


def test_log_format_matches_ktdi() -> None:
    assert LOG_FORMAT == "[{asctime}] [{levelname:<7}] {name}: {message}"
