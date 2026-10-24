# Installing CritDeck in the homelab container

For the Debian 13 (trixie), x86_64 container with Python 3.13 that the deployment
lock was made for. The bot runs from a checkout at `/opt/critdeck` as a dedicated
`critdeck` user, under systemd.

Every command below runs as root in the container unless it says otherwise.

## 1. Packages and user

```bash
apt install git python3-venv
```

```bash
useradd --system --home-dir /opt/critdeck --shell /usr/sbin/nologin critdeck
```

## 2. Code and dependencies

```bash
git clone https://github.com/TheScottBot/CritDeckPy.git /opt/critdeck
```

```bash
python3 -m venv /opt/critdeck/.venv
```

The lock pins every wheel by hash, so this refuses anything that differs from
what was checked:

```bash
/opt/critdeck/.venv/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r /opt/critdeck/deploy/requirements-debian13-x86_64-py313.txt
```

## 3. Settings

```bash
cp /opt/critdeck/.env.example /opt/critdeck/.env
```

Edit `/opt/critdeck/.env` and set `DISCORD_TOKEN`. Then let the bot read the
file but not change it, and keep it from everyone else, since it holds the
token:

```bash
chown root:critdeck /opt/critdeck/.env
```

```bash
chmod 640 /opt/critdeck/.env
```

## 4. Deck files and logs

```bash
mkdir -p /opt/critdeck/decks /opt/critdeck/logs
```

```bash
chown critdeck:critdeck /opt/critdeck/logs
```

From the machine that holds the deck files, copy the base deck in (and any
`extensions/` or `special-levels/` folders the same way):

```bash
scp decks/player-deck.json root@critdeck:/opt/critdeck/decks/
```

## 5. The service

```bash
cp /opt/critdeck/deploy/critdeck.service /etc/systemd/system/critdeck.service
```

```bash
systemctl daemon-reload
```

```bash
systemctl enable --now critdeck
```

Watch it start:

```bash
journalctl -u critdeck -f
```

The first lines say whether `.env` was found, how many deck files loaded, the
surfaces and intents, and whether slash commands were synced.

## Registering the slash commands

Discord keeps registered commands between restarts, so this is done once, not on
every start.

- While testing, set `GUILD_IDS` in `.env` to the test server's id: the commands
  appear there at once, on every start.
- At release, remove `GUILD_IDS`, set `SYNC_GLOBAL_COMMANDS=true`, restart once,
  check the journal for `slash commands synced target=global`, then set it back to
  `false`. Global commands can take a while to appear in every server.

## Updating

```bash
git -C /opt/critdeck pull
```

```bash
/opt/critdeck/.venv/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r /opt/critdeck/deploy/requirements-debian13-x86_64-py313.txt
```

```bash
systemctl restart critdeck
```

A restart wipes every server's deck, as it always has. Deck files themselves can
be changed at any time without a restart; the next new deck picks them up.

## If it will not start

- `startup error:` in the journal names the setting at fault, never its value.
- `base deck rejected reason=file_missing`: `decks/player-deck.json` is missing.
- `login failed`: the token is wrong, or the Message Content Intent is switched
  off in the Discord Developer Portal.
- `status=226/NAMESPACE`: the container cannot give the service its own
  filesystem view. The sandboxing lines in the unit need the container's nesting
  feature switched on (on Proxmox: the container's Options, Features, Nesting),
  then a container restart.
