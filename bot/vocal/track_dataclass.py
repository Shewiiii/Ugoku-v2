import asyncio
import aiofiles
from dataclasses import dataclass, field, fields
import logging
from pathlib import Path
from math import floor
from time import time
from typing import Literal, Union, Optional, Self, Callable, TYPE_CHECKING

import discord
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from librespot.audio import AbsChunkedInputStream
import spotipy

from bot.utils import get_dominant_rgb_from_url, get_cache_path
from deezer_decryption.api import Deezer
from config import (
    DEFAULT_EMBED_COLOR,
    DEEZER_ENABLED,
    SPOTIFY_ENABLED,
    AGRESSIVE_CACHING,
)

if TYPE_CHECKING:
    from bot.vocal.server_session import ServerSession


class Timer:
    def __init__(self):
        self._start_time = None
        self._elapsed_time_accumulator = 0

    def start(self) -> None:
        if self._start_time is None:
            self._start_time = time()

    def stop(self) -> float:
        if self._start_time is not None:
            self._elapsed_time_accumulator += time() - self._start_time
        self._start_time = None

    def get(self) -> int:
        current_elapsed = self._elapsed_time_accumulator
        if self._start_time is not None:
            current_elapsed += time() - self._start_time
        return floor(current_elapsed)

    def reset(self) -> int:
        self.__init__()


