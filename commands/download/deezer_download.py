import httpx
import os
import logging

import discord
from discord.ext import commands
from deezer.errors import DataException

from config import DEEZER_ENABLED
from bot.utils import cleanup_cache, tag_flac_file, get_cache_path, upload


class DeezerDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

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

        # Get the track from query
        try:
            track = await self.bot.deezer.get_track_from_query(query)
        except DataException:
            await ctx.edit(content="Track not found !")
            return
        except httpx.HTTPError as e:
            await ctx.edit(content=f"Error when generating a crypted stream URL.\n-# error: {e}")

        # Set the cache path
        await cleanup_cache()
        cache_id = f"deezer{track['id']}"
        file_path = get_cache_path(cache_id.encode('utf-8'))

        # Download
        if not file_path.is_file():
            file_path = await self.bot.deezer.download(track)

        # Tag the file
        display_name = f"{track['artist']} - {track['title']}"
        await tag_flac_file(
            file_path,
            title=track['title'],
            date=track['date'],
            artist=track['artists'],
            album=track['album'],
            album_cover_url=track['cover']
        )

        await upload(self.bot, ctx, file_path, f"{display_name}.flac")


def setup(bot):
    bot.add_cog(DeezerDownload(bot))
