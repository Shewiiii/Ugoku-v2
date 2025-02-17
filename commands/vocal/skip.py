from discord.ext import commands
from datetime import datetime
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Skip(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_skip(
        self,
        ctx: discord.ApplicationContext,
        send=False
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        respond = (ctx.send if send else ctx.respond)
        if not await vocal_action_check(session, ctx, respond):
            return

        await send_response(respond, "Skipping!", session.guild_id)

        # SKIP
        session.skipped = True
        if session.loop_current:
            session.queue.pop(0)
            session.loop_current = False

        if not len(session.queue) == 1:
            session.last_played_time = datetime.now()
        session.voice_client.stop()

    @commands.slash_command(
        name='skip',
        description='Skip the current song.'
    )
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_skip(ctx)


def setup(bot):
    bot.add_cog(Skip(bot))
