import asyncio
from pathlib import Path
import os

import discord
from discord.ext import commands

from config import SPOTIFY_ENABLED, TEMP_FOLDER
from bot.utils import cleanup_cache


class SpotifyDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='download',
        description='Download songs from Spotify.'
    )
    async def download(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        quality: discord.Option(
            str,
            choices=['Very High (OGG 320kbps)', 'High', 'Normal'],
            default='Very High (OGG 320kbps)'
        )  # type: ignore
    ) -> None:
        # The following is a proof of concept code~
        # TODO:
        # - Tag the file
        # - Add album/playlist support
        # - Don't refresh Librespot while someone is downloading
        # - Add messages context

        if not SPOTIFY_ENABLED:
            await ctx.respond(content='Spotify features are not enabled.')
            return

        await ctx.respond('Wait a second~')
        tracks = await ctx.bot.spotify.get_tracks(user_input=query)

        stream = await tracks[0]['source']()
        data = await asyncio.to_thread(stream.read)
        file_path = TEMP_FOLDER / f"{tracks[0]['display_name']}.ogg"

        # Update cached files
        cleanup_cache()

        if not file_path.is_file():
            with open(file_path, 'wb') as file:
                file.write(data)
            size = len(data)
        else:
            size = os.path.getsize(file_path)

        if size < ctx.guild.filesize_limit:
            await ctx.send(file=discord.File(file_path))
        else:
            await ctx.edit(
                content=f"The download of {tracks[0]['display_name']} "
                'failed: file too big.'
            )


def setup(bot):
    bot.add_cog(SpotifyDownload(bot))
