"""/help: how CritDeck works, in the bot's own voice."""

from __future__ import annotations

from discord.ext import commands

from critdeck import config
from critdeck.lib.deck_files import MAXIMUM_PARTY_LEVEL, MINIMUM_PARTY_LEVEL, StrengthTier

HELP_DESCRIPTION = "How CritDeck works."

# Read from the tier table, so help can never disagree with the levels the deck
# uses. The first tier is always in the deck, so it is not announced.
TIER_ARRIVALS = ", ".join(
    f"{tier.strength_name} from {tier.minimum_party_level}"
    for tier in StrengthTier
    if tier.minimum_party_level > MINIMUM_PARTY_LEVEL
)


def help_text(command_prefix: str) -> str:
    # The special levels and the hidden commands are deliberately absent. The
    # last line uses Discord's small text markdown.
    return (
        "**CritDeck** \N{GAME DIE}\n"
        "For when a natural 20 deserves more than double dice.\n"
        "\n"
        f"`/newdeck level` Shuffle a fresh crit deck for a party level from {MINIMUM_PARTY_LEVEL} "
        f"to {MAXIMUM_PARTY_LEVEL}. Nastier cards join as you level up: {TIER_ARRIVALS}. "
        "One deck per server, shared by every channel.\n"
        "`/draw` Flip the next card. Run the deck dry and it reshuffles itself.\n"
        "`/help` This, again.\n"
        "\n"
        f"-# Every command also works typed with `{command_prefix}`, for example `{command_prefix}newdeck 7`."
    )


class Help(commands.Cog):
    @commands.hybrid_command(name="help", description=HELP_DESCRIPTION)
    async def help(self, ctx: commands.Context) -> None:
        await ctx.send(help_text(config.COMMAND_PREFIX), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help())
