from datetime import datetime
from typing import Optional, Callable

import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Pause(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_pause(
        self,
        ctx: discord.ApplicationContext,
        silent: bool = False
    ) -> bool:
        guild_id = ctx.guild.id
        session: Optional[ServerSession] = sm.server_sessions.get(guild_id)
        if not await vocal_action_check(session, ctx, ctx.respond, silent=silent):
            return False

        # Pause
        session.voice_client.pause()
        current_time = datetime.now()
        elapsed_time = (current_time - session.last_played_time).seconds
        session.time_elapsed += elapsed_time
        session.last_played_time = current_time

        await send_response(
            ctx.respond,
            f"Paused at {session.time_elapsed}s!",
            guild_id,
            silent
        )

        return True

    @commands.slash_command(
        name='pause',
        description='Pause the current song.'
    )
    async def execute(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_pause(ctx)


def setup(bot):
    bot.add_cog(Pause(bot))
