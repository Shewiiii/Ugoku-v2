import asyncio
import discord
from discord.ext import commands
import gc

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check


class Leave(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(name="leave", description="Nooooo （＞人＜；）")
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, check_queue=False):
            return

        if session:
            session: ServerSession
            asyncio.create_task(ctx.respond("Baibai~"))
            await session.clean_session()
            await asyncio.to_thread(gc.collect)


def setup(bot):
    bot.add_cog(Leave(bot))
