"""/help (critdeck.cogs.help)."""

from __future__ import annotations

import pytest

from critdeck.cogs import fun
from critdeck.cogs.help import Help, help_text
from critdeck.lib.deck_files import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL, StrengthTier
from tests.fakes import Ctx, run


def test_help_replies_privately_and_works_outside_a_server():
    ctx = Ctx(None)

    run(Help.help.callback(Help(), ctx))

    assert ctx.last.content == help_text("?")
    assert ctx.last.private


@pytest.mark.parametrize("command_prefix", ["?", "!", "cd!"])
def test_help_names_the_configured_prefix(command_prefix):
    assert f"`{command_prefix}newdeck 7`" in help_text(command_prefix)


def test_help_names_the_commands_and_the_level_range():
    text = help_text("?")

    for command_usage in ("`/newdeck level`", "`/draw`", "`/help`"):
        assert command_usage in text
    assert f"from {MINIMUM_PARTY_LEVEL} to {MAXIMUM_PARTY_LEVEL}" in text


def test_help_names_each_tier_from_the_level_it_joins():
    text = help_text("?")

    for tier in StrengthTier:
        if tier.minimum_party_level > MINIMUM_PARTY_LEVEL:
            assert f"{tier.strength_name} from {tier.minimum_party_level}" in text


def test_help_never_mentions_the_hidden_commands():
    text = help_text("?").lower()

    for hidden_command_name in fun.HIDDEN_REPLIES:
        assert hidden_command_name.lower() not in text
