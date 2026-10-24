"""Logging to stderr and a size rotated file, as ktdi does.

stderr keeps journalctl and the terminal working. The file is best effort: if it
cannot be opened the bot says so once and carries on with stderr alone.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

LOG_FORMAT = "[{asctime}] [{levelname:<7}] {name}: {message}"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging_logger = logging.getLogger("critdeck.logging")


def configure_logging(log_file: Path, log_max_bytes: int, log_backups: int) -> bool:
    log_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT, style="{")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(log_formatter)
    root_logger.addHandler(stderr_handler)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=log_max_bytes, backupCount=log_backups, encoding="utf-8"
        )
    except OSError as open_error:
        logging_logger.warning(
            "file logging unavailable, logging to stderr only log_file=%s error_type=%s",
            log_file,
            type(open_error).__name__,
        )
        return False
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
    return True
