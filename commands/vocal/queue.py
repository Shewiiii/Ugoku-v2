from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.utils import vocal_action_check


class Queue(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(name="queue", description="Show the current queue.")
    async def queue(self, ctx: discord.ApplicationContext):
        guild_id: int = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond):
            return

        if not session:
            await ctx.respond("No active session !")
            return

        await session.display_queue(ctx)


def setup(bot):
    bot.add_cog(Queue(bot))
