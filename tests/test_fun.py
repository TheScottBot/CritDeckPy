"""The hidden typed commands, kept from the Go bot (critdeck.cogs.fun)."""

from __future__ import annotations

import pytest

from critdeck.cogs.fun import HIDDEN_REPLIES, Fun
from tests.fakes import Ctx, Guild, run


def reply_to(message_content: str, prefix: str = "?") -> list[str]:
    ctx = Ctx(Guild(), slash=False, content=message_content, prefix=prefix)
    run(Fun.hidden.callback(Fun(), ctx))
    return [sent.content for sent in ctx.sent]


@pytest.mark.parametrize(("hidden_command_name", "expected_reply"), list(HIDDEN_REPLIES.items()))
def test_hidden_command_answers_only_the_exact_message(hidden_command_name, expected_reply):
    # The Go bot matched these exactly, case included, and nothing else.
    assert reply_to(f"?{hidden_command_name}") == [expected_reply]
    assert reply_to(f"?{hidden_command_name.swapcase()}") == []
    assert reply_to(f"?{hidden_command_name} please") == []


def test_hidden_command_follows_the_prefix_used():
    hidden_command_name = next(iter(HIDDEN_REPLIES))

    assert reply_to(f"cd!{hidden_command_name}", prefix="cd!") == [HIDDEN_REPLIES[hidden_command_name]]


def test_hidden_replies_match_the_go_bot():
    assert HIDDEN_REPLIES == {
        "mrbigdice": "Just pick a number and that's your roll",
        "drbigdice": "Your dice roll factorial!",
        "DMDICE": "25",
        "spray": "https://klipy.com/gifs/spray-bottle-3",
    }


def test_hidden_command_is_hidden_under_every_name():
    assert Fun.hidden.hidden
    assert {Fun.hidden.name, *Fun.hidden.aliases} == set(HIDDEN_REPLIES)
