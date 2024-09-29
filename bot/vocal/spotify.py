import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any, Callable, Awaitable

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
from bot.vocal.types import TrackInfo, SpotifyID, CoverData, SpotifyAlbum, SpotifyTrackAPI, SpotifyAlbumAPI, \
    SpotifyPlaylistAPI, SpotifyArtistAPI
from config import SPOTIFY_TOP_COUNTRY


logger = logging.getLogger(__name__)
logging.getLogger('zeroconf').setLevel(logging.ERROR)


# Spotify Application credentials
class SpotifyConfig:
    def __init__(self) -> None:
        load_dotenv()
        self.client_id = os.getenv('SPOTIPY_CLIENT_ID')
        self.client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
        self.redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI')


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
    """A class to interact with Spotify's API and handle Spotify-related operations.

    This class provides methods to fetch track information, generate streams,
    and create embeds for Spotify tracks, albums, playlists, and artists.

    Attributes:
        sessions: A SpotifySessions object containing Spotify API sessions.

    """
    def __init__(self, sessions: SpotifySessions) -> None:
        """Initializes the Spotify class with SpotifySessions.

        Args:
            sessions: A SpotifySessions object containing Spotify API sessions.
        """
        self.sessions = sessions

    async def generate_info_embed(self, track_id: str) -> discord.Embed:
        """Generates a Discord embed with information about a Spotify track.

        Args:
            track_id: The Spotify ID of the track.

        Returns:
            discord.Embed: An embed containing track information.
        """
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

    async def generate_stream(self, id: str) -> Callable[[], Awaitable[Any]]:
        """Generates a stream for a given Spotify track ID.

        Args:
            id: The Spotify ID of the track.

        Returns:
            Callable[[], Awaitable[Any]]: An async function that returns the audio stream.
        """
        track_id = await asyncio.to_thread(TrackId.from_uri, f"spotify:track:{id}")
        stream = await asyncio.to_thread(
            self.sessions.lp.session.content_feeder().load,
            track_id, VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH),
            False, None
        )
        return stream.input_stream.stream()

    def get_track_info(self, track_API: SpotifyTrackAPI, album_info: Optional[SpotifyAlbum] = None) -> TrackInfo:
        """Extracts and returns track information from Spotify API response.

        Args:
            track_API: The Spotify API response for a track.
            album_info: Optional album information if available.

        Returns:
            dict (TrackInfo): A dictionary containing track information.
        """
        id = track_API['id']
        album = album_info or track_API.get('album', {})

        def get_album_name() -> Optional[str]:
            """
            Extract the album name from the album information.

            This function handles various possible formats of the album name data:
            - If it's a string, it returns the string directly.
            - If it's a dictionary, it attempts to return the 'name' key's value.
            - If it's a list, it attempts to return the first element if it's a string.
            - For any other case, it returns None.

            Returns:
                Optional[str]: The album name if found, or None if not available or not in a recognized format.
            """
            name = album.get('name')
            if isinstance(name, str):
                return name
            elif isinstance(name, dict):
                return str(name.get('name', ''))
            elif isinstance(name, list) and name:
                return str(name[0]) if isinstance(name[0], str) else ''
            return None

        def get_cover_url() -> Optional[str]:
            """
            Extract the cover URL from the album information.

            This function first checks for an 'images' list in the album data.
            If present and containing dictionary items, it returns the 'url' of the first image.
            If not found, it falls back to checking for a 'cover' field in the album data.

            Returns:
                Optional[str]: The URL of the album cover if found, or None if not available.
            """
            images = album.get('images', [])
            if images and isinstance(images[0], dict):
                return images[0].get('url')
            return album.get('cover')

        return {
            'display_name': f"{track_API['artists'][0]['name']} - {track_API['name']}",
            'title': track_API['name'],
            'artist': ', '.join(artist['name'] for artist in track_API['artists']),
            'album': get_album_name(),
            'cover': get_cover_url(),
            'duration': track_API['duration_ms'],
            'url': f"https://open.spotify.com/track/{id}",
            'id': id,
            'source': lambda: self.generate_stream(id),
            'embed': lambda: self.generate_info_embed(id)
        }

    async def fetch_id(self, user_input: str) -> Optional[SpotifyID]:
        """Fetch the Spotify ID and type either from a URL or search query.

        Args:
            user_input: A Spotify URL or search query.

        Returns:
            dict (SpotifyID): A dictionary containing the Spotify ID and type, or None if not found.
        """
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

    async def get_tracks(self, user_input: str) -> List[TrackInfo]:
        """Fetch tracks from a URL or search query.

        This method can handle tracks, albums, playlists, and artists.

        Args:
            user_input: A Spotify URL or search query.

        Returns:
            List[dict]: A list of dictionaries containing track information.
        """
        result = await self.fetch_id(user_input)
        if not result:
            return []

        id, type_ = result['id'], result['type']

        if type_ == 'track':
            track_API: SpotifyTrackAPI = await asyncio.to_thread(self.sessions.sp.track, id)
            return [self.get_track_info(track_API)]
        elif type_ == 'album':
            album_API: SpotifyAlbumAPI = await asyncio.to_thread(self.sessions.sp.album, id)
            album_info = {
                'name': album_API['name'],
                'cover': album_API['images'][0]['url'] if album_API['images'] else None,
                'url': album_API['external_urls']['spotify']
            }
            return [self.get_track_info(track, album_info) for track in album_API['tracks']['items']]
        elif type_ == 'playlist':
            playlist_API: SpotifyPlaylistAPI = await asyncio.to_thread(self.sessions.sp.playlist_tracks, id)
            return [self.get_track_info(track['track']) for track in playlist_API['items']]
        elif type_ == 'artist':
            artist_API: SpotifyArtistAPI = await asyncio.to_thread(self.sessions.sp.artist_top_tracks, id, country=SPOTIFY_TOP_COUNTRY)
            return [self.get_track_info(track) for track in artist_API['tracks']]

        return []

    async def get_cover_data(self, track_id: str) -> CoverData:
        """Fetches cover art data for a Spotify track.

        Args:
            track_id: The Spotify ID of the track.

        Returns:
            dict (CoverData): A dictionary containing the cover URL and dominant RGB color.
        """
        track = await asyncio.to_thread(self.sessions.sp.track, track_id)
        cover_url = track['album']['images'][0]['url']
        dominant_rgb = await get_accent_color_from_url(cover_url)

        return {'url': cover_url, 'dominant_rgb': dominant_rgb}


async def main() -> None:
    """Main function to initialize Spotify sessions and create a Spotify instance."""
    logging.basicConfig(level=logging.INFO)
    sessions = SpotifySessions()
    await sessions.init_spotify()
    spotify = Spotify(sessions)

if __name__ == '__main__':
    asyncio.run(main())
