import discord
from discord.ext import commands
from bot.session_manager import session_manager as sm

from bot.server_session import *


class Previous(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='previous',
        description='Play the previous track.'
    )
    async def previous(self, ctx: discord.ApplicationContext):
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)

        if session is None:
            await ctx.respond('No active sessions!')
            return

        if not session.stack_previous:
            await ctx.respond("No tracks played previously!")
            return

        await ctx.respond('Playing the previous track!')
        await session.play_previous(ctx)


def setup(bot):
    bot.add_cog(Previous(bot))
