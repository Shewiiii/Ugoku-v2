import logging

from discord.ext import commands
from datetime import datetime
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response


class Skip(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_skip(
        self,
        ctx: discord.ApplicationContext,
        send=False
    ) -> None:
        guild_id = ctx.guild.id
        respond = (ctx.send if send else ctx.respond)

        if guild_id not in sm.server_sessions:
            await send_response(
                respond,
                "No songs in queue!",
                session.guild_id
            )
            return

        session: ServerSession = sm.server_sessions[guild_id]

        if not session.queue:
            await send_response(
                respond,
                "No songs in queue!",
                session.guild_id
            )
            return

        await send_response(respond, "Skipping!", session.guild_id)

        # SKIP
        session.skipped = True
        if session.loop_current:
            session.queue.pop(0)
            session.loop_current = False

        if len(session.queue) == 1:
            session.voice_client.stop()
        else:
            session.last_played_time = datetime.now()
            session.voice_client.pause()
            await session.play_next(ctx)

    @commands.slash_command(
        name='skip',
        description='Skip the current song.'
    )
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_skip(ctx)


def setup(bot):
    bot.add_cog(Skip(bot))
