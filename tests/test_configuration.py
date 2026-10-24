"""Configuration from the environment and `.env`, strictly read."""

from __future__ import annotations

from pathlib import Path

import pytest

from critdeck.configuration import (
    CONFIGURATION_SETTINGS,
    MAXIMUM_ENV_FILE_BYTES,
    ConfigurationError,
    build_configuration,
    load_configuration,
    parse_env_file,
)
from tests.conftest import SYNTHETIC_TOKEN

TOKEN_ONLY_ENVIRONMENT = {"DISCORD_TOKEN": SYNTHETIC_TOKEN}


def test_build_configuration_applies_every_default_when_only_the_token_is_set() -> None:
    configuration = build_configuration(TOKEN_ONLY_ENVIRONMENT, None)

    assert configuration.token == SYNTHETIC_TOKEN
    assert configuration.command_prefix == "?"
    assert configuration.guild_ids == ()
    assert not configuration.sync_global_commands
    assert configuration.deck_directory == Path("decks")
    assert configuration.log_file == Path("logs/critdeck.log")
    assert configuration.log_max_bytes == 1_000_000
    assert configuration.log_backups == 5
    assert not configuration.env_file_found


def test_build_configuration_reads_every_setting() -> None:
    configuration = build_configuration(
        {
            "DISCORD_TOKEN": SYNTHETIC_TOKEN,
            "COMMAND_PREFIX": "cd!",
            "GUILD_IDS": "1308740369982423051, 42",
            "SYNC_GLOBAL_COMMANDS": "true",
            "DECK_DIRECTORY": "/srv/critdeck/decks",
            "LOG_FILE": "/var/log/critdeck/critdeck.log",
            "LOG_MAX_BYTES": "2048",
            "LOG_BACKUPS": "0",
        },
        None,
    )

    assert configuration.command_prefix == "cd!"
    assert configuration.guild_ids == (1308740369982423051, 42)
    assert configuration.sync_global_commands
    assert configuration.deck_directory == Path("/srv/critdeck/decks")
    assert configuration.log_file == Path("/var/log/critdeck/critdeck.log")
    assert configuration.log_max_bytes == 2048
    assert configuration.log_backups == 0


def test_environment_wins_over_the_env_file() -> None:
    configuration = build_configuration(
        {"DISCORD_TOKEN": SYNTHETIC_TOKEN, "COMMAND_PREFIX": "!"},
        {"DISCORD_TOKEN": "file.token", "COMMAND_PREFIX": "?"},
    )

    assert configuration.token == SYNTHETIC_TOKEN
    assert configuration.command_prefix == "!"
    assert configuration.env_file_found


def test_an_empty_environment_value_falls_through_to_the_env_file() -> None:
    # As in the Go bot, where an empty TOKEN environment variable fell through to
    # the configuration file.
    configuration = build_configuration({"DISCORD_TOKEN": ""}, {"DISCORD_TOKEN": SYNTHETIC_TOKEN})

    assert configuration.token == SYNTHETIC_TOKEN


def test_unrelated_environment_variables_are_ignored() -> None:
    configuration = build_configuration({**TOKEN_ONLY_ENVIRONMENT, "PATH": "/usr/bin", "HOME": "/root"}, None)

    assert configuration.token == SYNTHETIC_TOKEN


def test_a_missing_token_is_a_clear_startup_error() -> None:
    with pytest.raises(ConfigurationError) as configuration_error:
        build_configuration({}, None)

    assert str(configuration_error.value) == (
        "DISCORD_TOKEN is missing: set it in the environment or in .env in the working directory"
    )


INVALID_SETTINGS = {
    "token_with_whitespace": ("DISCORD_TOKEN", "two words"),
    "empty_prefix_from_file_only": ("COMMAND_PREFIX", " "),
    "prefix_with_whitespace": ("COMMAND_PREFIX", "c d"),
    "prefix_too_long": ("COMMAND_PREFIX", "x" * 11),
    "guild_id_not_digits": ("GUILD_IDS", "1308740369982423051,abc"),
    "guild_id_empty_entry": ("GUILD_IDS", "1,,2"),
    "sync_not_a_boolean": ("SYNC_GLOBAL_COMMANDS", "yes"),
    "sync_wrong_case": ("SYNC_GLOBAL_COMMANDS", "True"),
    "max_bytes_zero": ("LOG_MAX_BYTES", "0"),
    "max_bytes_not_digits": ("LOG_MAX_BYTES", "1e6"),
    "backups_negative": ("LOG_BACKUPS", "-1"),
    "empty_deck_directory": ("DECK_DIRECTORY", " "),
}


