"""The ordinary party level range, shared by every surface."""

from __future__ import annotations

import pytest

from critdeck.core.party_levels import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL, is_ordinary_party_level


def test_ordinary_party_level_range_is_zero_to_twenty() -> None:
    assert (MINIMUM_PARTY_LEVEL, MAXIMUM_PARTY_LEVEL) == (0, 20)


@pytest.mark.parametrize(
    ("party_level", "expected_ordinary"),
    [(-1, False), (0, True), (1, True), (19, True), (20, True), (21, False), (666, False)],
)
def test_is_ordinary_party_level_at_and_around_the_bounds(party_level: int, expected_ordinary: bool) -> None:
    assert is_ordinary_party_level(party_level) is expected_ordinary
