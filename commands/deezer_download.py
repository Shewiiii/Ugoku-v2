import asyncio
import os
import logging

import discord
from discord.ext import commands
from deezer.errors import DataException

from config import DEEZER_ENABLED
from bot.utils import cleanup_cache, tag_ogg_file, get_cache_path


class DeezerDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='dzdl',
        description='Download lossless songs from Deezer.',
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
            track = await self.bot.deezer.get_stream_url_from_query(query)
        except DataException:
            await ctx.edit(content="Track not found !")
            return

        # Set the cache path
        cleanup_cache()
        file_path = get_cache_path(str(track['track_id']).encode('utf-8'))

        # Download
        if not file_path.is_file():
            file_path = await asyncio.to_thread(self.bot.deezer.download, track)

        # Upload if possible
        size = os.path.getsize(file_path)
        if size < ctx.guild.filesize_limit:
            await ctx.edit(
                content="Here you go !",
                file=discord.File(
                    file_path,
                    # To change !
                    f"track.flac",
                )
            )
        else:
            await ctx.edit(content=f"Download failed: file too big.")


def setup(bot):
    bot.add_cog(DeezerDownload(bot))