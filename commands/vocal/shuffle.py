from typing import Optional

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response
from discord.ext import commands
import discord


class Shuffle(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_shuffle(
        self,
        ctx: discord.ApplicationContext,
        send: bool = False
    ) -> None:
        guild_id: int = ctx.guild.id
        session: Optional[ServerSession] = sm.server_sessions.get(guild_id)
        respond = (ctx.send if send else ctx.respond)

        if not session:
            await send_response(
                respond,
                "You are not in a voice channel!",
                guild_id
            )
            return

        session.shuffle_queue()

        if session.shuffle:
            response_message = "Queue shuffled!"
        else:
            response_message = "Original queue order restored."

        await send_response(respond, response_message, guild_id)

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
