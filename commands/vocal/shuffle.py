from typing import Optional
import asyncio

from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Shuffle(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_shuffle(
        self,
        ctx: discord.ApplicationContext,
        silent: bool = False
    ) -> None:
        guild_id: int = ctx.guild.id
        session: Optional[ServerSession] = sm.server_sessions.get(guild_id)
        if not await vocal_action_check(session, ctx, ctx.respond, silent=True):
            return

        await session.shuffle_queue()
        response_message = "Queue shuffled!" if session.shuffle else "Original queue order restored."
        await send_response(ctx.respond, response_message, guild_id, silent)
        await session.now_playing_view.update_buttons()
        await session.prepare_next_track()

    @commands.slash_command(
        name='shuffle',
        description='Shuffle the queue.'
    )
    async def shuffle(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        await self.execute_shuffle(ctx)


def setup(bot):
    bot.add_cog(Shuffle(bot))
