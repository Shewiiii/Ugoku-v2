import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Pause(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_pause(
        self, ctx: discord.ApplicationContext, silent: bool = False
    ) -> None:
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, silent=silent):
            return

        # Pause
        session: ServerSession
        session.voice_client.pause()
        session.last_played_time = datetime.now()
        track = session.queue[0]
        track.timer.stop()

        send_response(
            ctx.respond,
            f"Paused at {track.timer.get()}s!",
            guild_id,
            silent,
        )
        asyncio.create_task(session.now_playing_view.update_buttons())

    @commands.slash_command(name="pause", description="Pause the current song.")
    async def execute(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_pause(ctx)


def setup(bot):
    bot.add_cog(Pause(bot))
