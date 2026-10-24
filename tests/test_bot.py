"""The bot: intents, cogs, command sync, error replies, logging, shutdown and startup (critdeck.bot)."""

from __future__ import annotations

import logging
import signal
import types

import discord
import pytest
from discord.ext import commands

from critdeck import bot as critdeck_bot_module
from critdeck.bot import CritDeckBot, install_shutdown_signal_handlers, sync_application_commands
from critdeck.cogs import decks
from tests.fakes import (
    SYNTHETIC_TOKEN,
    Ctx,
    FakeCommandTree,
    FakeEventLoop,
    Guild,
    build_tiered_deck_bytes,
    fake_http_response,
    run,
    write_deck_directory,
)


def test_bot_asks_for_message_content_and_no_other_privileged_intent():
    critdeck_bot = CritDeckBot()

    assert critdeck_bot.intents.message_content
    assert not critdeck_bot.intents.members
    assert not critdeck_bot.intents.presences


def test_bot_matches_the_configured_prefix_in_any_case_with_its_own_help():
    critdeck_bot = CritDeckBot()

    assert critdeck_bot.command_prefix == "?"
    assert critdeck_bot.case_insensitive
    assert critdeck_bot.help_command is None


def test_bot_loads_every_cog():
    critdeck_bot = CritDeckBot()

    run(critdeck_bot.setup_hook())

    assert {command.name for command in critdeck_bot.commands if not command.hidden} == {"newdeck", "draw", "help"}
    assert {command.name for command in critdeck_bot.tree.get_commands()} == {"newdeck", "draw", "help"}
    assert critdeck_bot.get_command("NEWDECK") is critdeck_bot.get_command("newdeck")


# --- Command sync ---


def test_sync_with_nothing_asked_for_touches_nothing_and_says_so(caplog):
    command_tree = FakeCommandTree()
    caplog.set_level(logging.INFO)

    run(sync_application_commands(command_tree, (), sync_globally=False))

    assert command_tree.synced_targets == []
    assert "slash command sync not requested" in caplog.text


def test_sync_to_each_test_server_and_skip_one_that_refuses(caplog):
    missing_access = discord.Forbidden(
        fake_http_response(403, "Forbidden"), {"code": 50001, "message": "Missing Access"}
    )
    command_tree = FakeCommandTree({7007: missing_access})
    caplog.set_level(logging.INFO)

    run(sync_application_commands(command_tree, (7007, 8008), sync_globally=False))

    assert command_tree.copied_to_guild_ids == [7007, 8008]
    assert command_tree.synced_targets == [8008]
    assert "slash command sync refused guild_id=7007 status=403 discord_code=50001" in caplog.text
    assert "slash commands synced guild_id=8008 command_count=3" in caplog.text


def test_sync_globally_only_when_asked(caplog):
    command_tree = FakeCommandTree()
    caplog.set_level(logging.INFO)

    run(sync_application_commands(command_tree, (), sync_globally=True))

    assert command_tree.synced_targets == [None]
    assert "slash commands synced globally command_count=3" in caplog.text


# --- Errors and logging ---


def command_error(error: Exception) -> Ctx:
    ctx = Ctx(Guild())
    run(CritDeckBot().on_command_error(ctx, error))
    return ctx


def test_a_deck_command_in_a_direct_message_gets_the_server_only_notice():
    ctx = command_error(commands.NoPrivateMessage())

    assert ctx.last.content == decks.DIRECT_MESSAGE_TEXT
    assert ctx.last.private


@pytest.mark.parametrize(
    "input_error",
    [
        commands.BadArgument("not a number"),
        commands.TooManyArguments(),
        commands.MissingRequiredArgument(types.SimpleNamespace(name="level", displayed_name="level")),
    ],
)
def test_a_mistyped_level_gets_the_range_message(input_error):
    # ?newdeck nine, ?newdeck 7 8 and ?newdeck alone: newdeck is the only command that takes input.
    ctx = command_error(input_error)

    assert ctx.last.content == decks.PARTY_LEVEL_OUT_OF_RANGE_TEXT
    assert ctx.last.private


def test_an_unknown_prefix_command_is_ordinary_chat_and_ignored(caplog):
    caplog.set_level(logging.DEBUG)

    ctx = command_error(commands.CommandNotFound('Command "roll" is not found'))

    assert ctx.sent == []
    assert [record for record in caplog.records if record.name.startswith("critdeck")] == []


