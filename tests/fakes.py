"""Stand-ins for Discord objects and builders for synthetic decks, so commands run without Discord.

The real card text is third party data and never appears here.
"""

from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path, PurePosixPath

from critdeck.lib.deck_files import Card, CardEffect, DeckCatalogue, StrengthTier

SYNTHETIC_TOKEN = "synthetic.bot.token-not-a-real-credential"  # noqa: S105
SYNTHETIC_EFFECTS = (
    {"damageType": "Bludgeoning", "value": "Synthetic bludgeoning effect"},
    {"damageType": "Piercing", "value": "Synthetic piercing effect"},
)


def run(coroutine):
    return asyncio.run(coroutine)


class Guild:
    def __init__(self, guild_id: int = 111) -> None:
        self.id = guild_id


class Sent:
    """A message the bot sent, and whether only the person who asked could see it."""

    def __init__(self, content: str, private: bool) -> None:
        self.content = content
        self.private = private


class Ctx:
    """A command context: slash=True for /commands, False for typed prefix commands."""

    def __init__(self, guild: Guild | None = None, *, slash: bool = True, content: str = "", prefix: str = "?") -> None:
        self.guild = guild
        self.interaction = types.SimpleNamespace(data={}) if slash else None
        self.message = types.SimpleNamespace(content=content)
        self.prefix = prefix
        self.command = None
        self.cog = None
        self.sent: list[Sent] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> Sent:
        message = Sent(content, ephemeral)
        self.sent.append(message)
        return message

    @property
    def last(self) -> Sent:
        return self.sent[-1]


class FakeCardShuffler:
    """Shuffles by reversing, so a test can predict the order, and counts shuffles."""

    def __init__(self) -> None:
        self.shuffle_count = 0

    def shuffle(self, cards_to_shuffle: list[Card], /) -> None:
        self.shuffle_count += 1
        cards_to_shuffle.reverse()


class FakeCommandTree:
    """Records slash command syncs; the test supplies any error a guild's sync should raise."""

    def __init__(self, sync_errors_by_guild_id: dict[int, Exception] | None = None) -> None:
        self.copied_to_guild_ids: list[int] = []
        self.synced_targets: list[int | None] = []
        self.sync_errors_by_guild_id = sync_errors_by_guild_id or {}

    def copy_global_to(self, *, guild) -> None:
        self.copied_to_guild_ids.append(guild.id)

    async def sync(self, *, guild=None) -> list[object]:
        target_guild_id = None if guild is None else guild.id
        if target_guild_id in self.sync_errors_by_guild_id:
            raise self.sync_errors_by_guild_id[target_guild_id]
        self.synced_targets.append(target_guild_id)
        return [object(), object(), object()]


class FakeEventLoop:
    """Records signal handlers, or refuses them as the Windows event loop does."""

    def __init__(self, *, supports_signal_handlers: bool) -> None:
        self.handlers_by_signal: dict[int, object] = {}
        self.supports_signal_handlers = supports_signal_handlers

    def add_signal_handler(self, signal_number: int, handler, *handler_arguments) -> None:
        if not self.supports_signal_handlers:
            raise NotImplementedError
        self.handlers_by_signal[signal_number] = lambda: handler(*handler_arguments)


def fake_http_response(status: int, reason: str):
    """The two attributes discord.HTTPException reads from a response."""
    return types.SimpleNamespace(status=status, reason=reason)


def build_card_record(strength: str = "Setback", effects: list | None = None) -> dict:
    return {"strength": strength, "effects": list(SYNTHETIC_EFFECTS) if effects is None else effects}


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
    for subdirectory_name, named_files in (("extensions", extension_files), ("special-levels", special_level_files)):
        if named_files is None:
            continue
        subdirectory = deck_directory / subdirectory_name
        subdirectory.mkdir(exist_ok=True)
        for file_name, file_bytes in named_files.items():
            (subdirectory / file_name).write_bytes(file_bytes)
    return deck_directory


def build_synthetic_card(strength: StrengthTier, card_label: str) -> Card:
    return Card(strength, (CardEffect("Magic", f"Synthetic effect of {card_label}"),))


def build_deck_catalogue(tiered_cards, special_level_decks: dict | None = None) -> DeckCatalogue:
    return DeckCatalogue(
        tiered_cards=tuple(tiered_cards),
        special_level_decks={level: tuple(cards) for level, cards in (special_level_decks or {}).items()},
        loaded_files=(PurePosixPath("player-deck.json"),),
        left_out_files=(),
    )


ONE_CARD_PER_TIER = tuple(build_synthetic_card(tier, tier.strength_name) for tier in StrengthTier)
