import asyncio
import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check


class Clear(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="clear", description="Clear the queue and stop the current song."
    )
    async def clear(self, ctx: discord.ApplicationContext) -> None:
        asyncio.create_task(ctx.defer())
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, check_queue=False):
            return

        session: ServerSession
        # Important to await here
        await session.stop_playback()
        await session.close_streams()
        session.loop_current = False
        session.loop_queue = False
        session.shuffle = False
        asyncio.create_task(ctx.respond("Queue cleared!"))

        if session.now_playing_message:
            await session.now_playing_message.delete()
            session.now_playing_message = None


def setup(bot):
    bot.add_cog(Clear(bot))
