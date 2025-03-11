from discord.ext import commands
from datetime import datetime
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check
from commands.vocal.now_playing import NowPlaying


class Skip(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_skip(
        self,
        ctx: discord.ApplicationContext,
        silent: bool = False,
        resend_now_playing_embed: bool = False
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, silent=silent):
            return

        send_response(ctx.respond, "Skipping!", session.guild_id, silent)

        # SKIP
        session.skipped = True
        if session.loop_current:
            session.loop_current = False

        if not len(session.queue) == 1:
            session.last_played_time = datetime.now()
        if resend_now_playing_embed:
            session.old_message = session.now_playing_message
            session.now_playing_message = None
        session.voice_client.stop()

    @commands.slash_command(
        name='skip',
        description='Skip the current song.'
    )
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_skip(ctx, resend_now_playing_embed=True)


def setup(bot):
    bot.add_cog(Skip(bot))
