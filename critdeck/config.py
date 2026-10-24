"""Settings from the environment, then .env in the working directory; the environment wins.

Every setting is listed, with its default, in .env.example. A bad setting is
collected in PROBLEMS rather than raised, so main() can name each one and stop
before anything else happens. Problems name the setting, never its value: one of
the values is the bot token.
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path.cwd() / ".env"
ENV_FILE_FOUND = ENV_FILE.is_file()
# The tests set CRITDECK_NO_DOTENV so they never read a real .env. The path is
# explicit so python-dotenv never searches parent directories, and nothing is
# interpolated, because ${...} expansion could change a token.
if not os.getenv("CRITDECK_NO_DOTENV") and ENV_FILE_FOUND:
    load_dotenv(ENV_FILE, override=False, interpolate=False)

PROBLEMS: list[str] = []

MAXIMUM_COMMAND_PREFIX_LENGTH = 10


def _whole_number(setting_name: str, default: str, minimum: int) -> int:
    setting_text = os.getenv(setting_name) or default
    if not re.fullmatch(r"[0-9]+", setting_text) or int(setting_text) < minimum:
        PROBLEMS.append(f"{setting_name} must be a whole number of at least {minimum}")
        return int(default)
    return int(setting_text)


def _guild_ids(guild_ids_text: str) -> tuple[int, ...]:
    if not guild_ids_text.strip():
        return ()
    guild_id_texts = [guild_id_text.strip() for guild_id_text in guild_ids_text.split(",")]
    # ktdi skips a mistyped id with a warning; here it stops startup, so a sync
    # never quietly misses a server someone meant to list.
    if not all(re.fullmatch(r"[0-9]+", guild_id_text) for guild_id_text in guild_id_texts):
        PROBLEMS.append("GUILD_IDS must be server ids separated by commas, digits only")
        return ()
    return tuple(int(guild_id_text) for guild_id_text in guild_id_texts)


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
if not DISCORD_TOKEN:
    PROBLEMS.append("DISCORD_TOKEN is missing: set it in the environment or in .env in the working directory")

# Prefix for the typed backup commands, e.g. "?" gives "?newdeck 7". The slash commands always work too.
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX") or "?"
if len(COMMAND_PREFIX) > MAXIMUM_COMMAND_PREFIX_LENGTH or any(character.isspace() for character in COMMAND_PREFIX):
    PROBLEMS.append(f"COMMAND_PREFIX must be 1 to {MAXIMUM_COMMAND_PREFIX_LENGTH} characters with no whitespace")

# Server ids to register slash commands to straight away, for testing.
GUILD_IDS = _guild_ids(os.getenv("GUILD_IDS", ""))

# true once, at release, registers the slash commands in every server.
SYNC_GLOBAL_COMMANDS_TEXT = os.getenv("SYNC_GLOBAL_COMMANDS") or "false"
if SYNC_GLOBAL_COMMANDS_TEXT not in {"true", "false"}:
    PROBLEMS.append("SYNC_GLOBAL_COMMANDS must be true or false")
SYNC_GLOBAL_COMMANDS = SYNC_GLOBAL_COMMANDS_TEXT == "true"

DECK_DIRECTORY = Path(os.getenv("DECK_DIRECTORY") or "decks")

# Rolling log file, as ktdi: it rotates at LOG_MAX_BYTES, keeping LOG_BACKUPS old files.
LOG_FILE = Path(os.getenv("LOG_FILE") or "logs/critdeck.log")
LOG_MAX_BYTES = _whole_number("LOG_MAX_BYTES", "1000000", minimum=1)
LOG_BACKUPS = _whole_number("LOG_BACKUPS", "5", minimum=0)
