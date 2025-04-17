import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import spotipy
from dotenv import load_dotenv
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.zeroconf import ZeroconfServer
from librespot.audio import AbsChunkedInputStream
from spotipy.oauth2 import SpotifyClientCredentials

from bot.search import is_url
from bot.vocal.track_dataclass import Track
from config import (
    SPOTIFY_TOP_COUNTRY,
    SPOTIFY_ENABLED,
    SPOTIFY_API_ENABLED,
    SPOTIFY_REFRESH_INTERVAL,
)


logging.getLogger("zeroconf").setLevel(logging.ERROR)


# Spotify Application credentials
class SpotifyConfig:
    def __init__(self) -> None:
        load_dotenv()
        self.client_id = os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")


# Initialize Librespot and Spotipy sessions
class SpotifySessions:
    def __init__(self) -> None:
        self.config = SpotifyConfig()
        self.lp: Optional[Librespot] = None
        self.sp: Optional[spotipy.Spotify] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def init_spotify(self) -> None:
        try:
            self.loop = asyncio.get_running_loop()

            # Librespot
            if SPOTIFY_ENABLED:
                self.lp = Librespot()
                await self.lp.create_session()
                asyncio.create_task(self.lp.listen_to_session())

            # Spotify API
            if SPOTIFY_API_ENABLED:
                self.sp = spotipy.Spotify(
                    auth_manager=SpotifyClientCredentials(
                        client_id=self.config.client_id,
                        client_secret=self.config.client_secret,
                    )
                )

            logging.info("Spotify sessions initialized successfully")

        except Exception as e:
            logging.error(f"Error initializing Spotify sessions: {repr(e)}, retrying in 10 seconds")
            await asyncio.sleep(10)
            await self.init_spotify()


def get_album_name(name) -> str:
    """Extract the album name from the album information.
    Returns '?' if no name is found."""
    if isinstance(name, str):
        return name
    elif isinstance(name, dict):
        return str(name.get("name", "?"))
    elif isinstance(name, list) and name:
        return name[0] if isinstance(name[0], str) else "?"
    return "?"


def get_cover_url(album) -> str:
    """Extract the cover URL from the album information.
    Returns an empty string if no image is found."""
    images = album.get("images", [])
    if images and isinstance(images[0], dict):
        return images[0].get("url", "")
    return album.get("cover", "")


SPOTIFY_URL_REGEX = re.compile(
    r"https?://open\.spotify\.com/(?:(?:intl-[a-z]{2})/)?"
    r"(track|album|playlist|artist)/(?P<ID>[0-9a-zA-Z]{22})",
    re.IGNORECASE,
)


class Librespot:
    def __init__(self) -> None:
        self.updated: Optional[datetime] = None
        self.session: Optional[Session] = None
        self.loop = asyncio.get_running_loop()
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def create_session(self, path: Path = Path("./credentials.json")) -> None:
        """Wait for credentials and generate a json file if needed."""
        if not path.exists():
            logging.warning(
                "Please log in to Librespot from Spotify's official client! "
                "Any command using Spotify features will not work."
            )
            session = await self.loop.run_in_executor(
                self.executor, ZeroconfServer.Builder().create
            )
            while not path.exists():
                await asyncio.sleep(1)
            logging.info(
                "Credentials saved Successfully, closing Zeroconf session. "
                "You can now close Spotify. ( ^^) _旦~~"
            )
            session.close_session()

        await self.generate_session()

    async def generate_session(self) -> None:
        if self.session:
            return
        self.session = await self.loop.run_in_executor(
            self.executor, lambda: Session.Builder().stored_file().create()
        )
        self.updated = datetime.now()
        logging.info("Librespot session created!")

    async def close_session(self) -> None:
        """Close the Librespot session."""
        if self.session:
            await self.loop.run_in_executor(self.executor, self.session.close)
            self.session = None
            logging.info("Librespot session closed.")

    async def refresh_librespot(self) -> None:
        if self.session:
            try:
                await self.close_session()
            except Exception:
                # To precise, except ConnectionAbortedError is
                # interrupting the function
                pass
            self.session = None
        try:
            await self.generate_session()
        except Exception as e:
            logging.error(
                f"An error occurred when refreshing Librespot: {e},"
                "retying in 5 seconds..."
            )
            await asyncio.sleep(5)
            await self.refresh_librespot()
        logging.info("Librespot session regenerated successfully.")

    async def listen_to_session(self) -> None:
        """Read data from Spotify, regenerate Librespot session on failure."""
        retry_delay = 1
        max_retry_delay = 60
        track_id = await asyncio.to_thread(
            TrackId.from_uri, "spotify:track:4oLiJFE0PE8ZKTVNraDt7s"
        )
        while True:
            try:
                while True:
                    try:
                        logging.debug("Check Librespot session..")
                        # Simulate a track play
                        stream = await self.get_stream(track_id)
                        await asyncio.to_thread(stream.read, 1)
                        await asyncio.sleep(SPOTIFY_REFRESH_INTERVAL)
                    except Exception as e:
                        logging.error(f"Stream read error: {repr(e)}")
                        await self.refresh_librespot()
                        await asyncio.sleep(10)
                        # Break to outer loop to get a new stream
                        break
            except Exception as e:
                logging.error(f"Error getting stream or refreshing session: {e}")
                await asyncio.sleep(retry_delay)
                # Exponential backoff
                retry_delay = min(max_retry_delay, retry_delay * 2)

    async def get_stream(
        self, track_id: TrackId, audio_quality: AudioQuality = AudioQuality.VERY_HIGH
    ) -> AbsChunkedInputStream:
        stream = await asyncio.to_thread(
            self.session.content_feeder().load,
            track_id,
            VorbisOnlyAudioQuality(audio_quality),
            False,
            None,
        )
        return stream.input_stream.stream()


