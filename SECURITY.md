# Security

## What is trusted and what is not

| Input | Trusted? | How it is handled |
|---|---|---|
| Slash command options | No | Discord types `level` as an integer; the bot still checks the range and refuses anything else |
| Typed prefix messages | No | Parsed by a strict grammar with a length bound; refused rather than truncated; never logged |
| Deck files in `decks/` | Partly: written by the operator, but third party text | Size and file count bounded, every field checked, unknown fields refused; card text is only ever sent as text |
| `.env` and the environment | Yes, written by the operator | Size bounded, unknown keys refused, values never printed |
| The bot token | Secret | Read from `DISCORD_TOKEN` only; never logged, printed or shown in a repr; `.env` is gitignored and readable only by the service |

The bot stores no personal data. A server's id is used in memory as the key to
its deck and is gone on restart.

## Logging

Logs record command names, outcomes, input lengths, deck file problems, command
syncs and failed replies by status code. They never record message content, card
text or the token, and tests check that.

## Accepted risks

Drafted from the author's decisions on 24 October 2026; to be confirmed by the
author before release.

- Decks live in memory only and are lost on restart. This is deliberate: a
  restart is the guaranteed full reset when something misbehaves.
- The typed backup commands need Discord's privileged Message Content Intent, so
  the bot can read every message in channels it can see. It acts only on
  messages that start with the prefix and logs none of them.
- One hidden reply links to an external GIF host, kept from the Go bot.
- discord.py 2.7.1 uses a function Python 3.14 deprecates; the tests ignore
  discord.py's deprecation warnings, as ktdi's do, until it releases a fix.

## Limitations

- Deck file paths and names appear in the log when a file is left out, so the
  log can reveal which extension and special level files exist.
- The deployment lock is for one platform: Debian 13, x86_64, Python 3.13.
  Another host needs its own lock.
- Discord rate limits global command syncs; the bot syncs only when asked.

## Dependency scanning

- Dependabot proposes weekly updates for the Python dependencies, the deployment
  lock and the pinned CI actions, and raises security alerts as advisories are
  published.

No finding is currently accepted without a fix.
