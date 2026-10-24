# Testing

Every command runs from the repository root. Continuous integration runs the same
commands on Python 3.12, 3.13 and 3.14 (`.github/workflows/ci.yml`).

## Setting up

```bash
python -m venv .venv
```

Then, with the virtual environment's Python (`.venv/Scripts/python` on Windows,
`.venv/bin/python` elsewhere):

```bash
python -m pip install -e ".[dev]"
```

## Suites and checks

| Check | Command | Where it runs |
|---|---|---|
| Formatting | `python -m ruff format --check .` | Locally and CI |
| Lint, every rule, warnings as errors | `python -m ruff check .` | Locally and CI |
| Strict type checking | `python -m mypy` | Locally and CI |
| Prose and typography scan | `python -m repository_checks.prose_and_typography` | Locally and CI |
| Full test suite | `python -m pytest` | Locally and CI |
| Dependency audit of the deployment lock | `python -m pip_audit --requirement deploy/requirements-debian13-x86_64-py313.txt --disable-pip --require-hashes --progress-spinner off` | Locally and CI; needs network access |

The import boundary (no `discord` or adapter import in `core` or `commands`) is
enforced by the lint step through ruff's banned imports rule.

`tests/repository_checks` holds the planted violation tests: each feeds a check
a deliberate violation (an em dash, a hyphen run, a `discord` import in `core`
or `commands`, a type error, unformatted code) and fails if the check stops
catching it. They are part of the full suite, so every run proves every check.

## Deck data

Every deck test uses synthetic cards built in `tests/conftest.py`. The real card
text is third party data and is never a fixture.

`tests/core/test_catalogue_real_decks.py` checks the card counts of the real base
deck: 15, 15, 16 and 4 cards per strength tier, so 15, 30, 46 and 50 cards from
levels 0, 5, 9 and 13. It runs only where `decks/player-deck.json` has been
supplied and skips everywhere else, including CI, with the reason in the
`pytest -ra` summary. To run it, copy the base deck to `decks/player-deck.json`.

## Deployment files

`tests/deployment/test_deployment_files.py` checks that the deployment lock pins
every line with a hash and holds each runtime dependency at the version
`pyproject.toml` pins, and that the systemd unit runs the bot from
`/opt/CritDeckPy` as the `critdeckpy` user, restarts with a pause, stops with
SIGTERM and can write only its log directory. Whether the unit actually starts
is an author gate on the container.

`tests/deployment/test_deploy_script.py` checks that `deploy/deploy.sh` parses,
lists its phases in order, refuses an unknown phase before doing anything, and
names the same directory, service, user, unit and lock as the files it installs.
No test runs a real phase: they install packages and start services.

## Author gates

| Area | Gate |
|---|---|
| Checks and CI | The automated criteria reproduced on a clean machine |
| Prefix commands | Each backup prefix command confirmed in a test server |
| Slash commands | Commands registered in a test server; each command, the bounds, guild only behaviour and visibility confirmed; slash command contract frozen |
| Deployment | Installed in the homelab container by `deploy/INSTALL.md`, the service started, commands synced, a session played |

## Testing deviations

- UK spelling and quotation marks used for emphasis are checked by review, not
  by the scan. A word list would flag Discord's own API names, and
  telling emphasis from quotation needs judgement.
- There is no memory or undefined behaviour sanitiser to run: Python is memory
  safe.
- The formatter planted violation test passes on ruff's default settings as well
  as on this project's, so it proves the formatter check runs, not that a
  project specific format setting is in force.
