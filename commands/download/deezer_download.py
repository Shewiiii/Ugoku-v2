import httpx
import os
import logging

import discord
from discord.ext import commands
from deezer.errors import DataException

from config import DEEZER_ENABLED
from bot.utils import cleanup_cache, tag_flac_file, get_cache_path


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
        self.bot.downloading = True
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

        # Upload if possible
        # Define size limits
        size = os.path.getsize(file_path)
        size_limit = ctx.guild.filesize_limit if ctx.guild else 26214400
        try:
            if size < size_limit:
                await ctx.edit(
                    content="Here you go !",
                    file=discord.File(
                        file_path,
                        filename=f"{display_name}.flac"
                    )
                )
        except discord.errors.HTTPException as e:
            if e.status == 413:
                logging.error(
                    f"File not uploaded: {cache_id} is too big: {size}bytes")
        await ctx.edit(content=f"Download failed: file too big.")


def setup(bot):
    bot.add_cog(DeezerDownload(bot))
