import asyncio
from pathlib import Path
import os

import discord
from discord.ext import commands
from librespot.audio.decoders import AudioQuality

from config import SPOTIFY_ENABLED, TEMP_FOLDER
from bot.utils import cleanup_cache, tag_ogg_file, get_cache_path


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
        # - Don't refresh Librespot while someone is downloading
        # - Add messages context

        if not SPOTIFY_ENABLED:
            await ctx.respond(content='Spotify features are not enabled.')
            return

        await ctx.respond('Wait a second~')

        # Quality dict
        quality_dict = {
            'High (OGG 320kbps)': AudioQuality.VERY_HIGH,
            'Normal (OGG 160kbps)': AudioQuality.HIGH,
            'Low (OGG 96kbps)': AudioQuality.NORMAL
        }

        # Get the tracks
        tracks = await ctx.bot.spotify.get_tracks(
            user_input=query,
            aq=quality_dict[quality]
        )

        if not tracks:
            await ctx.edit(content="No track has been found!")
            return

        # TO CHANGE, only get the first track
        track = tracks[0]
        stream = await track['source']()
        data = await asyncio.to_thread(stream.read)

        # Update cached files
        cleanup_cache()
        file_path = get_cache_path(data)

        if not file_path.is_file():
            with open(file_path, 'wb') as file:
                file.write(data)
                await tag_ogg_file(
                    file_path=file_path,
                    title=track['title'],
                    artist=track['artist'],
                    album_cover_url=track['cover'],
                    album=track['album']
                )
            size = len(data)

        else:
            size = os.path.getsize(file_path)

        if size < ctx.guild.filesize_limit:
            await ctx.send(
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


def setup(bot):
    bot.add_cog(SpotifyDownload(bot))
