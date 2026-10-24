"""The ordinary party level range: the one table every surface reads.

The slash option description, the prefix grammar, the command actions and the
catalogue's special level check all take their bounds from here, so they cannot
disagree. A level outside the range is accepted only when a special level deck
claims it.
"""

from __future__ import annotations

# The Go bot accepted any integer. D&D characters run from level 1 to level 20,
# so anything else is either a typo or a special level.
MINIMUM_PARTY_LEVEL = 1
MAXIMUM_PARTY_LEVEL = 20


def is_ordinary_party_level(party_level: int) -> bool:
    return MINIMUM_PARTY_LEVEL <= party_level <= MAXIMUM_PARTY_LEVEL
