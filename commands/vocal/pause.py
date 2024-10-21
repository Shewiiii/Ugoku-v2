import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from datetime import datetime


class Pause(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    
    async def execute_pause(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild.id
        session: ServerSession | None = sm.server_sessions.get(guild_id)

        if not session:
            await ctx.respond("No active session!")
            return

        voice_client = session.voice_client

        if voice_client is None or not voice_client.is_connected():
            await ctx.respond("Ugoku is not connected to a voice channel.")
            return

        if voice_client.is_playing():
            voice_client.pause()
            session.last_played_time = datetime.now()
            await ctx.respond("Paused!")
        else:
            await ctx.respond("No audio is playing!")

    @commands.slash_command(
        name='pause',
        description='Pause the current song.'
    )
    async def execute(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_pause(ctx)

def setup(bot):
    bot.add_cog(Pause(bot))
