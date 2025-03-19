import asyncio
import discord
from discord.ext import commands

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check


class AudioBitrate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="audio-bitrate",
        description="Change the bitrate of the audio session, from 1 to 510 kbps.",
        integration_types={discord.IntegrationType.guild_install},
    )
    async def bitrate(self, ctx: discord.ApplicationContext, bitrate: int) -> None:
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond):
            return

        if not 0 <= bitrate <= 510:
            await ctx.respond(f"Invalid bitrate: {bitrate} kbps !")
            return

        session.bitrate = bitrate
        track = session.queue[0]
        track.timer.stop()
        asyncio.create_task(ctx.respond(f"Changing the bitrate to {bitrate} kbps !"))
        await session.seek(track.timer.get(), quiet=True)


def setup(bot):
    bot.add_cog(AudioBitrate(bot))
