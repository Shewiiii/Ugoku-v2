from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import send_response, vocal_action_check


class Shuffle(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_shuffle(
        self, ctx: discord.ApplicationContext, silent: bool = False
    ) -> None:
        guild_id: int = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if (
            not vocal_action_check(session, ctx, ctx.respond, silent=True)
            or len(session.queue) <= 2
        ):
            send_response(ctx.respond, "Nothing to shuffle !", guild_id, silent)
            return

        session: ServerSession
        await session.shuffle_queue()
        response_message = (
            "Queue shuffled!" if session.shuffle else "Original queue order restored."
        )
        send_response(ctx.respond, response_message, guild_id, silent)
        await session.load_next_tracks()

    @commands.slash_command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_shuffle(ctx)


def setup(bot):
    bot.add_cog(Shuffle(bot))
