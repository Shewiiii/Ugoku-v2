import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check


class Seek(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='seek',
        description='Forward to any position in the song (in seconds).'
    )
    async def seek(
        self,
        ctx: discord.ApplicationContext,
        position: int
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession | None = sm.server_sessions.get(guild_id)
        if not await vocal_action_check(session, ctx, ctx.respond):
            return

        await ctx.respond(f"Seeking to {position} seconds.")
        await session.seek(position, quiet=True)


def setup(bot):
    bot.add_cog(Seek(bot))
