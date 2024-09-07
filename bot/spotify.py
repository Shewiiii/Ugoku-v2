from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.zeroconf import ZeroconfServer
from librespot.metadata import TrackId
from librespot.core import Session
from dotenv import load_dotenv
import spotipy

from config import SPOTIFY_TOP_COUNTRY, LIBRESPOT_REFRESH_INTERVAL
from spotipy.oauth2 import SpotifyClientCredentials
from bot.search import is_url, token_sort_ratio
from bot.utils import get_accent_color

from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import discord
import logging
import aiohttp
import os
import re

logger = logging.getLogger(__name__)
logging.getLogger('zeroconf').setLevel(logging.ERROR)

# Spotify Application credentials
load_dotenv()
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')

# Librespot and Spotipy sessions
lp, sp = None, None

# Bot loop
loop = None


# Initialize Librespot and Spotipy sessions
async def init_spotify():
    global lp, sp, loop
    # Bot loop
    loop = asyncio.get_event_loop()
    # Librespot
    lp = Librespot()
    await lp.create_session()
    await lp.start_auto_refresh()
    # Spotipy
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials())


class Librespot:
    def __init__(self) -> None:
        self.updated = None
        self.session = None

    async def create_session(
        self,
        path: Path = Path('./credentials.json')
    ) -> None:
        """Check for credentials and create a session."""
        if not path.exists():
            logging.error(
                "Please log in to Librespot from Spotify's official client! "
                "Any command using Spotify features will not work."
            )
            session = await loop.run_in_executor(
                None,
                lambda: ZeroconfServer.Builder().create()
            )
            while not path.exists():
                await asyncio.sleep(1)
            logging.info(
                'Credentials saved Successfully, closing Zeroconf session. '
                'You can now close Spotify. ( ^^) _旦~~'
            )
            session.close_session()

    async def update_session(self) -> None:
        loop = asyncio.get_running_loop()
        self.session = await loop.run_in_executor(
            None,
            lambda: Session.Builder().stored_file().create()
        )
        self.updated = datetime.now()
        logging.info('Librespot session refreshed!')

    async def auto_refresh(self) -> None:
        while True:
            if not self.updated or (
                datetime.now() - self.updated) >= timedelta(
                    seconds=LIBRESPOT_REFRESH_INTERVAL):
                await self.update_session()
            await asyncio.sleep(LIBRESPOT_REFRESH_INTERVAL // 5)

    async def start_auto_refresh(self):
        asyncio.create_task(self.auto_refresh())


class Spotify_:
    async def generate_info_embed(self, track_id: str) -> discord.Embed:
        """Generates a Discord Embed with track information."""
        track_API = await loop.run_in_executor(
            None,
            lambda: sp.track(track_id)
        )
        track_name, album = track_API['name'], track_API['album']
        artist_string = ', '.join(
            f"[{artist['name']}]({artist['external_urls']['spotify']})"
            for artist in track_API['artists']
        )
        cover_url, track_url, album_url = (
            album['images'][0]['url'],
            f"https://open.spotify.com/track/{track_API['id']}",
            album['external_urls']['spotify']
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url) as response:
                cover_bytes = await response.read()
                dominant_rgb = get_accent_color(cover_bytes)

        embed = discord.Embed(
            title=track_name,
            url=track_url,
            description=f"By {artist_string}",
            color=discord.Colour.from_rgb(*dominant_rgb)
        ).add_field(
            name="Part of the album",
            value=f"[{album['name']}]({album_url})",
            inline=True
        ).set_author(
            name="Now playing"
        ).set_thumbnail(
            url=cover_url
        )

        return embed

    async def generate_stream(self, id: str):
        """Generates a stream for a given track ID."""

        track_id = await loop.run_in_executor(
            None,
            lambda: TrackId.from_uri(f"spotify:track:{id}")
        )

        stream = await loop.run_in_executor(
            None,
            lambda: lp.session.content_feeder().load(
                track_id, VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH),
                False,
                None
            )
        )

        return stream.input_stream.stream()

    def get_track_info(self, track_API: dict) -> dict:
        """Returns track info (display name, stream, embed)."""
        id = track_API['id']
        display_name = (
            f"{track_API['artists'][0]['name']} - "
            f"{track_API['name']}"
        )

        return {
            'display_name': display_name,
            'url': f"https://open.spotify.com/track/{id}",
            'id': id,
            'source': lambda: self.generate_stream(id),
            'embed': lambda: self.generate_info_embed(id)
        }

    async def fetch_id(self, user_input: str) -> dict | None:
        """Fetch the Spotify ID and type either from a URL or search query."""
        if is_url(user_input, ['open.spotify.com']):
            match = re.match(
                r"https?://open\.spotify\.com/(track|album|playlist|artist)/"
                r"(?P<ID>[0-9a-zA-Z]{22})",
                user_input
            )
            return {
                'id': match.group('ID'),
                'type': match.group(1)
            } if match else None
        search = await loop.run_in_executor(
            None,
            lambda: sp.search(q=user_input, limit=1)
        )
        item = (
            search['tracks']['items'][0]
            if search and search['tracks']['items']
            else None
        )
        if not item:
            return None

        track_ratio = token_sort_ratio(
            user_input,
            f"{item['artists'][0]['name']} {item['name']}"
        )
        album_ratio = token_sort_ratio(
            user_input,
            f"{item['album']['artists'][0]['name']} {item['album']['name']}"
        )
        return ({
            'id': item['id'],
            'type': 'track'
        } if track_ratio > album_ratio else {
            'id': item['album']['id'],
            'type': 'album'
        })

    async def get_tracks(self, user_input: str) -> list[dict]:
        """Fetch tracks from a URL or search query."""
        # Pretty dirty ／(^o^)＼
        result = await self.fetch_id(user_input)
        if not result:
            return []

        id, type_ = result['id'], result['type']

        if type_ == 'track':
            track_API = await loop.run_in_executor(
                None,
                lambda: sp.track(id)
            )
            return [self.get_track_info(track_API)]

        elif type_ == 'album':
            album_API = await loop.run_in_executor(
                None,
                lambda: sp.album_tracks(id)
            )
            return [self.get_track_info(track)
                    for track in album_API['items']]

        elif type_ == 'playlist':
            playlist_API = await loop.run_in_executor(
                None,
                lambda: sp.playlist_tracks(id)
            )
            return [self.get_track_info(track['track'])
                    for track in playlist_API['items']]

        elif type_ == 'artist':
            artist_API = await loop.run_in_executor(
                None,
                lambda: sp.artist_top_tracks(id, country=SPOTIFY_TOP_COUNTRY)
            )
            return [self.get_track_info(track)
                    for track in artist_API['tracks']]

        return []

    async def get_cover_data(self, track_id: str) -> dict:
        """Return a dict with the cover URL and its dominant color."""
        cover_url = await loop.run_in_executor(
            None,
            lambda: sp.track(track_id)['album']['images'][0]['url']
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url) as response:
                cover_bytes = await response.read()
                dominant_rgb = get_accent_color(cover_bytes)
        return {'url': cover_url, 'dominant_rgb': dominant_rgb}


if __name__ == '__main__':
    spotify = Spotify_()