def test_a_failed_reply_is_logged_by_status_and_code(caplog):
    deadline_missed = discord.NotFound(
        fake_http_response(404, "Not Found"), {"code": 10062, "message": "Unknown interaction"}
    )
    caplog.set_level(logging.INFO)

    command_error(commands.CommandInvokeError(deadline_missed))

    assert "reply failed status=404 discord_code=10062" in caplog.text


def test_any_other_command_error_is_logged_by_type_never_by_message(caplog):
    caplog.set_level(logging.INFO)

    command_error(commands.CommandError("private-content"))

    assert "command error error_type=CommandError" in caplog.text
    assert "private-content" not in caplog.text


@pytest.mark.parametrize(("slash", "surface"), [(True, "slash"), (False, "prefix")])
def test_each_command_is_logged_by_name_and_surface_never_content(caplog, slash, surface):
    ctx = Ctx(Guild(), slash=slash, content="?newdeck 7")
    ctx.command = types.SimpleNamespace(qualified_name="newdeck")
    caplog.set_level(logging.INFO)

    run(CritDeckBot().on_command(ctx))

    assert f"command=newdeck surface={surface}" in caplog.text
    assert "?newdeck 7" not in caplog.text


# --- Shutdown ---


def test_shutdown_handlers_cover_interrupt_and_terminate_where_the_loop_allows():
    event_loop = FakeEventLoop(supports_signal_handlers=True)
    requested_signal_names = []

    installed = install_shutdown_signal_handlers(event_loop, requested_signal_names.append)
    event_loop.handlers_by_signal[signal.SIGTERM]()

    assert installed == ("SIGINT", "SIGTERM")
    assert requested_signal_names == ["SIGTERM"]


def test_shutdown_handlers_install_nothing_on_windows():
    # Ctrl+C still stops the bot there, through KeyboardInterrupt.
    assert install_shutdown_signal_handlers(FakeEventLoop(supports_signal_handlers=False), print) == ()


# --- Startup ---


@pytest.fixture
def recorded_bot_runs(monkeypatch):
    bot_runs = []

    async def record_instead_of_connecting(critdeck_bot, token):
        bot_runs.append((critdeck_bot, token))

    monkeypatch.setattr(critdeck_bot_module, "run_until_stopped", record_instead_of_connecting)
    return bot_runs


@pytest.mark.usefixtures("restore_root_logging")
def test_startup_without_a_token_stops_with_the_reason(reload_config, recorded_bot_runs, capsys):
    reload_config()

    assert critdeck_bot_module.main() == 1
    assert capsys.readouterr().err == (
        "startup error: DISCORD_TOKEN is missing: set it in the environment or in .env in the working directory\n"
    )
    assert recorded_bot_runs == []


@pytest.mark.usefixtures("restore_root_logging")
def test_startup_without_a_base_deck_stops_before_contacting_discord(
    reload_config, recorded_bot_runs, tmp_path, caplog
):
    reload_config(DISCORD_TOKEN=SYNTHETIC_TOKEN, LOG_FILE=str(tmp_path / "logs" / "critdeck.log"))

    assert critdeck_bot_module.main() == 1
    assert "base deck rejected reason=file_missing" in caplog.text
    assert recorded_bot_runs == []


@pytest.mark.usefixtures("restore_root_logging")
def test_startup_logs_what_it_found_and_gives_the_token_only_to_the_bot(
    reload_config, recorded_bot_runs, tmp_path, caplog
):
    log_file = tmp_path / "logs" / "critdeck.log"
    reload_config(env_file=f"DISCORD_TOKEN={SYNTHETIC_TOKEN}\nLOG_FILE={log_file.as_posix()}\n")
    write_deck_directory(tmp_path / "decks", build_tiered_deck_bytes(["Setback", "Deadly"]))
    caplog.set_level(logging.INFO)

    assert critdeck_bot_module.main() == 0
    assert [token for _, token in recorded_bot_runs] == [SYNTHETIC_TOKEN]
    for expected_line in (
        "configuration env_file_found=True command_prefix=? deck_directory=decks",
        "file logging active=True",
        "deck catalogue loaded files=1 tiered_cards=2 special_levels=0",
        "intents requested message_content=True members=False presences=False",
        "bot stopped",
    ):
        assert expected_line in caplog.text
    assert SYNTHETIC_TOKEN not in caplog.text
    assert SYNTHETIC_TOKEN not in log_file.read_text(encoding="utf-8")
