import asyncio
import discord
from discord.ext import commands
import httpx
from spotipy.exceptions import SpotifyException

from bot.search import is_url
from bot.utils import get_cache_path
from config import DEEZER_ENABLED
from deezer_decryption.download import Download


class DeezerDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.download = Download()

    @commands.slash_command(
        name='dzdl',
        description='Download lossless songs from Deezer. Spotify URLs are compatible.',
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        }
    )
    async def dzdl(
        self,
        ctx: discord.ApplicationContext,
        query: str
    ) -> None:
        if not DEEZER_ENABLED:
            await ctx.respond(content='Deezer features are not enabled.')
            return
        await ctx.respond('Give me a second~')
        is_spotify_url = is_url(query, ['open.spotify.com'])
        track_not_found_message = 'Track not found !'

        if is_spotify_url:
            native_track_api = await self.download.api.parse_spotify_track(query, self.bot.spotify.sessions.sp)
            if not native_track_api:
                await ctx.edit(content=track_not_found_message)
                return
            query = native_track_api.get('id')

        try:
            path = await self.download.track_from_query(query, upload_=True, bot=self.bot, ctx=ctx, track_id=is_spotify_url)
        except httpx.ConnectTimeout:
            await ctx.edit(content='Connection timed out, please try again !')
            return

        if not path:
            await ctx.edit(content=track_not_found_message)


def setup(bot):
    bot.add_cog(DeezerDownload(bot))
