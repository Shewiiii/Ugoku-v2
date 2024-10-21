import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager


class Resume(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_resume(self, ctx: discord.ApplicationContext) -> None:
        session = session_manager.server_sessions.get(ctx.guild.id)

        if not session:
            await ctx.respond('Nothing to resume!')
            return

        voice_client = session.voice_client

        if voice_client.is_paused():
            voice_client.resume()
            await ctx.respond('Resumed!')
        else:
            await ctx.respond('The audio is not paused.')

    @commands.slash_command(
        name='resume',
        description='Resume the current song.'
    )
    async def resume(self, ctx: discord.ApplicationContext) -> None:
        await self.execute_resume(ctx)


def setup(bot):
    bot.add_cog(Resume(bot))
