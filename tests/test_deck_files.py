"""Deck files: parsing, validation and loading of decks/, against synthetic fixtures (critdeck.lib.deck_files)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from critdeck.lib.deck_files import (
    MAXIMUM_PARTY_LEVEL,
    MINIMUM_PARTY_LEVEL,
    MAXIMUM_DECK_FILE_BYTES,
    MAXIMUM_DECK_FILES_PER_DIRECTORY,
    MAXIMUM_JSON_NESTING_DEPTH,
    BaseDeckRejectedError,
    Card,
    CardEffect,
    DeckFileRejectedError,
    DeckFileRejectionReason,
    LeftOutDeckFile,
    StrengthTier,
    load_deck_catalogue,
    parse_special_level_deck_file,
    is_ordinary_party_level,
    parse_tiered_deck_file,
)
from tests.conftest import REAL_DECK_DIRECTORY
from tests.fakes import (
    build_card_record,
    build_special_level_deck_bytes,
    build_tiered_deck_bytes,
    encode_deck_document,
    write_deck_directory,
)

Reason = DeckFileRejectionReason


def test_parse_tiered_deck_file_returns_cards_with_effects_in_order() -> None:
    deck_bytes = encode_deck_document(
        {
            "cards": [
                build_card_record(
                    "Dangerous",
                    [
                        {"damageType": "Slashing", "value": "First"},
                        {"damageType": "Magic", "value": "Second"},
                    ],
                )
            ]
        }
    )

    assert parse_tiered_deck_file(deck_bytes) == (
        Card(
            StrengthTier.DANGEROUS,
            (CardEffect("Slashing", "First"), CardEffect("Magic", "Second")),
        ),
    )


@pytest.mark.parametrize("padded_strength", ["Deadly\r\n", "\nDeadly", "\r\nDeadly\r\n"])
def test_parse_tiered_deck_file_trims_line_endings_from_strength(padded_strength: str) -> None:
    # The Go bot trimmed CR and LF from both ends before comparing; kept for parity.
    cards = parse_tiered_deck_file(build_tiered_deck_bytes([padded_strength]))

    assert cards[0].strength is StrengthTier.DEADLY


def test_parse_tiered_deck_file_accepts_crlf_line_endings() -> None:
    deck_bytes = build_tiered_deck_bytes(["Setback"]).replace(b", ", b",\r\n")

    assert len(parse_tiered_deck_file(deck_bytes)) == 1


TIERED_REJECTIONS = {
    "not_utf8": (b'{"cards": ["\xff"]}', Reason.NOT_UTF8),
    "byte_order_mark": (b"\xef\xbb\xbf" + build_tiered_deck_bytes(["Setback"]), Reason.MALFORMED_JSON),
    "malformed_json": (b'{"cards": [', Reason.MALFORMED_JSON),
    "not_a_number_constant": (b'{"cards": [], "x": NaN}', Reason.MALFORMED_JSON),
    # Under the size bound. Whether Python's own parser gives up on this depends on
    # the platform's stack (it parsed on Linux with Python 3.14), so the bound is ours.
    "deeply_nested": (b"[" * 100_000 + b"]" * 100_000, Reason.NESTED_TOO_DEEPLY),
    "one_level_too_deep": (
        b'{"cards": [' + b"[" * MAXIMUM_JSON_NESTING_DEPTH + b"]" * MAXIMUM_JSON_NESTING_DEPTH + b"]}",
        Reason.NESTED_TOO_DEEPLY,
    ),
    "duplicate_key": (b'{"cards": [], "cards": []}', Reason.DUPLICATE_KEY),
    "top_level_array": (b"[]", Reason.WRONG_TYPE),
    "unknown_top_level_field": (
        encode_deck_document({"cards": [build_card_record()], "edition": 2}),
        Reason.UNKNOWN_FIELD,
    ),
    "level_in_tiered_file": (
        encode_deck_document({"cards": [build_card_record()], "level": 666}),
        Reason.UNKNOWN_FIELD,
    ),
    "missing_cards": (encode_deck_document({}), Reason.MISSING_FIELD),
    "cards_not_a_list": (encode_deck_document({"cards": {}}), Reason.WRONG_TYPE),
    "no_cards": (encode_deck_document({"cards": []}), Reason.NO_CARDS),
    "card_not_an_object": (encode_deck_document({"cards": ["Setback"]}), Reason.WRONG_TYPE),
    "card_unknown_field": (
        encode_deck_document({"cards": [{**build_card_record(), "art": "x"}]}),
        Reason.UNKNOWN_FIELD,
    ),
    "card_missing_strength": (
        encode_deck_document({"cards": [{"effects": build_card_record()["effects"]}]}),
        Reason.MISSING_FIELD,
    ),
    "card_missing_effects": (
        encode_deck_document({"cards": [{"strength": "Setback"}]}),
        Reason.MISSING_FIELD,
    ),
    "unknown_strength": (build_tiered_deck_bytes(["Mild"]), Reason.UNKNOWN_STRENGTH),
    "strength_wrong_case": (build_tiered_deck_bytes(["setback"]), Reason.UNKNOWN_STRENGTH),
    "strength_not_a_string": (
        encode_deck_document({"cards": [build_card_record(strength=5)]}),  # type: ignore[arg-type]
        Reason.WRONG_TYPE,
    ),
    "effects_not_a_list": (
        encode_deck_document({"cards": [{"strength": "Setback", "effects": "x"}]}),
        Reason.WRONG_TYPE,
    ),
    "no_effects": (encode_deck_document({"cards": [build_card_record(effects=[])]}), Reason.NO_EFFECTS),
    "effect_unknown_field": (
        encode_deck_document(
            {"cards": [build_card_record(effects=[{"damageType": "Magic", "value": "x", "dice": "d6"}])]}
        ),
        Reason.UNKNOWN_FIELD,
    ),
    "effect_missing_value": (
        encode_deck_document({"cards": [build_card_record(effects=[{"damageType": "Magic"}])]}),
        Reason.MISSING_FIELD,
    ),
    "effect_value_not_a_string": (
        encode_deck_document({"cards": [build_card_record(effects=[{"damageType": "Magic", "value": 3}])]}),
        Reason.WRONG_TYPE,
    ),
}


@pytest.mark.parametrize(
    ("deck_bytes", "expected_reason"), TIERED_REJECTIONS.values(), ids=TIERED_REJECTIONS.keys()
)
def test_parse_tiered_deck_file_rejects_invalid_file(
    deck_bytes: bytes, expected_reason: DeckFileRejectionReason
) -> None:
    with pytest.raises(DeckFileRejectedError) as rejection:
        parse_tiered_deck_file(deck_bytes)

    assert rejection.value.reason is expected_reason


def test_parse_tiered_deck_file_refuses_file_one_byte_over_the_bound() -> None:
    valid_bytes = build_tiered_deck_bytes(["Setback"])
    oversized_bytes = valid_bytes + b" " * (MAXIMUM_DECK_FILE_BYTES + 1 - len(valid_bytes))

    with pytest.raises(DeckFileRejectedError) as rejection:
        parse_tiered_deck_file(oversized_bytes)

    assert rejection.value.reason is Reason.TOO_LARGE


def test_parse_tiered_deck_file_accepts_file_exactly_at_the_bound() -> None:
    valid_bytes = build_tiered_deck_bytes(["Setback"])
    bound_sized_bytes = valid_bytes + b" " * (MAXIMUM_DECK_FILE_BYTES - len(valid_bytes))

    assert len(parse_tiered_deck_file(bound_sized_bytes)) == 1


def test_deck_file_rejection_message_never_contains_file_content() -> None:
    content_marker = "SYNTHETIC-CONTENT-MARKER"

    with pytest.raises(DeckFileRejectedError) as rejection:
        parse_tiered_deck_file(build_tiered_deck_bytes([content_marker]))

    assert content_marker not in str(rejection.value)
    assert content_marker not in repr(rejection.value)


@pytest.mark.parametrize("special_level", [666, -1, 3141, 0])
def test_parse_special_level_deck_file_returns_level_and_cards(special_level: int) -> None:
    special_level_deck = parse_special_level_deck_file(build_special_level_deck_bytes(special_level))

    assert special_level_deck.level == special_level
    assert len(special_level_deck.cards) == 1


SPECIAL_LEVEL_REJECTIONS = {
    "missing_level": (encode_deck_document({"cards": [build_card_record()]}), Reason.MISSING_FIELD),
    "boolean_level": (
        encode_deck_document({"level": True, "cards": [build_card_record()]}),
        Reason.WRONG_TYPE,
    ),
    "decimal_level": (
        encode_deck_document({"level": 3.14, "cards": [build_card_record()]}),
        Reason.WRONG_TYPE,
    ),
    "text_level": (encode_deck_document({"level": "666", "cards": [build_card_record()]}), Reason.WRONG_TYPE),
    "no_cards": (encode_deck_document({"level": 666, "cards": []}), Reason.NO_CARDS),
    "unknown_field": (
        encode_deck_document({"level": 666, "cards": [build_card_record()], "name": "x"}),
        Reason.UNKNOWN_FIELD,
    ),
}


@pytest.mark.parametrize(
    ("deck_bytes", "expected_reason"), SPECIAL_LEVEL_REJECTIONS.values(), ids=SPECIAL_LEVEL_REJECTIONS.keys()
)
def test_parse_special_level_deck_file_rejects_invalid_file(
    deck_bytes: bytes, expected_reason: DeckFileRejectionReason
) -> None:
    with pytest.raises(DeckFileRejectedError) as rejection:
        parse_special_level_deck_file(deck_bytes)

    assert rejection.value.reason is expected_reason


def test_load_deck_catalogue_with_base_only(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(tmp_path, build_tiered_deck_bytes(["Setback", "Deadly"]))

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert [card.strength for card in deck_catalogue.tiered_cards] == [
        StrengthTier.SETBACK,
        StrengthTier.DEADLY,
    ]
    assert deck_catalogue.loaded_files == (PurePosixPath("player-deck.json"),)
    assert deck_catalogue.left_out_files == ()
    assert deck_catalogue.special_level_decks == {}


def test_load_deck_catalogue_merges_extensions_after_base_in_file_name_order(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        extension_files={
            "zombie-extension.json": build_tiered_deck_bytes(["Deadly"]),
            "halloween-extension.json": build_tiered_deck_bytes(["Dangerous", "Dangerous"]),
        },
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert [card.strength for card in deck_catalogue.tiered_cards] == [
        StrengthTier.SETBACK,
        StrengthTier.DANGEROUS,
        StrengthTier.DANGEROUS,
        StrengthTier.DEADLY,
    ]
    assert deck_catalogue.loaded_files == (
        PurePosixPath("player-deck.json"),
        PurePosixPath("extensions/halloween-extension.json"),
        PurePosixPath("extensions/zombie-extension.json"),
    )


def test_load_deck_catalogue_leaves_out_broken_extension_and_keeps_the_rest(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        extension_files={
            "broken-extension.json": b'{"cards": [',
            "good-extension.json": build_tiered_deck_bytes(["Deadly"]),
        },
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert len(deck_catalogue.tiered_cards) == 2
    assert deck_catalogue.left_out_files == (
        LeftOutDeckFile(PurePosixPath("extensions/broken-extension.json"), Reason.MALFORMED_JSON),
    )


def test_load_deck_catalogue_refuses_missing_base(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path, None, extension_files={"halloween-extension.json": build_tiered_deck_bytes(["Deadly"])}
    )

    with pytest.raises(BaseDeckRejectedError) as rejection:
        load_deck_catalogue(deck_directory)

    assert rejection.value.reason is Reason.FILE_MISSING


def test_load_deck_catalogue_refuses_broken_base(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(tmp_path, build_tiered_deck_bytes(["Mild"]))

    with pytest.raises(BaseDeckRejectedError) as rejection:
        load_deck_catalogue(deck_directory)

    assert rejection.value.reason is Reason.UNKNOWN_STRENGTH


def test_load_deck_catalogue_refuses_missing_deck_directory(tmp_path: Path) -> None:
    with pytest.raises(BaseDeckRejectedError) as rejection:
        load_deck_catalogue(tmp_path / "no-such-directory")

    assert rejection.value.reason is Reason.FILE_MISSING


def test_load_deck_catalogue_refuses_base_file_over_the_bound_on_disk(tmp_path: Path) -> None:
    valid_bytes = build_tiered_deck_bytes(["Setback"])
    deck_directory = write_deck_directory(
        tmp_path, valid_bytes + b" " * (MAXIMUM_DECK_FILE_BYTES + 1 - len(valid_bytes))
    )

    with pytest.raises(BaseDeckRejectedError) as rejection:
        load_deck_catalogue(deck_directory)

    assert rejection.value.reason is Reason.TOO_LARGE


def test_load_deck_catalogue_maps_special_levels(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        special_level_files={
            "beast.json": build_special_level_deck_bytes(666),
            "below-zero.json": build_special_level_deck_bytes(-1, card_count=3),
        },
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert {level: len(cards) for level, cards in deck_catalogue.special_level_decks.items()} == {
        666: 1,
        -1: 3,
    }
    assert PurePosixPath("special-levels/beast.json") in deck_catalogue.loaded_files


def test_load_deck_catalogue_leaves_out_every_file_claiming_the_same_special_level(
    tmp_path: Path,
) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        special_level_files={
            "first-claim.json": build_special_level_deck_bytes(666),
            "second-claim.json": build_special_level_deck_bytes(666),
            "unrelated.json": build_special_level_deck_bytes(-1),
        },
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert set(deck_catalogue.special_level_decks) == {-1}
    assert deck_catalogue.left_out_files == (
        LeftOutDeckFile(PurePosixPath("special-levels/first-claim.json"), Reason.DUPLICATE_SPECIAL_LEVEL),
        LeftOutDeckFile(PurePosixPath("special-levels/second-claim.json"), Reason.DUPLICATE_SPECIAL_LEVEL),
    )


def test_load_deck_catalogue_reports_unexpected_entries(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        extension_files={"notes.txt": b"not a deck"},
    )
    (deck_directory / "stray.json").write_bytes(build_tiered_deck_bytes(["Deadly"]))
    (deck_directory / "extensions" / "nested").mkdir()

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert len(deck_catalogue.tiered_cards) == 1
    assert deck_catalogue.left_out_files == (
        LeftOutDeckFile(PurePosixPath("extensions/nested"), Reason.UNEXPECTED_ENTRY),
        LeftOutDeckFile(PurePosixPath("extensions/notes.txt"), Reason.UNEXPECTED_ENTRY),
        LeftOutDeckFile(PurePosixPath("stray.json"), Reason.UNEXPECTED_ENTRY),
    )


def test_load_deck_catalogue_leaves_out_directory_with_too_many_files(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        extension_files={
            f"extension-{file_index:03}.json": build_tiered_deck_bytes(["Deadly"])
            for file_index in range(MAXIMUM_DECK_FILES_PER_DIRECTORY + 1)
        },
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert len(deck_catalogue.tiered_cards) == 1
    assert deck_catalogue.left_out_files == (
        LeftOutDeckFile(PurePosixPath("extensions"), Reason.TOO_MANY_FILES),
    )


def test_load_deck_catalogue_accepts_directory_with_exactly_the_maximum_files(tmp_path: Path) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        extension_files={
            f"extension-{file_index:03}.json": build_tiered_deck_bytes(["Deadly"])
            for file_index in range(MAXIMUM_DECK_FILES_PER_DIRECTORY)
        },
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert len(deck_catalogue.tiered_cards) == 1 + MAXIMUM_DECK_FILES_PER_DIRECTORY
    assert deck_catalogue.left_out_files == ()


def test_strength_tier_minimum_party_levels_match_the_go_thresholds() -> None:
    assert {tier: tier.minimum_party_level for tier in StrengthTier} == {
        StrengthTier.SETBACK: 0,
        StrengthTier.DANGEROUS: 5,
        StrengthTier.LIFE_THREATENING: 9,
        StrengthTier.DEADLY: 13,
    }


def test_load_deck_catalogue_leaves_out_subdirectory_that_cannot_be_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        extension_files={"halloween-extension.json": build_tiered_deck_bytes(["Deadly"])},
    )
    unlistable_directory = deck_directory / "extensions"
    original_iterdir = Path.iterdir

    def iterdir_failing_for_extensions(directory: Path) -> object:
        if directory == unlistable_directory:
            raise PermissionError(directory)
        return original_iterdir(directory)

    monkeypatch.setattr(Path, "iterdir", iterdir_failing_for_extensions)

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert len(deck_catalogue.tiered_cards) == 1
    assert deck_catalogue.left_out_files == (LeftOutDeckFile(PurePosixPath("extensions"), Reason.UNREADABLE),)


def test_load_deck_catalogue_refuses_deck_directory_that_cannot_be_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck_directory = write_deck_directory(tmp_path, build_tiered_deck_bytes(["Setback"]))
    original_iterdir = Path.iterdir

    def iterdir_failing_for_deck_directory(directory: Path) -> object:
        if directory == deck_directory:
            raise PermissionError(directory)
        return original_iterdir(directory)

    monkeypatch.setattr(Path, "iterdir", iterdir_failing_for_deck_directory)

    with pytest.raises(BaseDeckRejectedError) as rejection:
        load_deck_catalogue(deck_directory)

    assert rejection.value.reason is Reason.UNREADABLE


@pytest.mark.parametrize("ordinary_level", [MINIMUM_PARTY_LEVEL, 7, MAXIMUM_PARTY_LEVEL])
def test_load_deck_catalogue_leaves_out_special_level_inside_the_ordinary_range(
    tmp_path: Path, ordinary_level: int
) -> None:
    # An ordinary level already has a deck; a file claiming one would silently
    # replace it for every table playing at that level.
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        special_level_files={"clash.json": build_special_level_deck_bytes(ordinary_level)},
    )

    deck_catalogue = load_deck_catalogue(deck_directory)

    assert deck_catalogue.special_level_decks == {}
    assert deck_catalogue.left_out_files == (
        LeftOutDeckFile(
            PurePosixPath("special-levels/clash.json"), Reason.SPECIAL_LEVEL_INSIDE_ORDINARY_RANGE
        ),
    )


@pytest.mark.parametrize("outside_level", [MINIMUM_PARTY_LEVEL - 1, MAXIMUM_PARTY_LEVEL + 1])
def test_load_deck_catalogue_accepts_special_level_just_outside_the_ordinary_range(
    tmp_path: Path, outside_level: int
) -> None:
    deck_directory = write_deck_directory(
        tmp_path,
        build_tiered_deck_bytes(["Setback"]),
        special_level_files={"edge.json": build_special_level_deck_bytes(outside_level)},
    )

    assert set(load_deck_catalogue(deck_directory).special_level_decks) == {outside_level}


def test_ordinary_party_level_range_is_one_to_twenty() -> None:
    # There is no level 0 in D&D, so the range starts at 1 (author's decision,
    # 24 October 2026; the Go bot accepted any integer).
    assert (MINIMUM_PARTY_LEVEL, MAXIMUM_PARTY_LEVEL) == (1, 20)


@pytest.mark.parametrize(
    ("party_level", "expected_ordinary"),
    [(-1, False), (0, False), (1, True), (2, True), (19, True), (20, True), (21, False), (666, False)],
)
def test_is_ordinary_party_level_at_and_around_the_bounds(party_level: int, expected_ordinary: bool) -> None:
    assert is_ordinary_party_level(party_level) is expected_ordinary


REAL_BASE_DECK_PATH = REAL_DECK_DIRECTORY / "player-deck.json"
needs_real_base_deck = pytest.mark.skipif(
    not REAL_BASE_DECK_PATH.is_file(),
    reason="decks/player-deck.json is third party data, gitignored and not supplied here",
)


@needs_real_base_deck
def test_real_base_deck_card_count_per_strength_tier() -> None:
    real_cards = parse_tiered_deck_file(REAL_BASE_DECK_PATH.read_bytes())

    assert {tier: sum(card.strength is tier for card in real_cards) for tier in StrengthTier} == {
        StrengthTier.SETBACK: 15,
        StrengthTier.DANGEROUS: 15,
        StrengthTier.LIFE_THREATENING: 16,
        StrengthTier.DEADLY: 4,
    }


@needs_real_base_deck
@pytest.mark.parametrize(
    ("party_level", "expected_card_count"),
    [(1, 15), (4, 15), (5, 30), (8, 30), (9, 46), (12, 46), (13, 50), (20, 50)],
)
def test_real_base_deck_cards_available_at_party_level(party_level: int, expected_card_count: int) -> None:
    real_cards = parse_tiered_deck_file(REAL_BASE_DECK_PATH.read_bytes())

    assert sum(card.strength.minimum_party_level <= party_level for card in real_cards) == expected_card_count


def test_nesting_at_the_bound_is_accepted_and_brackets_inside_text_do_not_count() -> None:
    # A deck file nests five deep (object, cards, card, effects, effect); the bound
    # leaves room above that, and card text full of brackets is still just text.
    bracket_heavy_text = "[" * (MAXIMUM_JSON_NESTING_DEPTH * 2) + '{\\"quoted\\"}'
    deck_bytes = encode_deck_document(
        {"cards": [build_card_record(effects=[{"damageType": "Magic", "value": bracket_heavy_text}])]}
    )

    assert parse_tiered_deck_file(deck_bytes)[0].effects[0].value == bracket_heavy_text
