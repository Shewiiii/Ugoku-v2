from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.audio import AbsChunkedInputStream
from librespot.zeroconf import ZeroconfServer
from dotenv import load_dotenv

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from bot.search import is_url, similar
from config import SPOTIFY_ENABLED
import config

from io import BytesIO
from pathlib import Path
import logging
import time
import os
import re


load_dotenv()
logger = logging.getLogger(__name__)

# Variables
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')

# Init session
# librespot
if SPOTIFY_ENABLED:
    credentials_path = Path('./credentials.json')
    if not credentials_path.exists():
        session = ZeroconfServer.Builder().create()
        logging.warning("Not logged into Spotify. Please log in to Librespot "
                        "from Spotify's official client!")

        while not credentials_path.exists():
            time.sleep(1)

        print("Successfully logged in. You can now use the bot ( ^^) _旦~~"
              "(Restart the bot to get rid of connection aborted errors)")
        session.close_session()

    # Login with the stored credentials file
    session = Session.Builder().stored_file().create()

    # Spotipy
    auth_manager = SpotifyClientCredentials()
    sp = spotipy.Spotify(auth_manager=auth_manager)


class Spotify_:

    async def generate_stream(self, id: str) -> AbsChunkedInputStream:
        '''Get the stream of a track from a single ID.
        '''
        track_id: TrackId = TrackId.from_uri(f"spotify:track:{id}")
        stream = session.content_feeder().load(
            track_id, VorbisOnlyAudioQuality(
                AudioQuality.VERY_HIGH), False, None
        )
        return stream.input_stream.stream()

    async def get_track_name(self, id: str) -> str | None:
        try:
            track_API: dict = sp.track(id)
        except TypeError:
            return

        display_name: str = (
            f"{track_API['artists'][0]['name']} "
            f"- {track_API['name']}"
        )
        return display_name

    def get_id_from_url(self, url: str) -> dict | None:
        track_url_search = re.findall(
            r"^(https?://)?open\.spotify\.com/(track|album|playlist)/(?P<ID>[0-9a-zA-Z]{22})(\?si=.+?)?$",
            string=url
        )
        if not track_url_search:
            return
        id: str = track_url_search[0][2]
        type = track_url_search[0][1]

        if type == 'album' or type == 'playlist':
            is_collection = True
        else:
            is_collection = False

        return {'id': id, 'is_collection': is_collection}

    async def get_id_from_query(self, query: str) -> dict | None:
        search = sp.search(q=query, limit=1)
        if not search:
            return
        items: str = search['tracks']['items']
        if not items:
            return
        item = items[0]

        # Basically searching if the query is an album or song
        track_ratio: float = similar(
            query,
            # E.g: Thaehan Intro
            f"{item['artists'][0]['name']} {item['name']}"
        )
        album_ratio: float = similar(
            query,
            # E.g: Thaehan Two Poles
            f"{item['album']['artists'][0]['name']} {item['album']['name']}"
        )
        if track_ratio > album_ratio:
            id: str = item['id']
            is_collection = False
        else:
            id: str = item['album']['id']
            is_collection = True

        return {'id': id, 'is_collection': is_collection}

    async def get_track_items_from_collection(self, id: str) -> list:
        try:
            return sp.album_tracks(id)['items']
        except spotipy.SpotifyException:
            # It's a playlist
            items = sp.playlist_items(id)['items']
            return [item['track'] for item in items]

    async def get_collection_track_ids(self, id: str) -> list[str]:
        items: list = await self.get_track_items_from_collection(id)
        track_ids = [item['id'] for item in items]
        return track_ids

    async def get_track_urls(self, user_input: str) -> list | None:
        ids = await self.get_track_ids(user_input)
        if not ids:
            return
        return [f'https://open.spotify.com/track/{id}' for id in ids]

    # Ok so basically only that method should be used in the bot..
    async def get_track_ids(self, user_input: str) -> list | None:
        if is_url(user_input, ['open.spotify.com']):
            result: dict = self.get_id_from_url(user_input)
        else:
            result: dict = await self.get_id_from_query(query=user_input)
        if not result:
            return

        if result['is_collection']:
            ids: list = await self.get_collection_track_ids(result['id'])
            return ids

        return [result['id']]

    # ..And that one :elaina_magic:
    async def get_track(self, id: str) -> dict:
        '''Returns an info dictionary containing an audio stream
        '''
        display_name: str = await self.get_track_name(id)

        async def generate_stream_func() -> AbsChunkedInputStream:
            return await self.generate_stream(id)

        info_dict = {
            'display_name': display_name,
            'url': f'https://open.spotify.com/track/{id}',
            'source': generate_stream_func
        }
        return info_dict
