"""The grammar of a typed party level, as in `?newdeck 7`.

Slash commands receive a typed integer from Discord; typed prefix commands
receive whatever the player wrote, so it is parsed here, strictly.
"""

from __future__ import annotations

import re

# Long enough for any ordinary level and any plausible special level, including
# a negative one; anything longer is refused rather than truncated.
MAXIMUM_PARTY_LEVEL_TEXT_LENGTH = 9

# ASCII digits only, with an optional minus for negative special levels. Python's
# int() would also accept underscores, surrounding whitespace, a plus sign and
# digits from other scripts; none of those is a level anyone means to type.
PARTY_LEVEL_TEXT_PATTERN = re.compile(r"-?[0-9]+")


def parse_party_level_text(level_text: str) -> int | None:
    if len(level_text) > MAXIMUM_PARTY_LEVEL_TEXT_LENGTH:
        return None
    if not PARTY_LEVEL_TEXT_PATTERN.fullmatch(level_text):
        return None
    return int(level_text)
