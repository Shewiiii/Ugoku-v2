import asyncio
import discord
from discord.errors import Forbidden
from discord.ext import commands

from bot.search import is_url
from bot.utils import process_song_query, upload
from config import DEEZER_ENABLED
from deezer_decryption.constants import EXTENSION
from deezer_decryption.download import Download


class DeezerDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.download = Download(bot=self.bot)

    @commands.slash_command(
        name="dzdl",
        description="Download lossless songs from Deezer. Spotify URLs are compatible.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def dzdl(self, ctx: discord.ApplicationContext, query: str) -> None:
        if not DEEZER_ENABLED:
            await ctx.respond(content="Deezer features are not enabled.")
            return
        defer_task = asyncio.create_task(ctx.respond("Give me a second~"))

        # Convert the query
        try:
            query = await process_song_query(query, ctx.bot)
        except Forbidden:
            await defer_task
            await ctx.edit(content="I don't have access to that message !")
            return

        # vars
        spotify_url = is_url(query, ["open.spotify.com"])
        track_not_found_message = "Track not found !"

        if spotify_url:
            native_track_api = await self.download.api.parse_spotify_track(
                query, self.bot.spotify.sessions.sp
            )
            if not native_track_api:
                await ctx.edit(content=track_not_found_message)
                return
            query = native_track_api.get("id")

        try:
            path, track_data = await self.download.track_from_query(
                query, track_id=spotify_url
            )
        except asyncio.TimeoutError:
            await ctx.edit(content="Connection timed out, please try again !")
            return

        if not path:
            await ctx.edit(content=track_not_found_message)
            return

        filename = (
            f"{track_data['ART_NAME']} - {track_data['SNG_TITLE']}.{EXTENSION['FLAC']}"
        )
        await upload(ctx.bot, ctx, path, filename)


def setup(bot):
    bot.add_cog(DeezerDownload(bot))
