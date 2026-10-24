# CritDeck (Python)

A Discord bot that builds a shuffled critical hit deck for a party level and
draws cards from it, one deck per server.

Slash commands are the main way to use it; every command also works typed with a
configurable prefix.

| Command | What it does |
|---|---|
| `/newdeck level` | Shuffles a fresh deck for a party level from 1 to 20, shared by every channel in the server |
| `/draw` | Draws the next card; an empty deck reshuffles itself |
| `/help` | Shows how it works |

Decks live in memory only. Restarting the bot wipes every deck, which is the
quickest way to reset things if the bot misbehaves.

## Setting up the Discord application

In the [Discord Developer Portal](https://discord.com/developers/applications):

1. Create an application and a bot, and copy the bot token.
2. Under Bot, Privileged Gateway Intents, switch on **Message Content Intent**.
   The typed prefix commands need it; without it the bot refuses to log in.
3. Invite the bot with the `bot` and `applications.commands` scopes. Without
   `applications.commands` the slash commands cannot be registered in that
   server.

## Deck files

Deck files are third party card text, so they are not in this repository. Put
them in `decks/` (gitignored) in the directory the bot runs from:

| Path | What it is |
|---|---|
| `decks/player-deck.json` | The base deck. Required: the bot will not start without it |
| `decks/extensions/*.json` | Extra cards, merged into the base by strength tier |
| `decks/special-levels/*.json` | A deck of its own, dealt whole at a level outside 1 to 20 that the file names |

Every file is read again each time a new deck is made, so files can be added or
removed without a restart. A broken extension is left out and logged, and the
table is told; a broken base deck refuses the new deck and keeps the current
one.

## Running it

Python 3.12 or later. From the repository root:

```bash
python -m venv .venv
```

Then, with the virtual environment's Python (`.venv/Scripts/python` on Windows,
`.venv/bin/python` elsewhere):

```bash
python -m pip install -e .
```

Copy [`.env.example`](.env.example) to `.env`, set `DISCORD_TOKEN`, and start the
bot from the same directory:

```bash
python -m critdeck
```

The installed `critdeck` command does the same. Ctrl+C, or SIGTERM where the
platform supports it, shuts the bot down cleanly.

To run it as a service in the homelab container, follow
[`deploy/INSTALL.md`](deploy/INSTALL.md).

## Configuration

Settings come from the environment, then from `.env` in the working directory;
the environment wins. Every setting is listed, with its default, in
[`.env.example`](.env.example). A missing token, a malformed value or an unknown
key in `.env` stops startup with the setting's name and the reason; values are
never printed.

Slash commands are registered with Discord only when asked: `GUILD_IDS` registers
them to test servers straight away on every start, and `SYNC_GLOBAL_COMMANDS=true`
registers them everywhere. Leave both unset for an ordinary restart; Discord
keeps the commands it already has.

## Logging

Logs go to stderr and to a size rotated file (`logs/critdeck.log` by default).
They record each command's name, outcome and input length, deck file problems,
command syncs and failed replies. Message content, card text and the token are
never logged.

## The cards

The card text is a transcription of Nord Games' Critical Hit Deck (Players 5e)
and is third party intellectual property.

To build it and run the checks, see [`TESTING.md`](TESTING.md).
