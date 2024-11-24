import os
import asyncio
from typing import Optional
import logging
from requests import get, Response
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from spotipy import Spotify, SpotifyClientCredentials
from deezer import Deezer
from deemix import parseLink
from deemix.utils.crypto import generateBlowfishKey, decryptChunk
from deemix.decryption import streamTrack
from deemix.types.Track import Track
from deemix.utils import USER_AGENT_HEADER
from deemix.plugins.spotify import Spotify as Spplugin

from config import SPOTIFY_API_ENABLED
from bot.search import is_url
from bot.utils import get_cache_path

SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
DEEZER_ARL = os.getenv('DEEZER_ARL')


class DeezerChunkedInputStream:
    """track: {'track_id': int, 'stream_url': str}"""

    def __init__(self, track: dict) -> None:
        self.id: int = track['track_id']
        self.stream_url = track['stream_url']
        self.buffer: bytes = b''
        self.blowfish_key: bytes = generateBlowfishKey(str(self.id))
        self.headers: dict = {'User-Agent': USER_AGENT_HEADER}
        # Do not change the chunk size
        self.chunk_size = 2048 * 3
        self.finished = False
        self.current_position = 0

    def get_encrypted_stream(self) -> None:
        self.encrypted_stream: Response = get(
            self.stream_url,
            headers=self.headers,
            stream=True,
            timeout=10
        )
        self.chunks = self.encrypted_stream.iter_content(self.chunk_size)

    def read(self, size: Optional[int] = None) -> bytes:
        if self.finished:
            return b''
        # If chunk in buffer, return it directly
        if self.current_position < len(self.buffer):
            end_position = self.current_position + self.chunk_size
            data = self.buffer[self.current_position:end_position]
            self.current_position += len(data)
            return data
        # Request a new chunk
        try:
            chunk = next(self.chunks)
            if len(chunk) >= 2048:
                decrypted_chunk = decryptChunk(
                    self.blowfish_key,
                    chunk[0:2048]
                ) + chunk[2048:]
                # Add to buffer
                self.buffer += decrypted_chunk
                self.current_position += len(decrypted_chunk)
                return decrypted_chunk
            else:
                self.finished = True
        except StopIteration:
            self.finished = True
            return b''

    def seek(self, position: int) -> None:
        if position < 0:
            position = 0
        if position <= len(self.buffer):
            # If the position is within the already-buffered data
            self.current_position = position
        else:
            # If the position is beyond buffered data, fetch chunks until reaching it
            while len(self.buffer) < position and not self.finished:
                try:
                    chunk = next(self.chunks)
                    decrypted_chunk = decryptChunk(
                        self.blowfish_key, chunk[0:2048]) + chunk[2048:]
                    self.buffer += decrypted_chunk
                except StopIteration:
                    self.finished = True
                    break
            self.current_position = min(position, len(self.buffer))


class Deezer_:
    def __init__(self) -> None:
        self.dz = None
        self.sp = Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET
        ))
        self.format = 'FLAC'

    async def init_deezer(self) -> None:
        assert SPOTIFY_API_ENABLED, "Spotify API is requred."
        self.dz = Deezer()
        await asyncio.to_thread(
            self.dz.login_via_arl,
            DEEZER_ARL
        )
        # Create DEEZER_ENABLED variable in config file
        if SPOTIFY_API_ENABLED:
            self.spotify = Spplugin()
            self.spotify.enabled = True
            self.spotify.sp = self.sp

        logging.info("Deezer has been initialized successfully")

    async def get_link_id(self, url: str) -> Optional[str]:
        from_spotify = is_url(url, ['open.spotify.com'])
        parse_func = self.spotify.parseLink if from_spotify else parseLink
        parsed_url = parse_func(url)

        if not parsed_url or not parsed_url[2]:
            return None

        if from_spotify:
            if not self.spotify:
                return None
            spotify_track_data = await asyncio.to_thread(
                self.spotify.getTrack,
                parsed_url[2]
            )
            return f"isrc:{spotify_track_data['isrc']}" if spotify_track_data else None

        return parsed_url[2]

    async def get_stream_url(self, url: str) -> Optional[dict]:
        link_id = await self.get_link_id(url)
        if not link_id:
            return

        # Prepare track object
        if link_id.startswith("isrc"):
            # Spotify
            track_api = self.dz.api.get_track(link_id)
            track_token = track_api['track_token']
            id = track_api['id']
        else:
            # Deezer
            track_api = self.dz.gw.get_track_with_fallback(link_id)
            track_token = track_api['TRACK_TOKEN']
            id = int(track_api['SNG_ID'])

        # Track URL
        stream_url = await asyncio.to_thread(
            self.dz.get_track_url,
            track_token,
            'FLAC'
        )

        results = {
            'stream_url': stream_url,
            'track_id': id
        }

        return results

    async def get_stream_url_from_query(self, query: str) -> Optional[dict]:
        """Get a track stream URL from a query (text or URL)"""
        # gekiyaba Spotify or Deezer url
        if is_url(query, ['open.spotify.com', ' deezer.com']):
            results = await self.get_stream_url(query)
            return results

        # normal query
        search_data = await asyncio.to_thread(
            self.dz.gw.search,
            query
        )
        if not search_data['TRACK']['data']:
            # Not found!
            return

        track_api = search_data['TRACK']['data'][0]
        track_token = track_api['TRACK_TOKEN']
        id = int(track_api['SNG_ID'])

        # Track URL
        stream_url = await asyncio.to_thread(
            self.dz.get_track_url,
            track_token,
            'FLAC'
        )

        results = {
            'stream_url': stream_url,
            'track_id': id
        }

        return results

    @staticmethod
    def stream(track: dict) -> DeezerChunkedInputStream:
        stream = DeezerChunkedInputStream(track)
        stream.get_encrypted_stream()
        return stream

    @staticmethod
    def download(track: dict) -> Optional[Path]:
        """Download a track from Deezer from a track dict.
        Params: 
            track (dict): Dict containint the "stream_url" and "track_id"

        Returns:
            Path: The path to the cache file
        """
        # Setup the download
        cis = DeezerChunkedInputStream(track)
        cis.get_encrypted_stream()
        file_path = get_cache_path(str(track['track_id']).encode('utf-8'))
        chunks = cis.encrypted_stream.iter_content(2048 * 3)

        # Write the content to file cache
        with open(file_path, 'wb') as file:
            while True: 
                try:
                    chunk = next(chunks)
                except StopIteration:
                    # Done
                    break
                if len(chunk) >= 2048:
                    decrypted = decryptChunk(cis.blowfish_key, chunk[:2048])
                    chunk = decrypted + chunk[2048:]
                file.write(chunk)
        logging.info(f"Track {track['track_id']} downloaded successfully")
        return file_path
