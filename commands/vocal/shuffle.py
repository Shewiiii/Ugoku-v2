from typing import Optional
import random

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from discord.ext import commands
import discord


class Shuffle(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_shuffle(
        self,
        ctx: discord.ApplicationContext,
    ) -> None:

        # Connect to the voice channel
        guild_id = ctx.guild.id
        session: ServerSession | None = sm.server_sessions.get(guild_id)

        if not session:
            await ctx.respond('You are not in a voice channel!')
            return

        session.shuffle_queue()

        if session.shuffle:
            await ctx.respond('Queue shuffled!')
        else:
            await ctx.respond('Original queue order restored.')

    @commands.slash_command(
        name='shuffle',
        description='Shuffle the queue.'
    )
    async def shuffle(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        await self.execute_shuffle(ctx)


def setup(bot):
    bot.add_cog(Shuffle(bot))
