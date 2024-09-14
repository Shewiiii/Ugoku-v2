import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager as sm


class Leave(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='leave',
        description='Nooooo （＞人＜；）'
    )
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)

        if session:
            await ctx.respond('Baibai~')
            voice_client: discord.VoiceClient = session.voice_client
            await voice_client.disconnect()
            voice_client.cleanup()
            del sm.server_sessions[guild_id]


def setup(bot):
    bot.add_cog(Leave(bot))
