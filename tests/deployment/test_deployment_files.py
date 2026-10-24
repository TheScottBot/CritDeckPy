"""The homelab deployment files: the hashed lock and the systemd unit."""

from __future__ import annotations

import re
import tomllib

from tests.conftest import REPOSITORY_ROOT

DEPLOYMENT_LOCK_PATH = REPOSITORY_ROOT / "deploy" / "requirements-debian13-x86_64-py313.txt"
SYSTEMD_UNIT_PATH = REPOSITORY_ROOT / "deploy" / "critdeckpy.service"
LOCK_LINE_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9._-]+)==(?P<version>[A-Za-z0-9.]+) --hash=sha256:[0-9a-f]{64}"
)


def read_lock_requirements() -> dict[str, str]:
    lock_requirements: dict[str, str] = {}
    for lock_line in DEPLOYMENT_LOCK_PATH.read_text(encoding="utf-8").splitlines():
        if not lock_line or lock_line.startswith("#"):
            continue
        lock_line_match = LOCK_LINE_PATTERN.fullmatch(lock_line)
        assert lock_line_match is not None, lock_line
        lock_requirements[lock_line_match["name"].lower()] = lock_line_match["version"]
    return lock_requirements


def read_systemd_unit() -> dict[str, dict[str, list[str]]]:
    unit_sections: dict[str, dict[str, list[str]]] = {}
    current_section: dict[str, list[str]] = {}
    for unit_line in SYSTEMD_UNIT_PATH.read_text(encoding="utf-8").splitlines():
        if not unit_line or unit_line.startswith("#"):
            continue
        if unit_line.startswith("["):
            current_section = unit_sections.setdefault(unit_line.strip("[]"), {})
            continue
        directive_name, _, directive_value = unit_line.partition("=")
        current_section.setdefault(directive_name, []).append(directive_value)
    return unit_sections


def test_lock_pins_every_line_exactly_with_a_hash() -> None:
    assert read_lock_requirements()


def test_lock_holds_each_runtime_dependency_at_its_pyproject_version() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock_requirements = read_lock_requirements()

    for runtime_requirement in pyproject["project"]["dependencies"]:
        requirement_name, _, pinned_version = runtime_requirement.partition("==")
        assert lock_requirements[requirement_name.lower()] == pinned_version


def test_unit_runs_the_bot_from_its_checkout_as_its_own_user() -> None:
    service_directives = read_systemd_unit()["Service"]

    # New names throughout, because the Go bot still runs on the same host from
    # /opt/critdeck and its service must not be overwritten.
    assert service_directives["User"] == ["critdeckpy"]
    assert service_directives["WorkingDirectory"] == ["/opt/CritDeckPy"]
    assert service_directives["ExecStart"] == ["/opt/CritDeckPy/.venv/bin/python -m critdeck"]
    assert service_directives["Environment"] == ["PYTHONPATH=/opt/CritDeckPy/src"]


def test_unit_restarts_after_a_failure_but_not_in_a_tight_loop() -> None:
    service_directives = read_systemd_unit()["Service"]

    assert service_directives["Restart"] == ["on-failure"]
    assert service_directives["RestartSec"] == ["30"]


def test_unit_stops_the_bot_with_sigterm_which_it_closes_cleanly_on() -> None:
    assert read_systemd_unit()["Service"].get("KillSignal", ["SIGTERM"]) == ["SIGTERM"]


def test_unit_can_write_only_its_log_directory() -> None:
    service_directives = read_systemd_unit()["Service"]

    assert service_directives["ProtectSystem"] == ["strict"]
    assert service_directives["ReadWritePaths"] == ["/opt/CritDeckPy/logs"]
    assert service_directives["NoNewPrivileges"] == ["yes"]


def test_unit_starts_at_boot_once_the_network_is_up() -> None:
    unit_sections = read_systemd_unit()

    assert unit_sections["Unit"]["After"] == ["network-online.target"]
    assert unit_sections["Unit"]["Wants"] == ["network-online.target"]
    assert unit_sections["Install"]["WantedBy"] == ["multi-user.target"]
