"""Shared test setup.

Run the tests with:  python -m pytest
"""

import importlib
import logging
import os
from pathlib import Path

# Before importing critdeck: never read the real .env, and start every setting from its default.
os.environ["CRITDECK_NO_DOTENV"] = "1"
SETTING_NAMES = (
    "DISCORD_TOKEN",
    "COMMAND_PREFIX",
    "GUILD_IDS",
    "SYNC_GLOBAL_COMMANDS",
    "DECK_DIRECTORY",
    "LOG_FILE",
    "LOG_MAX_BYTES",
    "LOG_BACKUPS",
)
for setting_name in SETTING_NAMES:
    os.environ.pop(setting_name, None)

import pytest  # noqa: E402

from critdeck import config  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
REAL_DECK_DIRECTORY = REPOSITORY_ROOT / "decks"


@pytest.fixture
def reload_config(monkeypatch, tmp_path):
    """Re-read the settings: reload_config(SETTING="value", ..., env_file="KEY=value\\n").

    Runs in an empty working directory, and puts the defaults back afterwards.
    """

    def reload_with(env_file: str | None = None, **settings: str):
        monkeypatch.chdir(tmp_path)
        for setting_name, setting_value in settings.items():
            monkeypatch.setenv(setting_name, setting_value)
        if env_file is not None:
            (tmp_path / ".env").write_text(env_file, encoding="utf-8")
            monkeypatch.delenv("CRITDECK_NO_DOTENV")
        return importlib.reload(config)

    yield reload_with
    monkeypatch.undo()
    for setting_name in SETTING_NAMES:
        os.environ.pop(setting_name, None)
    importlib.reload(config)


@pytest.fixture
def restore_root_logging():
    """Startup configures the root logger; give it back as it was, closing any file it opened."""
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    yield
    for added_handler in [handler for handler in root_logger.handlers if handler not in original_handlers]:
        root_logger.removeHandler(added_handler)
        added_handler.close()
    root_logger.setLevel(original_level)
