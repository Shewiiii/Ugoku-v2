from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.utils import vocal_action_check


class NowPlaying(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='now-playing',
        description='Send the Now playing embed.'
    )
    async def queue(self, ctx: discord.ApplicationContext):
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not await vocal_action_check(session, ctx, ctx.respond):
            return

        await ctx.respond("Sending !", ephemeral=True)
        await session.now_playing_message.delete()
        session.now_playing_message = None
        await session.update_now_playing(ctx)


def setup(bot):
    bot.add_cog(NowPlaying(bot))
