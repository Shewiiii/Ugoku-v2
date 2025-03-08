import asyncio
import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager as sm

from bot.vocal.server_session import *
from bot.utils import send_response, vocal_action_check


class Previous(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_previous(
        self,
        ctx: discord.ApplicationContext,
        silent: bool = False
    ) -> None:
        guild_id: int = ctx.guild.id
        session: Optional[ServerSession] = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, check_queue=False, silent=silent):
            return

        if not session.stack_previous:
            send_response(ctx.respond, "No tracks played previously!", guild_id, silent)
            return

        send_response(ctx.respond, "Playing the previous track!", guild_id, silent)
        await session.play_previous(ctx)
        await session.now_playing_view.update_buttons(delay=0.5)

    @commands.slash_command(
        name='previous',
        description='Play the previous track.'
    )
    async def previous(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_previous(ctx)


def setup(bot):
    bot.add_cog(Previous(bot))
