# CritDeck (Python)

A Python port of CritDeck, the Discord bot that builds a shuffled critical hit deck
for a party level and draws cards from it, one deck per server.

The port is at CE1: an empty, installable package with its checks. There is no
bot to run yet. To build it and run the checks, see [`TESTING.md`](TESTING.md);
it needs Python 3.12 or later. The Plan
record, implementation log and deviation record are kept on the author's machine
under `docs/untracked/`, which is not tracked, so a fresh clone does not contain
them.

## Where it came from

Ported from `https://github.com/TheScottBot/CritDeck` at commit
`65e721a73141dc02b5f134b342aa9874175110f5`.

The card text is a transcription of Nord Games' Critical Hit Deck (Players 5e) and
is third party intellectual property. It is not tracked: deck files live in the
gitignored `decks/` directory, supplied separately.
