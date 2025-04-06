import discord
from discord.ext import commands
from typing import TYPE_CHECKING

from bot.vocal.session_manager import session_manager as sm
from bot.utils import vocal_action_check, send_response

if TYPE_CHECKING:
    from bot.vocal.server_session import ServerSession


class Loop(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_loop(
        self, ctx: discord.ApplicationContext, mode: str, silent: bool = False
    ) -> None:
        guild_id: int = ctx.guild.id
        session: "ServerSession" = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond, silent=silent):
            return

        mode = mode.lower()

        if mode == "song":
            session.loop_current = not session.loop_current
            state = "now" if session.loop_current else "no longer"
            response = f"You are {state} looping the current song!"
        elif mode == "queue":
            session.loop_queue = not session.loop_queue
            if session.loop_queue:
                session.loop_current = False
                response = "You are now looping the queue!"
            else:
                await session.close_streams(tracks=session.to_loop)
                session.to_loop.clear()
                response = "You are not looping the queue anymore."

        else:
            response = "oi"

        send_response(ctx.respond, response, guild_id, silent)
        await session.now_playing_view.update_buttons()

    @commands.slash_command(
        name="loop", description="Loop/Unloop what you are listening to in VC."
    )
    async def loop(
        self,
        ctx: discord.ApplicationContext,
        mode: discord.Option(str, choices=["Song", "Queue"], default="Queue"),  # type: ignore
    ) -> None:
        await self.execute_loop(ctx, mode)


def setup(bot):
    bot.add_cog(Loop(bot))
