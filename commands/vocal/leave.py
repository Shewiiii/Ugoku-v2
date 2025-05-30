import asyncio
import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check


class Leave(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_leave(
        self, ctx: discord.ApplicationContext, send: bool = False
    ) -> None:
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, check_queue=False):
            return

        if session:
            session: ServerSession
            respond = ctx.send if send else ctx.respond
            asyncio.create_task(respond("Baibai~"))
            await session.clean_session()

    @commands.slash_command(name="leave", description="Nooooo （＞人＜；）")
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_leave(ctx)


def setup(bot):
    bot.add_cog(Leave(bot))