class Spotify:
    def __init__(self, sessions: SpotifySessions) -> None:
        """Initializes the Spotify class with SpotifySessions."""
        self.sessions = sessions

    async def generate_stream(self, id_: str) -> AbsChunkedInputStream:
        """Generates a stream for a given Spotify track ID."""
        track_id = await asyncio.to_thread(TrackId.from_uri, f"spotify:track:{id_}")
        stream = await self.sessions.lp.get_stream(
            track_id, audio_quality=AudioQuality.VERY_HIGH
        )
        return stream

    def get_track(self, track_api: dict, album_info: Optional[dict] = None) -> Track:
        """Extracts and returns track information from Spotify API response."""
        id_ = track_api["id"]
        album = album_info or track_api.get("album", {})
        album_name = get_album_name(album.get("name"))
        cover_url = get_cover_url(album)
        duration = round(track_api["duration_ms"] / 1000)

        track = Track(
            service="spotify/deezer",
            id=id_,
            title=track_api["name"],
            album=album_name,
            cover_url=cover_url,
            duration=duration,
            track_number=track_api["track_number"],
            disc_number=track_api["disc_number"],
            source_url=f"https://open.spotify.com/track/{id_}",
            stream_generator=lambda: self.generate_stream(id_),
            unloaded_embed=True,
        ).set_artists([artist["name"] for artist in track_api["artists"]])
        return track

    async def fetch_id(
        self,
        query: str,
        album: bool = False,
    ) -> dict:
        """Fetch the Spotify ID and type either from a URL or search query."""
        if is_url(query, ["open.spotify.com"]):
            m = SPOTIFY_URL_REGEX.match(query)
            if m:
                return {"id": m.group("ID"), "type": m.group(1)}
            return {}

        items = await self.search(query, limit=1)
        if not items:
            return {}

        item = items[0]
        return {
            "id": item["album"]["id"] if album else item["id"],
            "type": "album" if album else "track",
        }

    async def get_tracks(
        self,
        query: Optional[str] = None,
        offset: int = 0,
        album: bool = False,
        id_: Optional[str] = None,
        type: Optional[str] = None,
    ) -> list[Track]:
        """Fetch tracks from a URL or search query.
        This method can handle tracks, albums, playlists, and artists."""
        if not id_ and not type:
            if not query:
                return []
            result = await self.fetch_id(query, album)
            if not result:
                return []
            id_, type = result["id"], result["type"]

        tracks: list[Track] = []

        # TRACK
        if type == "track":
            track_api: dict = await asyncio.to_thread(
                self.sessions.sp.track, track_id=id_
            )
            tracks.append(self.get_track(track_api))

        # ALBUM
        elif type == "album":
            album_API: dict = await asyncio.to_thread(
                self.sessions.sp.album, album_id=id_
            )
            album_info = {
                "name": album_API["name"],
                "cover": album_API["images"][0]["url"] if album_API["images"] else None,
                "url": album_API["external_urls"]["spotify"],
            }
            for track in album_API["tracks"]["items"]:
                tracks.append(self.get_track(track, album_info))

        # PLAYLIST
        elif type == "playlist":
            playlist_API: dict = await asyncio.to_thread(
                self.sessions.sp.playlist_tracks, playlist_id=id_, offset=offset
            )
            for item in playlist_API["items"]:
                if item and "track" in item and item["track"]:
                    tracks.append(self.get_track(item["track"]))

        # ARTIST
        elif type == "artist":
            artist_API: dict = await asyncio.to_thread(
                self.sessions.sp.artist_top_tracks,
                artist_id=id_,
                country=SPOTIFY_TOP_COUNTRY,
            )
            for track in artist_API["tracks"]:
                tracks.append(self.get_track(track))

        return tracks

    async def search(
        self, query: str, limit: int = 10, offset: int = 0, type: str = "track"
    ) -> list:
        """Search for tracks on Spotify."""
        track_items = (
            await asyncio.to_thread(
                self.sessions.sp.search, query, limit=limit, offset=offset, type=type
            )
        )[f"{type}s"]["items"]

        return track_items
