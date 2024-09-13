from discord.ext import commands
import discord

from bot.session_manager import *


class Queue(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='queue',
        description='Show the current queue.'
    )
    async def queue(self, ctx: discord.ApplicationContext):
        guild_id = ctx.guild.id
        session = server_sessions.get(guild_id)

        if session is None:
            await ctx.respond('No active sessions!')
            return

        await session.display_queue(ctx)


def setup(bot):
    bot.add_cog(Queue(bot))