@dataclass()
class Track:
    service: Literal["spotify/deezer", "ytdlp", "onsei", "custom"]
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
    timer: Timer = Timer()
    stream_generator: Optional[Callable] = None
    loading_event: Optional[asyncio.Event] = None
    # "Loading event" is only used for ytdlp sources for now,
    # Spotify and deezer streams need to be reloaded
    # (paths are out of the equation because of the early return above)
    file_extension: Optional[str] = None  # Needed for Yt-dlp
    cache_event: Optional[asyncio.Event] = None

    def __eq__(self, other):
        return self.stream_source == other.stream_source

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
    ) -> discord.Embed:
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
            .add_field(name="Remaining", value="", inline=True)  # fields index: 1
            .add_field(name="Next", value="", inline=True)  # fields index: 2
            .set_author(name="Now playing")
            .set_thumbnail(url=self.cover_url)
        )
        return self.embed

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

    async def load_deezer_stream(self, session: "ServerSession") -> bool:
        is_deezer_enabled = DEEZER_ENABLED
        is_service_valid = self.service == "spotify/deezer"
        is_stream_source_uncached = not isinstance(self.stream_source, (str, Path))
        is_not_blacklisted = self.id not in session.deezer_blacklist

        should_load_stream = (
            is_deezer_enabled
            and is_service_valid
            and is_stream_source_uncached
            and is_not_blacklisted
        )

        if not should_load_stream:
            return False

        deezer: Deezer = session.bot.deezer

        # Already a Deezer stream
        if isinstance(self.stream_source, DeezerChunkedInputStream):
            await asyncio.to_thread(self.stream_source.set_chunks)
            return True

        # Try to get native track API (to grab the song from irsc)
        native_track_api = await deezer.parse_spotify_track(
            self.source_url, session.bot.spotify.sessions.sp
        )

        # Load the stream
        stream_loaded = False
        if native_track_api:
            gw_track_api = await deezer.get_track(native_track_api["id"])
            if gw_track_api:
                stream_urls = await deezer.get_stream_urls(
                    [gw_track_api["TRACK_TOKEN"]]
                )
                stream_url = stream_urls[0]
                if stream_url:
                    stream_loaded = True

        if not stream_loaded:
            session.deezer_blacklist.add(self.id)
            return False

        self.stream_source = DeezerChunkedInputStream(
            native_track_api["id"],
            stream_url,
            gw_track_api["TRACK_TOKEN"],
            session.bot.deezer,
            str(self),
            self.timer,
        )
        await asyncio.to_thread(self.stream_source.set_chunks)
        logging.info(f"Loaded Deezer stream of {self}")
        return True

    async def load_spotify_stream(self, session: "ServerSession") -> bool:
        if not SPOTIFY_ENABLED:
            if isinstance(self.stream_generator, Callable):
                self.stream_source = None
            return False
        elif self.stream_source:
            if session.is_seeking or session.loop_current:
                # Reload a stream to avoid seeking issues
                # but it's not the most optimized
                old_source = self.stream_source
                asyncio.create_task(asyncio.to_thread(old_source.close))
            else:
                return True

        # Handle Spotify stream generators
        if callable(self.stream_generator):
            try:
                self.stream_source = await self.stream_generator()
            except Exception as e:
                logging.error(repr(e))
                return False
            logging.info(f"Loaded Spotify stream of {self}")

        # If agressive caching is enabled, save the stream to a cache file
        if AGRESSIVE_CACHING:
            cache_id = f"spotify{self.id}"
            file_path = get_cache_path(cache_id)

            if not file_path.with_suffix(".valid").is_file():
                self.cache_event = asyncio.Event()
                asyncio.create_task(self.store_spotify_stream(file_path))

                # Wait for the first write
                await self.cache_event.wait()
                self.cache_event = None

            self.stream_source = file_path

        else:
            # Skip non-audio content in Spotify streams
            await asyncio.to_thread(self.stream_source.seek, 167)

        return True

    async def store_spotify_stream(self, file_path: Path) -> bool:
        if not SPOTIFY_ENABLED:
            return False

        # Download
        stream = self.stream_source
        async with aiofiles.open(file_path, "wb") as file:
            while True:
                data = await asyncio.to_thread(stream.read, 4096)
                if not data:
                    break
                await file.write(data)
                if self.cache_event:
                    self.cache_event.set()

        # If the download is sucessful, create a "valid" marker
        async with aiofiles.open(file_path.with_suffix(".valid"), "w"):
            ...

        return True

    async def load_youtube(self) -> bool:
        if not self.stream_generator:
            return False
        new_track: Track = (await self.stream_generator())[0]
        relevant_fields = {
            "title",
            "artist",
            "artists",
            "album",
            "source_url",
            "embed",
            "stream_source",
            "cover_url",
            "duration",
        }
        for f in fields(new_track):
            if f.name in relevant_fields:
                setattr(self, f.name, getattr(new_track, f.name))
        logging.info(f"Loaded Youtube stream of {self}")
        return True

    async def load_stream(
        self, session: Optional["ServerSession"] = None
    ) -> Optional[Union[AbsChunkedInputStream, DeezerChunkedInputStream]]:
        if isinstance(self.stream_source, (Path, str)):
            return

        match self.service:
            case "spotify/deezer":
                if not session:
                    raise ValueError("Session param missing")
                if not await self.load_deezer_stream(session):
                    await self.load_spotify_stream(session)

            case "ytdlp":
                # You probably dont wanna reload yt-dlp streams
                if self.loading_event:
                    try:
                        await asyncio.wait_for(self.loading_event.wait(), 10.0)
                    except TimeoutError:
                        ...
                else:
                    self.loading_event = asyncio.Event()
                    try:
                        await self.load_youtube()
                    finally:
                        self.loading_event.set()

        return self.stream_source

    async def close_stream(self, clear: bool = False) -> None:
        source = self.stream_source
        try:
            if isinstance(source, DeezerChunkedInputStream):
                # Built-in stream (re)generator
                await (source.close() if clear else source.close_streams())
            elif isinstance(source, AbsChunkedInputStream):
                await asyncio.to_thread(source.close)
                self.stream_source = None

            if clear:
                self.stream_generator = None

        except Exception as e:
            logging.error(f"Error closing stream of {self}: {repr(e)}")

    async def close(self) -> None:
        if self.stream_source is not None:
            await self.close_stream(clear=True)

        if self.embed:
            self.embed.clear_fields()
            self.embed = None

        self.stream_source = None
        self.stream_generator = None
