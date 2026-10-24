"""Settings from the environment and .env (critdeck.config)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import SYNTHETIC_TOKEN


def test_defaults_apply_when_only_the_token_is_set(reload_config):
    config = reload_config(DISCORD_TOKEN=SYNTHETIC_TOKEN)

    assert config.PROBLEMS == []
    assert config.COMMAND_PREFIX == "?"
    assert config.GUILD_IDS == ()
    assert config.SYNC_GLOBAL_COMMANDS is False
    assert config.DECK_DIRECTORY == Path("decks")
    assert config.LOG_FILE == Path("logs/critdeck.log")
    assert (config.LOG_MAX_BYTES, config.LOG_BACKUPS) == (1_000_000, 5)


def test_every_setting_is_read(reload_config):
    config = reload_config(
        DISCORD_TOKEN=SYNTHETIC_TOKEN,
        COMMAND_PREFIX="cd!",
        GUILD_IDS="1308740369982423051, 42",
        SYNC_GLOBAL_COMMANDS="true",
        DECK_DIRECTORY="/srv/decks",
        LOG_FILE="/var/log/critdeck.log",
        LOG_MAX_BYTES="2048",
        LOG_BACKUPS="0",
    )

    assert config.PROBLEMS == []
    assert config.COMMAND_PREFIX == "cd!"
    assert config.GUILD_IDS == (1308740369982423051, 42)
    assert config.SYNC_GLOBAL_COMMANDS is True
    assert config.DECK_DIRECTORY == Path("/srv/decks")
    assert config.LOG_FILE == Path("/var/log/critdeck.log")
    assert (config.LOG_MAX_BYTES, config.LOG_BACKUPS) == (2048, 0)


def test_a_missing_token_is_a_named_problem(reload_config):
    config = reload_config()

    assert config.PROBLEMS == [
        "DISCORD_TOKEN is missing: set it in the environment or in .env in the working directory"
    ]


@pytest.mark.parametrize(
    ("setting_name", "bad_value"),
    [
        ("COMMAND_PREFIX", "c d"),
        ("COMMAND_PREFIX", "x" * 11),
        ("GUILD_IDS", "1308740369982423051,abc"),
        ("SYNC_GLOBAL_COMMANDS", "yes"),
        ("LOG_MAX_BYTES", "0"),
        ("LOG_BACKUPS", "-1"),
    ],
)
def test_a_bad_value_is_a_problem_named_by_setting_without_its_value(reload_config, setting_name, bad_value):
    config = reload_config(DISCORD_TOKEN=SYNTHETIC_TOKEN, **{setting_name: bad_value})

    assert len(config.PROBLEMS) == 1
    assert config.PROBLEMS[0].startswith(setting_name)
    assert bad_value not in config.PROBLEMS[0]


def test_env_file_in_the_working_directory_is_read(reload_config):
    config = reload_config(env_file=f"DISCORD_TOKEN={SYNTHETIC_TOKEN}\nCOMMAND_PREFIX=!\n")

    assert config.ENV_FILE_FOUND
    assert config.DISCORD_TOKEN == SYNTHETIC_TOKEN
    assert config.COMMAND_PREFIX == "!"


def test_the_environment_wins_over_env_file(reload_config):
    config = reload_config(env_file="DISCORD_TOKEN=from.file\nCOMMAND_PREFIX=!\n", DISCORD_TOKEN=SYNTHETIC_TOKEN)

    assert config.DISCORD_TOKEN == SYNTHETIC_TOKEN
    assert config.COMMAND_PREFIX == "!"


def test_dollar_signs_in_env_file_stay_literal(reload_config):
    config = reload_config(env_file="DISCORD_TOKEN=abc${HOME}def\n")

    assert config.DISCORD_TOKEN == "abc${HOME}def"
