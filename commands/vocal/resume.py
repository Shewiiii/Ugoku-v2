from datetime import datetime

import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager
from bot.utils import send_response, vocal_action_check


class Resume(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_resume(
        self, ctx: discord.ApplicationContext, silent: bool = False
    ) -> None:
        guild_id = ctx.guild.id
        session = session_manager.server_sessions.get(ctx.guild.id)
        if not vocal_action_check(session, ctx, ctx.respond, silent=silent):
            return

        voice_client = session.voice_client
        if voice_client.is_paused():
            voice_client.resume()
            session.last_played_time = datetime.now()
            send_response(ctx.respond, "Resumed!", guild_id, silent)
        else:
            send_response(ctx.respond, "The audio is not paused.", guild_id, silent)

        await session.now_playing_view.update_buttons()

    @commands.slash_command(name="resume", description="Resume the current song.")
    async def resume(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_resume(ctx)


def setup(bot):
    bot.add_cog(Resume(bot))