@pytest.mark.parametrize(
    ("setting_key", "invalid_value"), INVALID_SETTINGS.values(), ids=INVALID_SETTINGS.keys()
)
def test_an_invalid_setting_is_refused_by_name_without_echoing_its_value(
    setting_key: str, invalid_value: str
) -> None:
    with pytest.raises(ConfigurationError) as configuration_error:
        build_configuration({**TOKEN_ONLY_ENVIRONMENT, setting_key: invalid_value}, None)

    assert setting_key in str(configuration_error.value)
    if invalid_value.strip():
        assert invalid_value not in str(configuration_error.value)


def test_parse_env_file_reads_values_comments_blank_lines_and_export() -> None:
    env_file_values = parse_env_file(
        f"# CritDeck settings\n\nDISCORD_TOKEN={SYNTHETIC_TOKEN}\n"
        "export COMMAND_PREFIX='!'\nGUILD_IDS=\"1, 2\"\n"
    )

    assert env_file_values == {"DISCORD_TOKEN": SYNTHETIC_TOKEN, "COMMAND_PREFIX": "!", "GUILD_IDS": "1, 2"}


def test_parse_env_file_keeps_dollar_signs_literal() -> None:
    assert parse_env_file("DISCORD_TOKEN=abc${HOME}def\n") == {"DISCORD_TOKEN": "abc${HOME}def"}


ENV_FILE_REJECTIONS = {
    "malformed_line": ("DISCORD_TOKEN=abc\nthis is not a setting\n", "line 2 is not KEY=value"),
    "key_without_value": ("DISCORD_TOKEN=abc\nCOMMAND_PREFIX\n", "line 2 has no value"),
    "duplicate_key": ("DISCORD_TOKEN=abc\nDISCORD_TOKEN=def\n", "line 2 repeats DISCORD_TOKEN"),
    # TOKEN was the Go bot's key; a .env carried over from it is told plainly.
    "unknown_key": ("DISCORD_TOKEN=abc\nTOKEN=def\n", "line 2 sets unknown key TOKEN"),
}


@pytest.mark.parametrize(
    ("env_file_text", "expected_reason"), ENV_FILE_REJECTIONS.values(), ids=ENV_FILE_REJECTIONS.keys()
)
def test_parse_env_file_refuses_problems_by_line_without_echoing_values(
    env_file_text: str, expected_reason: str
) -> None:
    with pytest.raises(ConfigurationError) as configuration_error:
        parse_env_file(env_file_text)

    assert str(configuration_error.value) == f".env {expected_reason}"
    assert "def" not in str(configuration_error.value)


def test_unknown_key_message_lists_the_known_keys() -> None:
    known_keys = ", ".join(setting.key for setting in CONFIGURATION_SETTINGS)

    with pytest.raises(ConfigurationError) as configuration_error:
        parse_env_file("TOKEN=abc\n")

    assert configuration_error.value.known_keys == known_keys


def test_load_configuration_reads_env_file_from_the_working_directory(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"DISCORD_TOKEN={SYNTHETIC_TOKEN}\nCOMMAND_PREFIX=!\n", encoding="utf-8")

    configuration = load_configuration(tmp_path, {})

    assert configuration.token == SYNTHETIC_TOKEN
    assert configuration.command_prefix == "!"
    assert configuration.env_file_found


def test_load_configuration_without_an_env_file_uses_the_environment(tmp_path: Path) -> None:
    configuration = load_configuration(tmp_path, TOKEN_ONLY_ENVIRONMENT)

    assert not configuration.env_file_found


def test_load_configuration_never_looks_in_parent_directories(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"DISCORD_TOKEN={SYNTHETIC_TOKEN}\n", encoding="utf-8")
    working_directory = tmp_path / "service"
    working_directory.mkdir()

    with pytest.raises(ConfigurationError):
        load_configuration(working_directory, {})


def test_load_configuration_refuses_an_env_file_over_the_size_bound(tmp_path: Path) -> None:
    padding_line = "# " + "x" * 100 + "\n"
    (tmp_path / ".env").write_text(
        f"DISCORD_TOKEN={SYNTHETIC_TOKEN}\n"
        + padding_line * (MAXIMUM_ENV_FILE_BYTES // len(padding_line) + 1),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as configuration_error:
        load_configuration(tmp_path, {})

    assert str(configuration_error.value) == f".env is larger than {MAXIMUM_ENV_FILE_BYTES} bytes"


def test_load_configuration_refuses_an_env_file_that_is_not_utf8(tmp_path: Path) -> None:
    (tmp_path / ".env").write_bytes(b"DISCORD_TOKEN=caf\xe9\n")

    with pytest.raises(ConfigurationError) as configuration_error:
        load_configuration(tmp_path, {})

    assert str(configuration_error.value) == ".env is not valid UTF-8"


def test_configuration_repr_never_shows_the_token() -> None:
    configuration = build_configuration(TOKEN_ONLY_ENVIRONMENT, None)

    assert SYNTHETIC_TOKEN not in repr(configuration)
    assert SYNTHETIC_TOKEN not in str(configuration)
