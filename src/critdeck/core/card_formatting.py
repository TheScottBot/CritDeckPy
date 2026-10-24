"""The text a drawn card is sent as."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from critdeck.core.catalogue import Card


def format_card(card: Card) -> str:
    # Byte for byte the Go bot's output, trailing blank line included.
    return "".join(f"Damage Type: {effect.damage_type}\n{effect.value}\n\n" for effect in card.effects)
