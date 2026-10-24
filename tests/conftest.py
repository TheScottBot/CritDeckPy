"""Shared fixtures and doubles for the CritDeck test suite.

Fixtures and doubles live here and nowhere else, so every test file imports
them rather than defining its own, and a change to one is a change to all.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest

from critdeck.core.catalogue import Card, CardEffect, DeckCatalogue, StrengthTier

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
REAL_DECK_DIRECTORY = REPOSITORY_ROOT / "decks"

# Synthetic card text only. The real card text is third party data and never
# appears in a fixture.
SYNTHETIC_EFFECTS = (
    {"damageType": "Bludgeoning", "value": "Synthetic bludgeoning effect"},
    {"damageType": "Piercing", "value": "Synthetic piercing effect"},
)


def build_card_record(
    strength: str = "Setback", effects: list[dict[str, object]] | None = None
) -> dict[str, object]:
    return {
        "strength": strength,
        "effects": list(SYNTHETIC_EFFECTS) if effects is None else effects,
    }


def encode_deck_document(deck_document: object) -> bytes:
    return json.dumps(deck_document).encode("utf-8")


def build_tiered_deck_bytes(strengths: list[str]) -> bytes:
    return encode_deck_document({"cards": [build_card_record(strength) for strength in strengths]})


def build_special_level_deck_bytes(level: int, card_count: int = 1) -> bytes:
    return encode_deck_document({"level": level, "cards": [build_card_record() for _ in range(card_count)]})


def write_deck_directory(
    deck_directory: Path,
    base_deck_bytes: bytes | None,
    extension_files: dict[str, bytes] | None = None,
    special_level_files: dict[str, bytes] | None = None,
) -> Path:
    deck_directory.mkdir(parents=True, exist_ok=True)
    if base_deck_bytes is not None:
        (deck_directory / "player-deck.json").write_bytes(base_deck_bytes)
    for subdirectory_name, named_files in (
        ("extensions", extension_files),
        ("special-levels", special_level_files),
    ):
        if named_files is None:
            continue
        subdirectory = deck_directory / subdirectory_name
        subdirectory.mkdir(exist_ok=True)
        for file_name, file_bytes in named_files.items():
            (subdirectory / file_name).write_bytes(file_bytes)
    return deck_directory


def run_development_tool(
    *tool_arguments: str, standard_input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    # The tools run from the repository root so they read the real pyproject.toml,
    # which is the configuration under test.
    return subprocess.run(  # noqa: S603  # arguments are fixed by the tests, never external input
        [sys.executable, "-m", *tool_arguments],
        cwd=REPOSITORY_ROOT,
        input=standard_input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def build_synthetic_card(strength: StrengthTier, card_label: str) -> Card:
    return Card(strength, (CardEffect("Magic", f"Synthetic effect of {card_label}"),))


def build_deck_catalogue(
    tiered_cards: Sequence[Card], special_level_decks: Mapping[int, Sequence[Card]] | None = None
) -> DeckCatalogue:
    return DeckCatalogue(
        tiered_cards=tuple(tiered_cards),
        special_level_decks={level: tuple(cards) for level, cards in (special_level_decks or {}).items()},
        loaded_files=(PurePosixPath("player-deck.json"),),
        left_out_files=(),
    )


class FakeCardShuffler:
    """Shuffles by reversing, so a test can predict the order, and counts shuffles."""

    def __init__(self) -> None:
        self.shuffle_count = 0

    def shuffle(self, cards_to_shuffle: list[Card], /) -> None:
        self.shuffle_count += 1
        cards_to_shuffle.reverse()


class FakeDeckCatalogueLoader:
    """Hands back a prepared catalogue, or raises a prepared error, and counts calls."""

    def __init__(self, deck_catalogue: DeckCatalogue | None = None, error: Exception | None = None) -> None:
        self._deck_catalogue = deck_catalogue
        self._error = error
        self.load_count = 0

    def __call__(self) -> DeckCatalogue:
        self.load_count += 1
        if self._error is not None:
            raise self._error
        assert self._deck_catalogue is not None
        return self._deck_catalogue


class FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakePrefixContext:
    """Stands in for discord.ext.commands.Context: records what the bot sends."""

    def __init__(
        self,
        guild_id: int | None,
        message_content: str,
        prefix: str = "?",
        send_error: Exception | None = None,
    ) -> None:
        self.guild = None if guild_id is None else FakeGuild(guild_id)
        self.message = FakeMessage(message_content)
        self.prefix = prefix
        # The command the framework resolved; None, as for an unknown command.
        self.command = None
        self.sent_texts: list[str] = []
        self._send_error = send_error

    async def send(self, content: str) -> None:
        if self._send_error is not None:
            raise self._send_error
        self.sent_texts.append(content)


class FakeHttpResponse:
    """The two attributes discord.HTTPException reads from a response."""

    def __init__(self, status: int, reason: str) -> None:
        self.status = status
        self.reason = reason


class FakeInteractionResponse:
    """Stands in for discord.InteractionResponse: records each reply and its visibility."""

    def __init__(self, send_error: Exception | None) -> None:
        self.sent_replies: list[tuple[str, bool]] = []
        self._send_error = send_error

    async def send_message(self, content: str, *, ephemeral: bool) -> None:
        if self._send_error is not None:
            raise self._send_error
        self.sent_replies.append((content, ephemeral))


class FakeInteraction:
    """Stands in for discord.Interaction: the guild it came from and its response."""

    def __init__(self, guild_id: int | None, send_error: Exception | None = None) -> None:
        self.guild_id = guild_id
        self.response = FakeInteractionResponse(send_error)


class FakeCommandTree:
    """Stands in for discord.app_commands.CommandTree during a sync.

    The test supplies any error a guild's sync should raise, so this module does
    not need to import discord.
    """

    def __init__(self, sync_errors_by_guild_id: Mapping[int, Exception] | None = None) -> None:
        self.copied_to_guild_ids: list[int] = []
        self.synced_targets: list[int | None] = []
        self._sync_errors_by_guild_id = dict(sync_errors_by_guild_id or {})

    def copy_global_to(self, *, guild: FakeGuild) -> None:
        self.copied_to_guild_ids.append(guild.id)

    async def sync(self, *, guild: FakeGuild | None = None) -> list[object]:
        target_guild_id = None if guild is None else guild.id
        if target_guild_id is not None and target_guild_id in self._sync_errors_by_guild_id:
            raise self._sync_errors_by_guild_id[target_guild_id]
        self.synced_targets.append(target_guild_id)
        return [object(), object(), object()]


SYNTHETIC_TOKEN = "synthetic.bot.token-not-a-real-credential"  # noqa: S105  # a fixture, deliberately fake


@pytest.fixture
def restore_root_logging() -> Iterator[None]:
    # Startup configures the root logger; each test that runs it gets the root
    # logger back as it found it, closing any file it opened.
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    yield
    for added_handler in [handler for handler in root_logger.handlers if handler not in original_handlers]:
        root_logger.removeHandler(added_handler)
        added_handler.close()
    root_logger.setLevel(original_level)
