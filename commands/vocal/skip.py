from discord.ext import commands
import discord
from typing import Optional

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Skip(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_skip(
        self,
        ctx: discord.ApplicationContext,
        silent: bool = False,
        resend_now_playing_embed: bool = False,
    ) -> None:
        guild_id = ctx.guild.id
        session: Optional[ServerSession] = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, silent=silent):
            return

        session: ServerSession
        send_response(ctx.respond, "Skipping!", session.guild_id, silent)

        # SKIP
        session.skipped = True
        if session.loop_current:
            session.loop_current = False

        if resend_now_playing_embed:
            session.old_message = session.now_playing_message
            session.now_playing_message = None

        if not len(session.queue) == 1 and not session.voice_client.is_playing():
            # Retrigger the play loop if paused/stopped for whatever reasons
            session.after_playing(ctx)
        else:
            session.voice_client.stop()

    @commands.slash_command(name="skip", description="Skip the current song.")
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_skip(ctx, resend_now_playing_embed=True)


def setup(bot):
    bot.add_cog(Skip(bot))
