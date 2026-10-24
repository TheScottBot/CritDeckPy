"""Deck files: parsing, validation and loading of the deck directory.

The deck directory holds a base deck, any number of extensions merged into it by
strength tier, and special level decks dealt whole when a party level claims
them. Every file is read again each time a deck is built, so files can be added
or removed without a restart.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Never

if TYPE_CHECKING:
    from collections.abc import Mapping

# D&D characters run from level 1 to level 20. Anything else is a typo or a
# special level, which a deck file has to claim. The Go bot accepted any integer.
MINIMUM_PARTY_LEVEL = 1
MAXIMUM_PARTY_LEVEL = 20

BASE_DECK_FILE_NAME = "player-deck.json"
EXTENSIONS_DIRECTORY_NAME = "extensions"
SPECIAL_LEVELS_DIRECTORY_NAME = "special-levels"
DECK_FILE_SUFFIX = ".json"

# The real base deck is 47574 bytes. Five times that leaves room for a much larger
# deck while refusing anything that is clearly not one before it is parsed.
MAXIMUM_DECK_FILE_BYTES = 262_144
# Bounds the work a single new deck can cause, since every file is read each time.
MAXIMUM_DECK_FILES_PER_DIRECTORY = 100

TIERED_DECK_FIELDS = frozenset({"cards"})
SPECIAL_LEVEL_DECK_FIELDS = frozenset({"level", "cards"})
CARD_FIELDS = frozenset({"strength", "effects"})
EFFECT_FIELDS = frozenset({"damageType", "value"})


class StrengthTier(enum.Enum):
    SETBACK = ("Setback", 0)
    DANGEROUS = ("Dangerous", 5)
    LIFE_THREATENING = ("Life Threatening", 9)
    DEADLY = ("Deadly", 13)

    def __init__(self, strength_name: str, minimum_party_level: int) -> None:
        self.strength_name = strength_name
        self.minimum_party_level = minimum_party_level


STRENGTH_TIERS_BY_NAME = {tier.strength_name: tier for tier in StrengthTier}


class DeckFileRejectionReason(enum.Enum):
    FILE_MISSING = "file missing"
    UNREADABLE = "file unreadable"
    TOO_LARGE = "file over the size bound"
    TOO_MANY_FILES = "directory over the file count bound"
    UNEXPECTED_ENTRY = "unexpected entry in the deck directory"
    NOT_UTF8 = "not valid UTF-8"
    MALFORMED_JSON = "malformed JSON"
    DUPLICATE_KEY = "duplicate key"
    WRONG_TYPE = "wrong type"
    UNKNOWN_FIELD = "unknown field"
    MISSING_FIELD = "missing field"
    UNKNOWN_STRENGTH = "unknown strength"
    NO_CARDS = "no cards"
    NO_EFFECTS = "card with no effects"
    DUPLICATE_SPECIAL_LEVEL = "special level claimed by more than one file"
    SPECIAL_LEVEL_INSIDE_ORDINARY_RANGE = "special level inside the ordinary party level range"


class DeckFileRejectedError(Exception):
    # Only the reason category is carried. Deck files are third party text, and a
    # message that quoted them would put that text in the logs.
    def __init__(self, reason: DeckFileRejectionReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class BaseDeckRejectedError(Exception):
    def __init__(self, reason: DeckFileRejectionReason) -> None:
        super().__init__(f"base deck rejected: {reason.value}")
        self.reason = reason


@dataclass(frozen=True)
class CardEffect:
    damage_type: str
    value: str


@dataclass(frozen=True)
class Card:
    strength: StrengthTier
    effects: tuple[CardEffect, ...]


@dataclass(frozen=True)
class SpecialLevelDeck:
    level: int
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class LeftOutDeckFile:
    relative_path: PurePosixPath
    reason: DeckFileRejectionReason


@dataclass(frozen=True)
class DeckCatalogue:
    tiered_cards: tuple[Card, ...]
    special_level_decks: Mapping[int, tuple[Card, ...]]
    loaded_files: tuple[PurePosixPath, ...]
    left_out_files: tuple[LeftOutDeckFile, ...]


def is_ordinary_party_level(party_level: int) -> bool:
    return MINIMUM_PARTY_LEVEL <= party_level <= MAXIMUM_PARTY_LEVEL


def parse_tiered_deck_file(file_bytes: bytes) -> tuple[Card, ...]:
    deck_document = _decode_deck_document(file_bytes, TIERED_DECK_FIELDS)
    return _parse_cards(deck_document["cards"])


def parse_special_level_deck_file(file_bytes: bytes) -> SpecialLevelDeck:
    deck_document = _decode_deck_document(file_bytes, SPECIAL_LEVEL_DECK_FIELDS)
    level = deck_document["level"]
    # bool is a subclass of int in Python, so true would otherwise be level 1.
    if not isinstance(level, int) or isinstance(level, bool):
        _reject(DeckFileRejectionReason.WRONG_TYPE)
    return SpecialLevelDeck(level, _parse_cards(deck_document["cards"]))


def load_deck_catalogue(deck_directory: Path) -> DeckCatalogue:
    base_relative_path = PurePosixPath(BASE_DECK_FILE_NAME)
    try:
        base_cards = parse_tiered_deck_file(_read_bounded_file(deck_directory / BASE_DECK_FILE_NAME))
    except DeckFileRejectedError as base_rejection:
        raise BaseDeckRejectedError(base_rejection.reason) from base_rejection

    loaded_files = [base_relative_path]
    try:
        top_level_entries = sorted(deck_directory.iterdir())
    except OSError as listing_error:
        # Without a listing the extensions and special levels cannot be found, and
        # a deck built from the base alone would quietly drop an event in progress.
        raise BaseDeckRejectedError(DeckFileRejectionReason.UNREADABLE) from listing_error
    left_out_files = [
        LeftOutDeckFile(PurePosixPath(unexpected_entry.name), DeckFileRejectionReason.UNEXPECTED_ENTRY)
        for unexpected_entry in top_level_entries
        if unexpected_entry.name
        not in {BASE_DECK_FILE_NAME, EXTENSIONS_DIRECTORY_NAME, SPECIAL_LEVELS_DIRECTORY_NAME}
    ]

    tiered_cards = list(base_cards)
    for extension_relative_path, extension_bytes in _deck_files_in_subdirectory(
        deck_directory, EXTENSIONS_DIRECTORY_NAME, left_out_files
    ):
        try:
            tiered_cards.extend(parse_tiered_deck_file(extension_bytes))
        except DeckFileRejectedError as extension_rejection:
            left_out_files.append(LeftOutDeckFile(extension_relative_path, extension_rejection.reason))
            continue
        loaded_files.append(extension_relative_path)

    special_level_decks = _load_special_level_decks(deck_directory, loaded_files, left_out_files)

    return DeckCatalogue(
        tiered_cards=tuple(tiered_cards),
        special_level_decks=special_level_decks,
        loaded_files=tuple(loaded_files),
        left_out_files=tuple(sorted(left_out_files, key=lambda left_out_file: left_out_file.relative_path)),
    )


def _load_special_level_decks(
    deck_directory: Path, loaded_files: list[PurePosixPath], left_out_files: list[LeftOutDeckFile]
) -> dict[int, tuple[Card, ...]]:
    special_level_claims: dict[int, list[tuple[PurePosixPath, SpecialLevelDeck]]] = {}
    for special_relative_path, special_bytes in _deck_files_in_subdirectory(
        deck_directory, SPECIAL_LEVELS_DIRECTORY_NAME, left_out_files
    ):
        try:
            special_level_deck = parse_special_level_deck_file(special_bytes)
        except DeckFileRejectedError as special_rejection:
            left_out_files.append(LeftOutDeckFile(special_relative_path, special_rejection.reason))
            continue
        # An ordinary level already has a deck; a special deck claiming one would
        # silently replace it for every table playing at that level.
        if is_ordinary_party_level(special_level_deck.level):
            left_out_files.append(
                LeftOutDeckFile(
                    special_relative_path, DeckFileRejectionReason.SPECIAL_LEVEL_INSIDE_ORDINARY_RANGE
                )
            )
            continue
        special_level_claims.setdefault(special_level_deck.level, []).append(
            (special_relative_path, special_level_deck)
        )

    special_level_decks: dict[int, tuple[Card, ...]] = {}
    for level, claims in special_level_claims.items():
        # Picking one claimant would be a silent guess about which file was meant,
        # so a contested level is dealt by nobody until the clash is resolved.
        if len(claims) > 1:
            left_out_files.extend(
                LeftOutDeckFile(claim_path, DeckFileRejectionReason.DUPLICATE_SPECIAL_LEVEL)
                for claim_path, _ in claims
            )
            continue
        claim_path, special_level_deck = claims[0]
        loaded_files.append(claim_path)
        special_level_decks[level] = special_level_deck.cards
    return special_level_decks


def _deck_files_in_subdirectory(
    deck_directory: Path, subdirectory_name: str, left_out_files: list[LeftOutDeckFile]
) -> list[tuple[PurePosixPath, bytes]]:
    subdirectory = deck_directory / subdirectory_name
    if not subdirectory.is_dir():
        return []
    try:
        subdirectory_entries = sorted(subdirectory.iterdir())
    except OSError:
        left_out_files.append(
            LeftOutDeckFile(PurePosixPath(subdirectory_name), DeckFileRejectionReason.UNREADABLE)
        )
        return []
    if len(subdirectory_entries) > MAXIMUM_DECK_FILES_PER_DIRECTORY:
        left_out_files.append(
            LeftOutDeckFile(PurePosixPath(subdirectory_name), DeckFileRejectionReason.TOO_MANY_FILES)
        )
        return []

    readable_deck_files: list[tuple[PurePosixPath, bytes]] = []
    for subdirectory_entry in subdirectory_entries:
        entry_relative_path = PurePosixPath(subdirectory_name, subdirectory_entry.name)
        if not subdirectory_entry.is_file() or subdirectory_entry.suffix != DECK_FILE_SUFFIX:
            left_out_files.append(
                LeftOutDeckFile(entry_relative_path, DeckFileRejectionReason.UNEXPECTED_ENTRY)
            )
            continue
        try:
            readable_deck_files.append((entry_relative_path, _read_bounded_file(subdirectory_entry)))
        except DeckFileRejectedError as read_rejection:
            left_out_files.append(LeftOutDeckFile(entry_relative_path, read_rejection.reason))
    return readable_deck_files


def _read_bounded_file(deck_file_path: Path) -> bytes:
    # Reading one byte past the bound proves a file is over it without trusting a
    # size reported before the read, which could change in between.
    try:
        with deck_file_path.open("rb") as deck_file:
            file_bytes = deck_file.read(MAXIMUM_DECK_FILE_BYTES + 1)
    except FileNotFoundError:
        _reject(DeckFileRejectionReason.FILE_MISSING)
    except OSError:
        _reject(DeckFileRejectionReason.UNREADABLE)
    if len(file_bytes) > MAXIMUM_DECK_FILE_BYTES:
        _reject(DeckFileRejectionReason.TOO_LARGE)
    return file_bytes


def _decode_deck_document(file_bytes: bytes, permitted_fields: frozenset[str]) -> dict[str, object]:
    if len(file_bytes) > MAXIMUM_DECK_FILE_BYTES:
        _reject(DeckFileRejectionReason.TOO_LARGE)
    try:
        file_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _reject(DeckFileRejectionReason.NOT_UTF8)
    try:
        deck_document: object = json.loads(
            file_text,
            object_pairs_hook=_build_object_rejecting_duplicate_keys,
            parse_constant=_reject_non_standard_constant,
        )
    except (json.JSONDecodeError, RecursionError):
        _reject(DeckFileRejectionReason.MALFORMED_JSON)
    return _require_object_with_fields(deck_document, permitted_fields)


def _build_object_rejecting_duplicate_keys(key_value_pairs: list[tuple[str, object]]) -> dict[str, object]:
    # Python keeps the last of two equal keys silently; a deck file with both is
    # ambiguous about which was meant.
    decoded_object = dict(key_value_pairs)
    if len(decoded_object) != len(key_value_pairs):
        _reject(DeckFileRejectionReason.DUPLICATE_KEY)
    return decoded_object


def _reject_non_standard_constant(constant_name: str) -> Never:
    # NaN and Infinity are not JSON; Python accepts them unless told otherwise.
    raise json.JSONDecodeError(constant_name, constant_name, 0)


def _require_object_with_fields(candidate: object, permitted_fields: frozenset[str]) -> dict[str, object]:
    if not isinstance(candidate, dict):
        _reject(DeckFileRejectionReason.WRONG_TYPE)
    candidate_fields = set(candidate)
    if candidate_fields - permitted_fields:
        _reject(DeckFileRejectionReason.UNKNOWN_FIELD)
    if permitted_fields - candidate_fields:
        _reject(DeckFileRejectionReason.MISSING_FIELD)
    return candidate


def _parse_cards(card_records: object) -> tuple[Card, ...]:
    if not isinstance(card_records, list):
        _reject(DeckFileRejectionReason.WRONG_TYPE)
    if not card_records:
        _reject(DeckFileRejectionReason.NO_CARDS)
    return tuple(_parse_card(card_record) for card_record in card_records)


def _parse_card(card_record: object) -> Card:
    card_fields = _require_object_with_fields(card_record, CARD_FIELDS)
    strength_text = card_fields["strength"]
    if not isinstance(strength_text, str):
        _reject(DeckFileRejectionReason.WRONG_TYPE)
    # The Go bot trimmed CR and LF from both ends before comparing, so a strength
    # written with a stray line ending still matched its tier.
    strength_tier = STRENGTH_TIERS_BY_NAME.get(strength_text.strip("\r\n"))
    if strength_tier is None:
        _reject(DeckFileRejectionReason.UNKNOWN_STRENGTH)
    effect_records = card_fields["effects"]
    if not isinstance(effect_records, list):
        _reject(DeckFileRejectionReason.WRONG_TYPE)
    # A card with no effects formats as empty text, which Discord refuses to send.
    if not effect_records:
        _reject(DeckFileRejectionReason.NO_EFFECTS)
    return Card(strength_tier, tuple(_parse_effect(effect_record) for effect_record in effect_records))


def _parse_effect(effect_record: object) -> CardEffect:
    effect_fields = _require_object_with_fields(effect_record, EFFECT_FIELDS)
    damage_type = effect_fields["damageType"]
    effect_value = effect_fields["value"]
    if not isinstance(damage_type, str) or not isinstance(effect_value, str):
        _reject(DeckFileRejectionReason.WRONG_TYPE)
    return CardEffect(damage_type, effect_value)


def _reject(reason: DeckFileRejectionReason) -> Never:
    raise DeckFileRejectedError(reason)
