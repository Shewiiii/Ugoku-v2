import discord
from discord.ext import commands
from datetime import datetime

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check


class AudioBitrate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name='audio-bitrate',
        description='Change the bitrate of the audio session, from 6 to 510 kbps.',
        integration_types={
            discord.IntegrationType.guild_install
        }
    )
    async def bitrate(
        self,
        ctx: discord.ApplicationContext,
        bitrate: int
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond):
            return

        if not 6 <= bitrate <= 510:
            await ctx.respond(f"Invalid bitrate: {bitrate} kbps !")

        session.bitrate = bitrate
        current_pos = session.time_elapsed + \
            int((datetime.now() - session.last_played_time).total_seconds())
        await ctx.respond(f"Changing the bitrate to {bitrate} kbps !")
        await session.seek(current_pos, quiet=True)


def setup(bot):
    bot.add_cog(AudioBitrate(bot))
