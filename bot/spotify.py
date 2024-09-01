from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.zeroconf import ZeroconfServer
from dotenv import load_dotenv

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from bot.search import is_url, token_sort_ratio
from bot.utils import get_accent_color
from config import SPOTIFY_ENABLED, SPOTIFY_TOP_COUNTRY

from typing import Dict, List, Optional
from pathlib import Path
import discord
import logging
import aiohttp
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
    async def generate_info_embed(self, track_id: str) -> discord.Embed:
        """Generates a Discord Embed with track information."""
        track_API = sp.track(track_id)
        track_name = track_API['name']
        track_url = f"https://open.spotify.com/track/{track_API['id']}"
        artist_string = ', '.join(
            f"[{artist['name']}]({artist['external_urls']['spotify']})" for artist in track_API['artists']
        )

        album = track_API['album']
        album_name = album['name']
        album_url = album['external_urls']['spotify']
        cover_url = album['images'][0]['url']

        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url) as response:
                cover_bytes = await response.read()
                dominant_rgb = get_accent_color(cover_bytes)

        embed = discord.Embed(
            title=track_name,
            url=track_url,
            description=f"By {artist_string}",
            color=discord.Colour.from_rgb(*dominant_rgb)
        )
        embed.add_field(
            name="Part of the album",
            value=f"[{album_name}]({album_url})",
            inline=True
        )
        embed.set_author(name="Now playing")
        embed.set_thumbnail(url=cover_url)

        return embed

    async def generate_stream(self, id: str):
        """Generates a stream for a given track ID."""
        track_id = TrackId.from_uri(f"spotify:track:{id}")
        stream = session.content_feeder().load(
            track_id, VorbisOnlyAudioQuality(
                AudioQuality.VERY_HIGH), False, None
        )
        return stream.input_stream.stream()

    def get_display_name(self, track_API: dict) -> Optional[str]:
        """Returns a formatted display name for the track."""
        if not track_API:
            return None
        return f"{track_API['artists'][0]['name']} - {track_API['name']}"

    def get_id_from_url(self, url: str) -> Optional[Dict[str, str]]:
        """Extracts the Spotify ID and type from a URL."""
        match = re.match(
            r"https?://open\.spotify\.com/(track|album|playlist|artist)/(?P<ID>[0-9a-zA-Z]{22})",
            url
        )
        if match:
            return {'id': match.group('ID'), 'type': match.group(1)}
        return None

    async def get_id_from_query(self, query: str) -> Optional[Dict[str, str]]:
        """Searches for a track or album by query and returns its ID and type."""
        search = sp.search(q=query, limit=1)
        if not search or not search['tracks']['items']:
            return None
        item = search['tracks']['items'][0]

        # Search is the query is a song or an album
        track_ratio = token_sort_ratio(
            query, f"{item['artists'][0]['name']} {item['name']}")
        album_ratio = token_sort_ratio(
            query, f"{item['album']['artists'][0]['name']} {item['album']['name']}")

        if track_ratio > album_ratio:
            return {'id': item['id'], 'type': 'track'}
        else:
            return {'id': item['album']['id'], 'type': 'album'}

    def get_track_info(self, track_API: dict) -> dict:
        """Returns an info dictionary containing display name, URL, stream generator, and embed generator."""
        id = track_API['id']
        display_name = self.get_display_name(track_API)

        async def generate_stream_func():
            return await self.generate_stream(id)

        async def generate_info_embed_func():
            return await self.generate_info_embed(id)

        return {
            'display_name': display_name,
            'url': f"https://open.spotify.com/track/{id}",
            'id': id,
            'source': generate_stream_func,
            'embed': generate_info_embed_func
        }

    # Only that method should be used in the bot :elaina_magic:
    async def get_tracks(self, user_input: str) -> List[dict]:
        """Returns a list of track info dictionaries based on the user input (URL or search query)."""
        if is_url(user_input, ['open.spotify.com']):
            result = self.get_id_from_url(user_input)
        else:
            result = await self.get_id_from_query(user_input)

        if not result:
            return []

        type_ = result['type']
        id = result['id']
        tracks_info = []

        if type_ == 'track':
            track_API = sp.track(id)
            tracks_info.append(self.get_track_info(track_API))
        elif type_ == 'album':
            album_API = sp.album_tracks(id)
            tracks_info.extend(self.get_track_info(track)
                               for track in album_API['items'])
        elif type_ == 'playlist':
            playlist_API = sp.playlist_tracks(id)
            tracks_info.extend(self.get_track_info(
                track['track']) for track in playlist_API['items'])
        elif type_ == 'artist':
            artist_API = sp.artist_top_tracks(id, country=SPOTIFY_TOP_COUNTRY)
            tracks_info.extend(self.get_track_info(
                track) for track in artist_API['tracks'])

        return tracks_info

    async def get_cover_data(self, track_id: str) -> dict:
        track_API = sp.track(track_id)
        album = track_API['album']
        cover_url = album['images'][0]['url']

        # Get the dominant colors
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url) as response:
                cover_bytes = await response.read()
                dominant_rgb = get_accent_color(cover_bytes)

        return {'url': cover_url, 'dominant_rgb': dominant_rgb}


if __name__ == '__main__':
    spotify = Spotify_()
