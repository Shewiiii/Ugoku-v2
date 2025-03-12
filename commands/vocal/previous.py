import asyncio
from bot.vocal.session_manager import session_manager as sm
import discord
from discord.ext import commands

from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Previous(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_previous(
        self,
        ctx: discord.ApplicationContext,
        silent: bool = False,
        resend_now_playing_embed=False,
    ) -> None:
        guild_id: int = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not vocal_action_check(
            session, ctx, ctx.respond, check_queue=False, silent=silent
        ):
            return

        session: ServerSession
        if not session.stack_previous:
            send_response(ctx.respond, "No tracks played previously!", guild_id, silent)
            return

        send_response(ctx.respond, "Playing the previous track!", guild_id, silent)
        if resend_now_playing_embed:
            session.old_message = session.now_playing_message
            session.now_playing_message = None
        asyncio.create_task(session.play_previous(ctx))

    @commands.slash_command(name="previous", description="Play the previous track.")
    async def previous(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_previous(ctx, resend_now_playing_embed=True)


def setup(bot):
    bot.add_cog(Previous(bot))
