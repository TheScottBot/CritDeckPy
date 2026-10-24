"""Every user facing string the bot sends, in one place.

Strings marked as from the Go bot are copied verbatim so players see the same
text after the port. The rest are new, written for slash commands.
"""

from __future__ import annotations

from critdeck.core.catalogue import StrengthTier
from critdeck.core.party_levels import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL

# From the Go bot.
DIRECT_MESSAGE_TEXT = "This command only works in a server, not in a direct message."
# From the Go bot. Formatted with card_count.
DECK_CREATED_TEXT = "Crit deck created. It has: {card_count} cards"

NO_DECK_TEXT = "No deck here yet. Create one with /newdeck and the party level, for example /newdeck 7"
# The same text for every refused level, so it reveals nothing about which
# special levels exist.
PARTY_LEVEL_OUT_OF_RANGE_TEXT = (
    f"Please give the party level as a whole number from {MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}."
)
BASE_DECK_UNAVAILABLE_TEXT = (
    "The deck files could not be loaded, so no new deck was made. The current deck is unchanged."
)
EXTENSIONS_LEFT_OUT_TEXT = "Some deck extensions could not be loaded and were left out."

# Read from the tier table, so help can never disagree with the levels the deck
# actually uses. The first tier is always in the deck, so it is not announced.
_TIER_ARRIVALS = ", ".join(
    f"{tier.strength_name} from {tier.minimum_party_level}"
    for tier in StrengthTier
    if tier.minimum_party_level > MINIMUM_PARTY_LEVEL
)

# Formatted with command_prefix, which is configurable. The special levels and
# the hidden commands are deliberately absent. The last line uses Discord's small
# text markdown.
HELP_TEXT = (
    "**CritDeck** \N{GAME DIE}\n"
    "For when a natural 20 deserves more than double dice.\n"
    "\n"
    f"`/newdeck level` Shuffle a fresh crit deck for a party level from {MINIMUM_PARTY_LEVEL} "
    f"to {MAXIMUM_PARTY_LEVEL}. Nastier cards join as you level up: {_TIER_ARRIVALS}. "
    "One deck per server, shared by every channel.\n"
    "`/draw` Flip the next card. Run the deck dry and it reshuffles itself.\n"
    "`/help` This, again.\n"
    "\n"
    "-# Every command also works typed with `{command_prefix}`, for example `{command_prefix}newdeck 7`."
)
