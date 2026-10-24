"""Settings from the environment and `.env` in the working directory.

The environment wins over `.env`, and an empty environment value falls through
to `.env`, as the Go bot's TOKEN did. Every problem is refused at startup by
setting name or `.env` line number. A value is never echoed, because one of them
is the bot token.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Never

from dotenv.parser import parse_stream

if TYPE_CHECKING:
    from collections.abc import Mapping

ENV_FILE_NAME = ".env"
# A settings file is a few hundred bytes; anything this size is not one.
MAXIMUM_ENV_FILE_BYTES = 65_536
# Discord bot tokens are around 72 characters; this only refuses nonsense.
MAXIMUM_TOKEN_LENGTH = 200
MAXIMUM_COMMAND_PREFIX_LENGTH = 10

ASCII_DIGITS_PATTERN = re.compile(r"[0-9]+")
BOOLEAN_TEXT = {"true": True, "false": False}


@dataclass(frozen=True)
class ConfigurationSetting:
    key: str
    # None marks a required setting with no default.
    default_text: str | None


CONFIGURATION_SETTINGS = (
    # Named as in ktdi and the author's other bots. The Go bot used TOKEN, which
    # is now refused as an unknown key, so a carried over .env says so plainly.
    ConfigurationSetting("DISCORD_TOKEN", None),
    ConfigurationSetting("COMMAND_PREFIX", "?"),
    ConfigurationSetting("GUILD_IDS", ""),
    ConfigurationSetting("SYNC_GLOBAL_COMMANDS", "false"),
    ConfigurationSetting("DECK_DIRECTORY", "decks"),
    ConfigurationSetting("LOG_FILE", "logs/critdeck.log"),
    ConfigurationSetting("LOG_MAX_BYTES", "1000000"),
    ConfigurationSetting("LOG_BACKUPS", "5"),
)
KNOWN_SETTING_KEYS = tuple(setting.key for setting in CONFIGURATION_SETTINGS)


class ConfigurationError(Exception):
    def __init__(self, problem: str) -> None:
        super().__init__(problem)
        self.known_keys = ", ".join(KNOWN_SETTING_KEYS)


@dataclass(frozen=True)
class Configuration:
    # Kept out of repr so the token cannot reach a log or a traceback by accident.
    token: str = field(repr=False)
    command_prefix: str
    guild_ids: tuple[int, ...]
    sync_global_commands: bool
    deck_directory: Path
    log_file: Path
    log_max_bytes: int
    log_backups: int
    env_file_found: bool


def load_configuration(working_directory: Path, environment: Mapping[str, str]) -> Configuration:
    # Only the working directory is read. python-dotenv's own search walks up
    # through parent directories, which could pick up an unrelated file.
    env_file_values = read_env_file(working_directory / ENV_FILE_NAME)
    return build_configuration(environment, env_file_values)


def read_env_file(env_file_path: Path) -> dict[str, str] | None:
    try:
        with env_file_path.open("rb") as env_file:
            env_file_bytes = env_file.read(MAXIMUM_ENV_FILE_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError as read_error:
        problem = f"{ENV_FILE_NAME} exists but cannot be read"
        raise ConfigurationError(problem) from read_error
    if len(env_file_bytes) > MAXIMUM_ENV_FILE_BYTES:
        problem = f"{ENV_FILE_NAME} is larger than {MAXIMUM_ENV_FILE_BYTES} bytes"
        raise ConfigurationError(problem)
    try:
        env_file_text = env_file_bytes.decode("utf-8")
    except UnicodeDecodeError as decode_error:
        problem = f"{ENV_FILE_NAME} is not valid UTF-8"
        raise ConfigurationError(problem) from decode_error
    return parse_env_file(env_file_text)


def parse_env_file(env_file_text: str) -> dict[str, str]:
    # python-dotenv's line parser, rather than dotenv_values, because the latter
    # skips malformed lines with only a warning, keeps the last of two equal keys
    # silently, and expands ${...} inside values, which could alter a token.
    env_file_values: dict[str, str] = {}
    for binding in parse_stream(io.StringIO(env_file_text)):
        line_number = binding.original.line
        if binding.error:
            _refuse(f"{ENV_FILE_NAME} line {line_number} is not KEY=value")
        if binding.key is None:
            continue
        if binding.value is None:
            _refuse(f"{ENV_FILE_NAME} line {line_number} has no value")
        if binding.key in env_file_values:
            _refuse(f"{ENV_FILE_NAME} line {line_number} repeats {binding.key}")
        if binding.key not in KNOWN_SETTING_KEYS:
            _refuse(f"{ENV_FILE_NAME} line {line_number} sets unknown key {binding.key}")
        env_file_values[binding.key] = binding.value
    return env_file_values


def build_configuration(
    environment: Mapping[str, str], env_file_values: Mapping[str, str] | None
) -> Configuration:
    setting_texts = {
        setting.key: _resolve_setting_text(setting, environment, env_file_values or {})
        for setting in CONFIGURATION_SETTINGS
    }
    return Configuration(
        token=_parse_token(setting_texts["DISCORD_TOKEN"]),
        command_prefix=_parse_command_prefix(setting_texts["COMMAND_PREFIX"]),
        guild_ids=_parse_guild_ids(setting_texts["GUILD_IDS"]),
        sync_global_commands=_parse_boolean("SYNC_GLOBAL_COMMANDS", setting_texts["SYNC_GLOBAL_COMMANDS"]),
        deck_directory=_parse_path("DECK_DIRECTORY", setting_texts["DECK_DIRECTORY"]),
        log_file=_parse_path("LOG_FILE", setting_texts["LOG_FILE"]),
        log_max_bytes=_parse_count("LOG_MAX_BYTES", setting_texts["LOG_MAX_BYTES"], minimum=1),
        log_backups=_parse_count("LOG_BACKUPS", setting_texts["LOG_BACKUPS"], minimum=0),
        env_file_found=env_file_values is not None,
    )


def _resolve_setting_text(
    setting: ConfigurationSetting, environment: Mapping[str, str], env_file_values: Mapping[str, str]
) -> str:
    environment_text = environment.get(setting.key, "")
    if environment_text:
        return environment_text
    env_file_text = env_file_values.get(setting.key, "")
    if env_file_text:
        return env_file_text
    if setting.default_text is None:
        _refuse(
            f"{setting.key} is missing: set it in the environment or in {ENV_FILE_NAME} "
            "in the working directory"
        )
    return setting.default_text


def _parse_token(token_text: str) -> str:
    if len(token_text) > MAXIMUM_TOKEN_LENGTH or any(character.isspace() for character in token_text):
        _refuse("DISCORD_TOKEN is not a Discord bot token: it is too long or contains whitespace")
    return token_text


def _parse_command_prefix(prefix_text: str) -> str:
    if len(prefix_text) > MAXIMUM_COMMAND_PREFIX_LENGTH or any(
        character.isspace() for character in prefix_text
    ):
        _refuse(f"COMMAND_PREFIX must be 1 to {MAXIMUM_COMMAND_PREFIX_LENGTH} characters with no whitespace")
    return prefix_text


def _parse_guild_ids(guild_ids_text: str) -> tuple[int, ...]:
    if not guild_ids_text:
        return ()
    guild_id_texts = [guild_id_text.strip() for guild_id_text in guild_ids_text.split(",")]
    # ktdi skips a mistyped id with a warning; here a typo stops startup, so the
    # command sync never quietly misses a server someone meant to list.
    if not all(ASCII_DIGITS_PATTERN.fullmatch(guild_id_text) for guild_id_text in guild_id_texts):
        _refuse("GUILD_IDS must be server ids separated by commas, digits only")
    return tuple(int(guild_id_text) for guild_id_text in guild_id_texts)


def _parse_boolean(setting_key: str, boolean_text: str) -> bool:
    if boolean_text not in BOOLEAN_TEXT:
        _refuse(f"{setting_key} must be true or false")
    return BOOLEAN_TEXT[boolean_text]


def _parse_path(setting_key: str, path_text: str) -> Path:
    if not path_text.strip():
        _refuse(f"{setting_key} must be a path")
    return Path(path_text)


def _parse_count(setting_key: str, count_text: str, *, minimum: int) -> int:
    if not ASCII_DIGITS_PATTERN.fullmatch(count_text) or int(count_text) < minimum:
        _refuse(f"{setting_key} must be a whole number of at least {minimum}")
    return int(count_text)


def _refuse(problem: str) -> Never:
    raise ConfigurationError(problem)
