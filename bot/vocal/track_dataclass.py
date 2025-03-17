import asyncio
from dataclasses import dataclass, field
import logging
from pathlib import Path
from time import perf_counter
from typing import Literal, Union, Optional, Self

import discord
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from librespot.audio import AbsChunkedInputStream
import spotipy

from bot.utils import get_dominant_rgb_from_url
from deezer_decryption.api import Deezer
from config import DEFAULT_EMBED_COLOR, DEEZER_ENABLED, SPOTIFY_ENABLED


@dataclass()
class Track:
    service: Literal["spotify/deezer", "youtube", "onsei", "custom"]
    id: Union[str, int] = 0
    title: str = "?"
    artist: str = "?"
    artists: list[str] = field(default_factory=lambda: ["?"])
    album: str = "?"
    source_url: Optional[str] = None
    stream_source: Union[
        str, Path, AbsChunkedInputStream, DeezerChunkedInputStream, None
    ] = None
    embed: Optional[discord.Embed] = None
    unloaded_embed: bool = False
    # True if an embed is available but waiting to be loaded
    date: str = ""
    cover_url: str = ""
    duration: Union[str, int, float] = "?"
    track_number: int = 1
    disc_number: int = 1
    dominant_rgb: tuple = DEFAULT_EMBED_COLOR

    def __eq__(self, other):
        (self.id, self.service) == (other.id, other.service)

    def __repr__(self):
        return f"{self.artist} - {self.title}"

    def __format__(self, format_spec):
        if format_spec == "markdown" and self.source_url:
            return f"[{str(self)}](<{self.source_url}>)"
        else:
            return str(self)

    def set_artist(self, artist: str) -> Self:
        self.artist = artist
        self.artists = [artist]
        return self

    def set_artists(self, artists: list) -> Self:
        if artists:
            self.artists = artists
            self.artist = ", ".join(artists)
        return self

    def create_embed(
        self, album_url: Optional[str] = None, artist_urls: Optional[list[str]] = None
    ) -> Self:
        embed_artists, embed_album = self.artist, self.album

        if album_url:
            embed_album = f"[{self.album}]({album_url})"

        if artist_urls:
            embed_artists = ", ".join(
                [
                    f"[{self.artists[i]}]({artist_urls[i]})"
                    for i in range(len(artist_urls))
                ]
            )

        self.embed = (
            discord.Embed(
                title=self.title,
                url=self.source_url,
                description=f"By {embed_artists}",
                color=discord.Colour.from_rgb(*self.dominant_rgb),
            )
            .add_field(name="Part of the album", value=embed_album, inline=True)
            .set_author(name="Now playing")
            .set_thumbnail(url=self.cover_url)
        )
        return self

    async def generate_embed(
        self, sp: Optional[spotipy.Spotify] = None
    ) -> discord.Embed:
        """Get the cover's dominant RGB before creating a Disord embed.
        If a Spotify class (spotipy) is given,
        album and artist markdowns will be added if available."""
        album_url = None
        artist_urls = None

        if sp:
            track_api: dict = await asyncio.to_thread(sp.track, self.id)
            album: str = track_api["album"]
            album_url: str = album["external_urls"]["spotify"]
            artist_urls: list[str] = [
                artist["external_urls"]["spotify"] for artist in track_api["artists"]
            ]

        self.dominant_rgb = await get_dominant_rgb_from_url(self.cover_url)
        self.create_embed(album_url, artist_urls)
        self.unloaded_embed = False
        logging.info(f"Embed of {self} generated")

        return self.embed

    async def load_deezer_stream(
        self,
        bot: discord.Bot,
        deezer_blacklist: set,
    ) -> Optional[DeezerChunkedInputStream]:
        start = perf_counter()

        is_deezer_enabled = DEEZER_ENABLED
        is_service_valid = self.service == "spotify/deezer"
        is_stream_source_unprocessed = not isinstance(self.stream_source, (str, Path))
        is_not_blacklisted = self.id not in deezer_blacklist

        should_preload_stream = (
            is_deezer_enabled
            and is_service_valid
            and is_stream_source_unprocessed
            and is_not_blacklisted
        )

        if not should_preload_stream:
            return

        deezer: Deezer = bot.deezer

        # Already a Deezer stream: reset the position
        if isinstance(self.stream_source, DeezerChunkedInputStream):
            await asyncio.to_thread(self.stream_source.set_chunks, timer_start=start)
            # If seeking: current position will automatically be set by Ffmpeg's pipe
            self.stream_source.current_position = 0
            return self.stream_source

        # Try to get native track API (to grab the song from irsc)
        native_track_api = await deezer.parse_spotify_track(
            self.source_url, bot.spotify.sessions.sp
        )

        # Load the stream
        stream_loaded = False
        if native_track_api:
            gw_track_api = await deezer.get_track(native_track_api["id"])
            if gw_track_api:
                stream_urls = await deezer.get_stream_urls(
                    [gw_track_api["TRACK_TOKEN"]]
                )
                if stream_urls:
                    stream_url = stream_urls[0]
                    stream_loaded = True

        if not stream_loaded:
            deezer_blacklist.add(self.id)
            return

        self.stream_source = DeezerChunkedInputStream(
            native_track_api["id"], stream_url, gw_track_api["TRACK_TOKEN"], bot, self
        )
        await asyncio.to_thread(self.stream_source.set_chunks, timer_start=start)

        return self.stream_source

    async def load_spotify_stream(self) -> Optional[AbsChunkedInputStream]:
        if not SPOTIFY_ENABLED:
            return

        # Handle Spotify stream generators
        if callable(self.stream_source):
            try:
                self.stream_source = await self.stream_source()
            except Exception as e:
                logging.error(repr(e))
                return
            logging.info(f"Loaded Spotify stream of {self}")

        # Skip non-audio content in Spotify streams
        if isinstance(self.stream_source, AbsChunkedInputStream):
            await asyncio.to_thread(self.stream_source.seek, 167)
            return self.stream_source

    async def load_stream(
        self, *args
    ) -> Optional[Union[AbsChunkedInputStream, DeezerChunkedInputStream]]:
        self.stream_source = (
            await self.load_deezer_stream(*args) or await self.load_spotify_stream()
        )
        return self.stream_source
