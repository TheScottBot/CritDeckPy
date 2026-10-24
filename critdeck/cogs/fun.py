"""Typed only, kept from the Go bot, and kept out of help and every document on purpose."""

from __future__ import annotations

from discord.ext import commands

# Keyed by the exact command that answers each.
HIDDEN_REPLIES = {
    "mrbigdice": "Just pick a number and that's your roll",
    "drbigdice": "Your dice roll factorial!",
    "DMDICE": "25",
    "spray": "https://klipy.com/gifs/spray-bottle-3",
}
HIDDEN_NAMES = list(HIDDEN_REPLIES)


class Fun(commands.Cog):
    @commands.command(name=HIDDEN_NAMES[0], aliases=HIDDEN_NAMES[1:], hidden=True)
    async def hidden(self, ctx: commands.Context) -> None:
        # Only the exact message answers, case included, as in the Go bot. A near
        # miss gets silence, so it gives nothing away.
        for hidden_name, hidden_reply in HIDDEN_REPLIES.items():
            if ctx.message.content == f"{ctx.prefix}{hidden_name}":
                await ctx.send(hidden_reply)
                return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun())
