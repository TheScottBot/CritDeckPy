"""Registering slash commands with Discord, only where and when asked."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import discord

from critdeck.discord_adapter.command_sync import CommandSyncPlan, sync_application_commands
from tests.conftest import FakeCommandTree, FakeHttpResponse

if TYPE_CHECKING:
    import pytest
    from discord import app_commands

FIRST_GUILD_ID = 7007
SECOND_GUILD_ID = 8008


def run_sync(fake_command_tree: FakeCommandTree, command_sync_plan: CommandSyncPlan) -> None:
    asyncio.run(
        sync_application_commands(cast("app_commands.CommandTree[Any]", fake_command_tree), command_sync_plan)
    )


def test_sync_with_nothing_requested_touches_nothing_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    fake_command_tree = FakeCommandTree()
    caplog.set_level(logging.INFO)

    run_sync(fake_command_tree, CommandSyncPlan(guild_ids=(), sync_globally=False))

    assert fake_command_tree.synced_targets == []
    assert "slash command sync not requested" in caplog.text


def test_sync_copies_the_commands_to_each_development_guild_and_syncs_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_command_tree = FakeCommandTree()
    caplog.set_level(logging.INFO)

    run_sync(
        fake_command_tree, CommandSyncPlan(guild_ids=(FIRST_GUILD_ID, SECOND_GUILD_ID), sync_globally=False)
    )

    assert fake_command_tree.copied_to_guild_ids == [FIRST_GUILD_ID, SECOND_GUILD_ID]
    assert fake_command_tree.synced_targets == [FIRST_GUILD_ID, SECOND_GUILD_ID]
    assert f"slash commands synced target=guild guild_id={FIRST_GUILD_ID} command_count=3" in caplog.text


def test_sync_globally_only_when_asked(caplog: pytest.LogCaptureFixture) -> None:
    fake_command_tree = FakeCommandTree()
    caplog.set_level(logging.INFO)

    run_sync(fake_command_tree, CommandSyncPlan(guild_ids=(), sync_globally=True))

    assert fake_command_tree.copied_to_guild_ids == []
    assert fake_command_tree.synced_targets == [None]
    assert "slash commands synced target=global command_count=3" in caplog.text


def test_sync_skips_a_guild_that_refuses_and_carries_on(caplog: pytest.LogCaptureFixture) -> None:
    missing_access = discord.Forbidden(
        FakeHttpResponse(403, "Forbidden"), {"code": 50001, "message": "Missing Access"}
    )
    fake_command_tree = FakeCommandTree({FIRST_GUILD_ID: missing_access})
    caplog.set_level(logging.INFO)

    run_sync(
        fake_command_tree, CommandSyncPlan(guild_ids=(FIRST_GUILD_ID, SECOND_GUILD_ID), sync_globally=False)
    )

    assert fake_command_tree.synced_targets == [SECOND_GUILD_ID]
    assert (
        f"slash command sync refused target=guild guild_id={FIRST_GUILD_ID} status=403 discord_code=50001"
        in caplog.text
    )
