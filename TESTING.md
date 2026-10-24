# Testing

From the repository root, with Python 3.12 or later:

```bash
python -m venv .venv
```

Then, with the virtual environment's Python (`.venv/Scripts/python` on Windows,
`.venv/bin/python` elsewhere):

```bash
python -m pip install -e ".[dev]"
```

```bash
python -m pytest
```

CI runs the same on Python 3.12, 3.13 and 3.14 (`.github/workflows/ci.yml`).

## How the tests work

As in ktdi, commands run without Discord: `tests/fakes.py` has stand-ins (`Ctx`,
`Guild`, a fake command tree and event loop) and synthetic deck builders, and
tests call a command's callback directly, for example
`run(Decks.new_deck.callback(decks_cog, ctx, 7))`. `Ctx(slash=False)` is a typed
prefix command. There is one test file per module.

Every deck test uses synthetic cards. The real card text is third party data and
is never a fixture.

`tests/test_deck_files.py` also checks the card counts of the real base deck: 15,
15, 16 and 4 cards per strength tier. Those tests run only where
`decks/player-deck.json` has been supplied, and skip everywhere else, including
CI.

`tests/test_deploy.py` checks the deployment lock, the systemd unit and
`deploy/deploy.sh` without running any phase: the phases install packages and
start services, which belongs on the container.

## Author gates

| Area | Gate |
|---|---|
| Commands | Each command, slash and typed, confirmed in a test server |
| Deployment | Installed in the homelab container with `deploy/deploy.sh`, the service started, commands synced, a session played |
