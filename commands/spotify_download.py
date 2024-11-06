import asyncio
import os
import logging

import discord
from discord.ext import commands
from librespot.audio.decoders import AudioQuality

from config import SPOTIFY_ENABLED
from bot.utils import cleanup_cache, tag_ogg_file, get_cache_path
from mutagen.oggvorbis import OggVorbisHeaderError


class SpotifyDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='spdl',
        description='Download songs from Spotify.',
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        }
    )
    async def spdl(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        quality: discord.Option(
            str,
            choices=[
                'High (OGG 320kbps)',
                'Normal (OGG 160kbps)',
                'Low (OGG 96kbps)'
            ],
            default='High (OGG 320kbps)'
        )  # type: ignore
    ) -> None:
        # The following is a proof of concept code~
        # TODO:
        # - Add album/playlist support
        # - Add messages context

        if not SPOTIFY_ENABLED:
            await ctx.respond(content='Spotify features are not enabled.')
            return

        await ctx.respond('Give me a second~')

        # Quality dict
        quality_dict = {
            'High (OGG 320kbps)': AudioQuality.VERY_HIGH,
            'Normal (OGG 160kbps)': AudioQuality.HIGH,
            'Low (OGG 96kbps)': AudioQuality.NORMAL
        }

        self.bot.downloading = True
        try:
            # Get the tracks
            tracks = await ctx.bot.spotify.get_tracks(
                query=query,
                aq=quality_dict[quality]
            )
            if not tracks:
                await ctx.edit(content="No track has been found!")
                return
            # TO CHANGE, only get the first track
            track = tracks[0]

            # Update cached files
            cleanup_cache()
            # The idea: when the cover (url) changes, do not use the cached file
            cover_url: str = track['cover']
            file_path = get_cache_path(cover_url.encode('utf-8'))

            if not file_path.is_file():
                # Get track data
                stream = await track['source']()
                data = await asyncio.to_thread(stream.read)

                with open(file_path, 'wb') as file:
                    file.write(data)

                try:
                    await tag_ogg_file(
                        file_path=file_path,
                        title=track['title'],
                        artist=track['artist'],
                        album_cover_url=track['cover'],
                        album=track['album']
                    )
                except OggVorbisHeaderError:
                    logging.warning(
                        f"Unable to read the full header of {file_path}")

                size = len(data)

            else:
                size = os.path.getsize(file_path)

            if size < ctx.guild.filesize_limit:
                await ctx.edit(
                    content="Here you go!",
                    file=discord.File(
                        file_path,
                        f"{track['display_name']}.ogg",
                    )
                )
            else:
                await ctx.edit(
                    content=f"The download of {track['display_name']} "
                    'failed: file too big.'
                )
        finally:
            self.bot.downloading = False


def setup(bot):
    bot.add_cog(SpotifyDownload(bot))
