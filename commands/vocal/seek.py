import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession


class Seek(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='seek',
        description='Seek to a certain position in the current song (in seconds).'
    )
    async def seek(
        self,
        ctx: discord.ApplicationContext,
        position: int
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession | None = sm.server_sessions.get(guild_id)

        if not session:
            await ctx.respond("No active session!")
            return

        if not session.queue:
            await ctx.respond("No song in queue!")
            return

        await ctx.respond(f"Seeking to {position} seconds.")
        await session.seek(position, quiet=True)


def setup(bot):
    bot.add_cog(Seek(bot))
