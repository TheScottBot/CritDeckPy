"""The homelab deployment: the hashed lock, the systemd unit and the phased deploy script.

No test runs a real deploy phase: they install packages, create users and start
services, which belongs on the container.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib

import pytest

from tests.conftest import REPOSITORY_ROOT

DEPLOYMENT_LOCK_PATH = REPOSITORY_ROOT / "deploy" / "requirements-debian13-x86_64-py313.txt"
DEPLOY_SCRIPT_PATH = REPOSITORY_ROOT / "deploy" / "deploy.sh"
BASH_PATH = shutil.which("bash")
needs_bash = pytest.mark.skipif(BASH_PATH is None, reason="bash is not installed here")
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
    assert service_directives["Environment"] == ["PYTHONPATH=/opt/CritDeckPy"]


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

EXPECTED_PHASES = ["packages", "user", "code", "dependencies", "settings", "decks", "service", "start"]


def run_deploy_script(*script_arguments: str) -> subprocess.CompletedProcess[str]:
    assert BASH_PATH is not None
    return subprocess.run(  # noqa: S603  # fixed arguments chosen by the tests
        [BASH_PATH, DEPLOY_SCRIPT_PATH.as_posix(), *script_arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def read_script_constant(constant_name: str) -> str:
    constant_match = re.search(
        rf"^readonly {constant_name}=(?P<value>\S+)$",
        DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert constant_match is not None, constant_name
    return constant_match["value"]


@needs_bash
def test_deploy_script_parses() -> None:
    assert BASH_PATH is not None
    syntax_check = subprocess.run(  # noqa: S603  # fixed arguments chosen by the tests
        [BASH_PATH, "-n", DEPLOY_SCRIPT_PATH.as_posix()], capture_output=True, text=True, check=False
    )

    assert syntax_check.returncode == 0, syntax_check.stderr


@needs_bash
def test_deploy_script_help_lists_the_phases_in_order() -> None:
    help_run = run_deploy_script("help")

    assert help_run.returncode == 0
    listed_phases = re.findall(r"^  (\w+)\s", help_run.stdout, re.MULTILINE)
    assert listed_phases == EXPECTED_PHASES


@needs_bash
def test_deploy_script_refuses_an_unknown_phase_before_doing_anything() -> None:
    unknown_phase_run = run_deploy_script("packages", "everything")

    assert unknown_phase_run.returncode == 2
    assert "unknown phase: everything" in unknown_phase_run.stderr


def test_deploy_script_uses_new_names_that_cannot_touch_the_go_bot() -> None:
    assert read_script_constant("INSTALL_DIRECTORY") == "/opt/CritDeckPy"
    assert read_script_constant("SERVICE_NAME") == "critdeckpy"
    assert read_script_constant("SERVICE_USER") == "critdeckpy"


def test_deploy_script_installs_the_unit_and_lock_that_exist_in_the_repository() -> None:
    assert (REPOSITORY_ROOT / read_script_constant("UNIT_FILE")).is_file()
    assert (REPOSITORY_ROOT / read_script_constant("LOCK_FILE")).is_file()
    assert read_script_constant("UNIT_FILE") == f"deploy/{read_script_constant('SERVICE_NAME')}.service"


def test_deploy_script_clones_this_repository() -> None:
    assert read_script_constant("REPOSITORY_URL") == "https://github.com/TheScottBot/CritDeckPy.git"
