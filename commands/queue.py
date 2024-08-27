from discord.ext import commands
import discord

from bot.vocal import *


class Queue(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='queue',
        description='Show the current queue.'
    )
    async def queue(self, ctx: discord.ApplicationContext):
        guild_id = ctx.guild.id

        if not guild_id in server_sessions:
            await ctx.respond(f'No active sessions!')
            return

        session: ServerSession = server_sessions[guild_id]
        await ctx.respond(f'{session.display_queue()}')


def setup(bot):
    bot.add_cog(Queue(bot))
