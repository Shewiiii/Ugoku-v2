from discord.ext import commands
from datetime import datetime
import discord

from bot.session_manager import session_manager
from bot.server_session import ServerSession


class Skip(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='skip',
        description='Skip the current song.'
    )
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild.id

        if guild_id not in session_manager.server_sessions:
            await ctx.respond('No songs in queue!')
            return

        session: ServerSession = session_manager.server_sessions[guild_id]

        if session.queue:
            await ctx.respond('Skipping!')
            session.skipped = True

            if session.loop_current:
                session.queue.pop(0)
                await ctx.respond('Switching loop mode to queue.')
                session.loop_current, session.loop_queue = False, True

            if len(session.queue) == 1:
                session.voice_client.stop()
            else:
                session.last_played_time = datetime.now()
                # Less latency, ffmpeg process not terminated
                session.voice_client.pause()
                await session.play_next(ctx)
        else:
            await ctx.respond('No songs in queue!')


def setup(bot):
    bot.add_cog(Skip(bot))
