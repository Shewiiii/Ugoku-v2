import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

import discord
import spotipy
from dotenv import load_dotenv
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.zeroconf import ZeroconfServer
from spotipy.oauth2 import SpotifyClientCredentials

from bot.search import is_url, token_sort_ratio
from bot.utils import get_accent_color_from_url
from config import SPOTIFY_TOP_COUNTRY


logger = logging.getLogger(__name__)
logging.getLogger('zeroconf').setLevel(logging.ERROR)


# Spotify Application credentials
class SpotifyConfig:
    def __init__(self):
        load_dotenv()
        self.client_id = os.getenv('SPOTIPY_CLIENT_ID')
        self.client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
        self.redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI')


# Initialize Librespot and Spotipy sessions
class SpotifySessions:
    def __init__(self):
        self.config = SpotifyConfig()
        self.lp: Optional[Librespot] = None
        self.sp: Optional[spotipy.Spotify] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def init_spotify(self):
        try:
            self.loop = asyncio.get_running_loop()
            self.lp = Librespot()
            await self.lp.create_session()
            self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=self.config.client_id,
                client_secret=self.config.client_secret
            ))
            logger.info("Spotify sessions initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Spotify sessions: {str(e)}")
            raise


class Librespot:
    def __init__(self) -> None:
        self.updated: Optional[datetime] = None
        self.session: Optional[Session] = None

    async def create_session(
        self,
        path: Path = Path('./credentials.json')
    ) -> None:
        """Wait for credentials and generate a json file if needed."""
        if not path.exists():
            logging.error(
                "Please log in to Librespot from Spotify's official client! "
                "Any command using Spotify features will not work."
            )
            session = await asyncio.to_thread(ZeroconfServer.Builder().create)
            while not path.exists():
                await asyncio.sleep(1)
            logging.info(
                'Credentials saved Successfully, closing Zeroconf session. '
                'You can now close Spotify. ( ^^) _旦~~'
            )
            session.close_session()

        await self.generate_session()

    async def generate_session(self) -> None:
        loop = asyncio.get_running_loop()
        if self.session:
            return
        self.session = await loop.run_in_executor(
            None,
            lambda: Session.Builder().stored_file().create()
        )
        self.updated = datetime.now()
        logging.info('Librespot session created!')


class Spotify:
    def __init__(self, sessions: SpotifySessions):
        self.sessions = sessions

    async def generate_info_embed(self, track_id: str) -> discord.Embed:
        track_API = await asyncio.to_thread(self.sessions.sp.track, track_id)

        # Grab all the data needed
        track_name = track_API['name']
        album = track_API['album']
        cover_url = album['images'][0]['url']
        track_url = f"https://open.spotify.com/track/{track_API['id']}"
        album_url = album['external_urls']['spotify']
        dominant_rgb = await get_accent_color_from_url(cover_url)

        # Create the artist string for the embed
        artist_string = ', '.join(
            f"[{artist['name']}]({artist['external_urls']['spotify']})"
            for artist in track_API['artists']
        )

        # Create the embed
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
        track_id = await asyncio.to_thread(
            TrackId.from_uri,
            f"spotify:track:{id}"
        )
        stream = await asyncio.to_thread(
            self.sessions.lp.session.content_feeder().load,
            track_id, VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH),
            False, None
        )
        return stream.input_stream.stream()

    def get_track_info(self, track_API: dict) -> dict:
        """Returns track info (display name, stream, embed)."""
        id = track_API['id']
        display_name = (
            f"{track_API['artists'][0]['name']} - {track_API['name']}"
        )

        return {
            'display_name': display_name,
            'title': track_API['name'],
            'artist': ', '.join(artist['name'] for artist in track_API['artists']),
            # The following can't work with an album api:
            # 'album': track_API['album']['name'],
            # 'cover': track_API['album']['images'][0]['url'],
            'duration': track_API['duration_ms'],
            'url': f"https://open.spotify.com/track/{id}",
            'id': id,
            'source': lambda: self.generate_stream(id),
            'embed': lambda: self.generate_info_embed(id)
        }

    async def fetch_id(self, user_input: str) -> Optional[Dict[str, str]]:
        """Fetch the Spotify ID and type either from a URL or search query."""
        if is_url(user_input, ['open.spotify.com']):
            match = re.match(
                r"https?://open\.spotify\.com/(?:(?:intl-[a-z]{2})/)?(track|album|playlist|artist)/(?P<ID>[0-9a-zA-Z]{22})",
                user_input,
                re.IGNORECASE
            )
            return {'id': match.group('ID'), 'type': match.group(1)} if match else None

        search = await asyncio.to_thread(self.sessions.sp.search, q=user_input, limit=1)
        if not search or not search['tracks']['items']:
            return None

        item = search['tracks']['items'][0]
        track_ratio = token_sort_ratio(
            user_input,
            f"{item['artists'][0]['name']} {item['name']}"
        )
        album_ratio = token_sort_ratio(
            user_input,
            f"{item['album']['artists'][0]['name']} {item['album']['name']}"
        )

        return {
            'id': item['id'] if track_ratio > album_ratio else item['album']['id'],
            'type': 'track' if track_ratio > album_ratio else 'album'
        }

    async def get_tracks(self, user_input: str) -> List[Dict]:
        """Fetch tracks from a URL or search query."""
        result = await self.fetch_id(user_input)
        if not result:
            return []

        id, type_ = result['id'], result['type']

        if type_ == 'track':
            track_API = await asyncio.to_thread(self.sessions.sp.track, id)
            return [self.get_track_info(track_API)]
        elif type_ == 'album':
            album_API = await asyncio.to_thread(self.sessions.sp.album_tracks, id)
            return [self.get_track_info(track) for track in album_API['items']]
        elif type_ == 'playlist':
            playlist_API = await asyncio.to_thread(self.sessions.sp.playlist_tracks, id)
            return [self.get_track_info(track['track']) for track in playlist_API['items']]
        elif type_ == 'artist':
            artist_API = await asyncio.to_thread(self.sessions.sp.artist_top_tracks, id, country=SPOTIFY_TOP_COUNTRY)
            return [self.get_track_info(track) for track in artist_API['tracks']]

        return []

    async def get_cover_data(self, track_id: str) -> Dict[str, any]:
        track = await asyncio.to_thread(self.sessions.sp.track, track_id)
        cover_url = track['album']['images'][0]['url']
        dominant_rgb = await get_accent_color_from_url(cover_url)

        return {'url': cover_url, 'dominant_rgb': dominant_rgb}


async def main():
    logging.basicConfig(level=logging.INFO)
    sessions = SpotifySessions()
    await sessions.init_spotify()
    spotify = Spotify(sessions)

if __name__ == '__main__':
    asyncio.run(main())
