import asyncio
import aiofiles
import logging

import discord
from discord.ext import commands
from librespot.audio.decoders import AudioQuality

from config import SPOTIFY_ENABLED
from bot.utils import tag_ogg_file, get_cache_path, upload
from bot.vocal.track_dataclass import Track
from mutagen.oggvorbis import OggVorbisHeaderError


class SpotifyDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="spdl",
        description="Download songs from Spotify.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def spdl(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        quality: discord.Option(
            str,
            choices=["High (OGG 320kbps)", "Normal (OGG 160kbps)", "Low (OGG 96kbps)"],
            default="High (OGG 320kbps)",
        ),  # type: ignore
    ) -> None:
        # The following is a proof of concept code~
        # TODO:
        # - Add album/playlist support
        # - Add messages context

        if not SPOTIFY_ENABLED:
            await ctx.respond(content="Spotify features are not enabled.")
            return

        asyncio.create_task(ctx.respond("Give me a second~"))

        # Quality dict
        quality_dict = {
            "High (OGG 320kbps)": AudioQuality.VERY_HIGH,
            "Normal (OGG 160kbps)": AudioQuality.HIGH,
            "Low (OGG 96kbps)": AudioQuality.NORMAL,
        }

        # Get the tracks, pick the first one
        tracks = await ctx.bot.spotify.get_tracks(query=query, aq=quality_dict[quality])
        if not tracks:
            await ctx.edit(content="No track has been found!")
            return
        track: Track = tracks[0]

        # Update cached files
        cache_id = f"spotify{track.id}"
        file_path = get_cache_path(cache_id.encode("utf-8"))

        if not file_path.is_file():
            # Get track data
            stream = await track.stream_source()
            data = await asyncio.to_thread(stream.read)
            # Download
            async with aiofiles.open(file_path, "wb") as file:
                await file.write(data)
            try:
                # Tag
                await tag_ogg_file(
                    file_path=file_path,
                    title=track.title,
                    artist=track.artist,
                    date=track.date,
                    album_cover_url=track.cover_url,
                    album=track.album,
                    track_number=track.track_number,
                    disc_number=track.disc_number,
                )
            except OggVorbisHeaderError:
                logging.warning(f"Unable to read the full header of {file_path}")

        await upload(self.bot, ctx, file_path, f"{track}.ogg")


def setup(bot):
    bot.add_cog(SpotifyDownload(bot))
