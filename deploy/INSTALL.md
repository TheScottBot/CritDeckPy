# Installing CritDeck in the homelab container

For the Debian 13 (trixie), x86_64 container with Python 3.13 that the deployment
lock was made for. The bot runs from a checkout at `/opt/CritDeckPy` as the
`critdeckpy` user, under the `critdeckpy` systemd service. Those names are its
own because the Go bot still runs on the same host from `/opt/critdeck`; nothing
here touches it.

`deploy.sh` does the work in phases. Run it as root in the container.

## First install

Fetch the script and run every phase:

```bash
curl --fail --location --remote-name https://raw.githubusercontent.com/TheScottBot/CritDeckPy/main/deploy/deploy.sh
```

```bash
bash deploy.sh
```

It stops twice on purpose, each time saying what to do and which phases to run
next:

1. At `settings`, having created `/opt/CritDeckPy/.env`: set `DISCORD_TOKEN`
   there (and `GUILD_IDS` for the test server while testing), then carry on with
   the phases it names. The token is never printed.
2. At `decks`: copy the base deck in. From the machine that holds the deck
   files:

```bash
scp decks/player-deck.json root@critdeck:/opt/CritDeckPy/decks/
```

   Extension and special level folders go in the same way.

`bash deploy.sh help` lists the phases. Each can be run again safely.

## Updating

```bash
bash /opt/CritDeckPy/deploy/deploy.sh code dependencies service start
```

A restart wipes every server's deck, as it always has. Deck files can change at
any time without a restart; the next new deck picks them up.

## Registering the slash commands

Discord keeps registered commands between restarts, so this is done once, not on
every start.

- While testing, `GUILD_IDS` in `.env` registers them to the test server at
  once, on every start.
- At release, remove `GUILD_IDS`, set `SYNC_GLOBAL_COMMANDS=true`, run
  `bash /opt/CritDeckPy/deploy/deploy.sh start`, check the journal for
  `slash commands synced target=global`, then set it back to `false`.

## If it will not start

Follow the log with `journalctl -u critdeckpy -f`.

- `startup error:` names the setting at fault, never its value.
- `base deck rejected reason=file_missing`: `decks/player-deck.json` is missing.
- `login failed`: the token is wrong, or the Message Content Intent is switched
  off in the Discord Developer Portal.
- `status=226/NAMESPACE`: the container cannot give the service its own
  filesystem view. The sandboxing lines in the unit need the container's nesting
  feature switched on (on Proxmox: the container's Options, Features, Nesting),
  then a container restart.
