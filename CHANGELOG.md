# Changelog

Each release names every change since the previous one and which author checks
were cleared at which commit.

## Unreleased

The first Python release of CritDeck.

### Commands

- Slash commands `/newdeck level`, `/draw` and `/help` are the main surface.
  Their names, option and contexts are frozen as of 24 October 2026.
- Every command also works typed with a configurable prefix (`?` by default),
  matched case insensitively as a whole word. `?newdeck7`, `?drawing` and
  `?newdeck 1 2` no longer match, as they did in the Go bot.
- Party levels run from 1 to 20. Level 0, negative levels and levels above 20
  are refused unless a special level deck claims them.
- Help is rewritten for slash commands and names the configured prefix.

### Decks

- Deck files live in `decks/`: the base deck, any number of extensions merged
  by strength tier, and special level decks. Every file is read again for each
  new deck, so decks can change without a restart.
- Deck files are validated strictly; a broken extension is left out and the
  table is told, and a broken base deck keeps the current deck.

### Running

- Configuration comes from the environment and `.env`. The token key is
  `DISCORD_TOKEN`; the Go bot's `TOKEN` and `config.json` are no longer read.
- Logs go to stderr and a size rotated file. Message content is no longer
  logged.
- SIGTERM now closes the bot cleanly, as well as Ctrl+C.
