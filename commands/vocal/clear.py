from datetime import datetime

import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response


class Clear(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='clear',
        description='Clear the queue and stop the current song.'
    )
    async def clear(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild.id
        session: ServerSession | None = sm.server_sessions.get(guild_id)

        if not session:
            await ctx.respond("No active session !")
            return

        if session:
            voice_client = session.voice_client
            session.queue.clear()
            session.original_queue.clear()
            session.to_loop.clear()
            session.stack_previous.clear()
            session.loop_current = False
            session.loop_queue = False
            session.shuffle = False

            if voice_client.is_playing():
                session.last_played_time = datetime.now()
                voice_client.stop()

            await ctx.respond('Queue cleared!')


def setup(bot):
    bot.add_cog(Clear(bot))
