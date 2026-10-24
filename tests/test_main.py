"""Startup: configuration, logging, base deck check, then the bot."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest

import critdeck.__main__ as critdeck_main
from critdeck.configuration import CONFIGURATION_SETTINGS
from tests.conftest import SYNTHETIC_TOKEN, build_tiered_deck_bytes, write_deck_directory

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def clean_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Startup reads the real environment and the working directory, so each test
    # starts from neither.
    for setting in CONFIGURATION_SETTINGS:
        monkeypatch.delenv(setting.key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "critdeck.log"))
    return tmp_path


@pytest.fixture
def recorded_bot_runs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, str]]:
    bot_runs: list[tuple[Any, str]] = []

    async def record_instead_of_connecting(critdeck_bot: Any, token: str) -> None:  # noqa: ANN401  # the bot is whatever main built
        bot_runs.append((critdeck_bot, token))

    monkeypatch.setattr(critdeck_main, "run_until_stopped", record_instead_of_connecting)
    return bot_runs


@pytest.mark.usefixtures("restore_root_logging", "clean_working_directory")
def test_main_without_a_token_fails_with_a_clear_message(
    capsys: pytest.CaptureFixture[str], recorded_bot_runs: list[tuple[Any, str]]
) -> None:
    exit_status = critdeck_main.main()

    assert exit_status == 1
    assert capsys.readouterr().err == (
        "startup error: DISCORD_TOKEN is missing: set it in the environment or in .env "
        "in the working directory\n"
    )
    assert recorded_bot_runs == []


@pytest.mark.usefixtures("restore_root_logging")
def test_main_with_no_base_deck_fails_before_connecting(
    clean_working_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    recorded_bot_runs: list[tuple[Any, str]],
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", SYNTHETIC_TOKEN)
    monkeypatch.setenv("DECK_DIRECTORY", str(clean_working_directory / "decks"))

    exit_status = critdeck_main.main()

    assert exit_status == 1
    assert "base deck rejected reason=file_missing" in caplog.text
    assert recorded_bot_runs == []


@pytest.mark.usefixtures("restore_root_logging")
def test_main_logs_what_it_starts_with_and_hands_the_token_to_the_bot_only(
    clean_working_directory: Path,
    caplog: pytest.LogCaptureFixture,
    recorded_bot_runs: list[tuple[Any, str]],
) -> None:
    write_deck_directory(clean_working_directory / "decks", build_tiered_deck_bytes(["Setback", "Deadly"]))
    (clean_working_directory / ".env").write_text(f"DISCORD_TOKEN={SYNTHETIC_TOKEN}\n", encoding="utf-8")
    caplog.set_level(logging.INFO)

    exit_status = critdeck_main.main()

    assert exit_status == 0
    assert [token for _, token in recorded_bot_runs] == [SYNTHETIC_TOKEN]
    for expected_line in (
        "configuration env_file_found=True command_prefix=? deck_directory=decks",
        "file logging active=True",
        "deck catalogue loaded files=1 tiered_cards=2 special_levels=0",
        "surfaces enabled slash=True prefix=True",
        "intents requested message_content=True members=False presences=False",
        "bot stopped",
    ):
        assert expected_line in caplog.text
    assert SYNTHETIC_TOKEN not in caplog.text
    log_file_text = (clean_working_directory / "logs" / "critdeck.log").read_text(encoding="utf-8")
    assert SYNTHETIC_TOKEN not in log_file_text
