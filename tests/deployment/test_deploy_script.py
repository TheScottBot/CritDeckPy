"""The phased deploy script: it parses, agrees with the unit and lock, and refuses bad phases.

No test runs a real phase: they install packages, create users and start
services, which belongs on the container, as an author gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from tests.conftest import REPOSITORY_ROOT

DEPLOY_SCRIPT_PATH = REPOSITORY_ROOT / "deploy" / "deploy.sh"
BASH_PATH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH_PATH is None, reason="bash is not installed here")

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


def test_deploy_script_parses() -> None:
    assert BASH_PATH is not None
    syntax_check = subprocess.run(  # noqa: S603  # fixed arguments chosen by the tests
        [BASH_PATH, "-n", DEPLOY_SCRIPT_PATH.as_posix()], capture_output=True, text=True, check=False
    )

    assert syntax_check.returncode == 0, syntax_check.stderr


def test_deploy_script_help_lists_the_phases_in_order() -> None:
    help_run = run_deploy_script("help")

    assert help_run.returncode == 0
    listed_phases = re.findall(r"^  (\w+)\s", help_run.stdout, re.MULTILINE)
    assert listed_phases == EXPECTED_PHASES


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
