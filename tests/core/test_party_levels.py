"""The ordinary party level range, shared by every surface."""

from __future__ import annotations

import pytest

from critdeck.core.party_levels import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL, is_ordinary_party_level


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
