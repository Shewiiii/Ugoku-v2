import os
import aiofiles
import asyncio
from typing import Optional
import logging
import requests
from pathlib import Path
import httpx

from spotipy import Spotify, SpotifyClientCredentials
from deezer import Deezer
from deezer.errors import DataException, DeezerError
from deemix import parseLink
from deemix.decryption import generateCryptedStreamURL
from deemix.utils.crypto import generateBlowfishKey, decryptChunk
from deemix.utils import USER_AGENT_HEADER
from deemix.plugins.spotify import Spotify as Spplugin

from config import SPOTIFY_API_ENABLED
from bot.search import is_url
from bot.utils import get_cache_path
from bot.search import get_closest_string


SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
DEEZER_ARL = os.getenv('DEEZER_ARL')


class DeezerChunkedInputStream:
    """track: {'id': int, 'stream_url': str}"""

    def __init__(self, track: dict) -> None:
        self.id: int = track['id']
        self.stream_url = track['stream_url']
        self.buffer: bytes = b''
        self.blowfish_key: bytes = generateBlowfishKey(str(self.id))
        self.headers: dict = {'User-Agent': USER_AGENT_HEADER}
        # Do not change the chunk size
        self.chunk_size = 2048 * 3
        self.finished = False
        self.current_position = 0

    def get_encrypted_stream(self) -> None:
        if not self.stream_url:
            raise DataException
        self.encrypted_stream: requests.Response = requests.get(
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
                return b''
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

    def close(self):
        """Close the stream and mark as finished."""
        self.finished = True
        if self.encrypted_stream:
            self.encrypted_stream.close()
        self.chunks = None
        del self.buffer


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
        if not self.dz.current_user.get('can_stream_lossless'):
            logging.warning(
                "You are not using a Deezer Premium account. "
                "Deezer related features will not work."
            )
        # Create DEEZER_ENABLED variable in config file
        if SPOTIFY_API_ENABLED:
            self.spotify = Spplugin()
            self.spotify.enabled = True
            self.spotify.sp = self.sp

        logging.info("Deezer has been initialized successfully")

    async def get_native_track_api(self, url: str) -> Optional[dict]:
        from_spotify = is_url(url, ['open.spotify.com'])
        parse_func = self.spotify.parseLink if from_spotify else parseLink
        parsed_url = parse_func(url)
        # No id found in the given URL
        if not parsed_url or not parsed_url[2]:
            return
        # Spotify URL without Spotify API enabled
        if from_spotify and not self.spotify:
            return
        spotify_track_data = await asyncio.to_thread(self.spotify.getTrack, parsed_url[2])
        # Track not found
        if not spotify_track_data:
            return
        track_api = await asyncio.to_thread(self.dz.api.get_track_by_ISRC, spotify_track_data['isrc'])
        return track_api

    async def get_track(
        self,
        url: Optional[str] = None,
        id_: Optional[str] = None
    ) -> Optional[dict]:
        try:
            if url:
                native_track_api = await self.get_native_track_api(url)
            else:
                native_track_api = await asyncio.to_thread(self.dz.api.get_track, id_)
        except DataException:
            # Not found
            return
        link_id = native_track_api.get('id')
        if not link_id or link_id == '0':
            return
        # Prepare track object
        gw_track_api = await asyncio.to_thread(self.dz.gw.get_track_with_fallback, link_id)
        results = await self.prepare_track_object(gw_track_api, native_track_api)
        return results

    async def get_track_from_query(self, query: str) -> Optional[dict]:
        """Get a track stream URL from a query (text or URL)"""
        # gekiyaba Spotify or Deezer url
        if is_url(query, ['open.spotify.com', ' deezer.com', 'deezer.page.link']):
            results = await self.get_track(url=query)
            if not results:
                raise DataException
            return results

        # normal query
        search_data = await asyncio.to_thread(self.dz.gw.search, query)
        if not search_data['TRACK']['data']:
            raise DataException

        # Get data from gw api
        songs = [f"{track['ART_NAME']} {track['SNG_TITLE']}"
                 for track in search_data['TRACK']['data']]
        i = get_closest_string(query, songs)

        # Api wrapping
        gw_track_api: dict = search_data['TRACK']['data'][i]
        native_track_api = self.dz.api.get_track(gw_track_api.get('SNG_ID', 0))
        results = await self.prepare_track_object(gw_track_api, native_track_api)
        return results

    async def get_stream_url_fallback(self, gw_track_api: dict) -> str:
        id_ = int(gw_track_api['SNG_ID'])
        stream_url = generateCryptedStreamURL(
            sng_id=id_,
            md5=gw_track_api['MD5_ORIGIN'],
            media_version=gw_track_api['MEDIA_VERSION'],
            media_format=9
        )
        async with httpx.AsyncClient(follow_redirects=True) as session:
            request = await session.head(
                stream_url,
                headers={'User-Agent': USER_AGENT_HEADER},
                timeout=5
            )
            request.raise_for_status()
        logging.info(f"Crypted stream url generated successfully: {id_}")
        return stream_url

    async def prepare_track_object(
        self,
        gw_track_api: dict,
        native_track_api: dict
    ) -> Optional[None]:
        id_ = int(gw_track_api['SNG_ID'])
        artist = gw_track_api['ART_NAME']
        artists = ', '.join(
            [artist]+gw_track_api['SNG_CONTRIBUTORS'].get('main_artist', []))

        # Track URL
        try:
            stream_url = await asyncio.to_thread(self.dz.get_track_url, gw_track_api['TRACK_TOKEN'], 'FLAC')
        except DeezerError as e:
            logging.error(
                f"Error when generating a stream URL for {id_}: {e}. "
                "Running the fallback method..."
            )
            try:
                stream_url = await self.get_stream_url_fallback(gw_track_api)
            except httpx.HTTPStatusError as e:
                logging.error(
                    f"Error when generating a crypted stream URL for {id_}: {e}")
                return

        results = {
            'stream_url': stream_url,
            'id': id_,
            'title': gw_track_api['SNG_TITLE'],
            'artist': artist,
            'artists': artists,
            'album': gw_track_api['ALB_TITLE'],
            'cover': f"https://cdn-images.dzcdn.net/images/cover/{gw_track_api['ALB_PICTURE']}/1000x1000-000000-80-0-0.jpg",
            'date': native_track_api.get('release_date', ''),
            'disc_number': native_track_api.get('disc_number', 1),
            'track_number': native_track_api.get('track_position', 1)
        }
        return results

    @staticmethod
    def stream(track: dict) -> DeezerChunkedInputStream:
        stream = DeezerChunkedInputStream(track)
        stream.get_encrypted_stream()
        return stream

    @staticmethod
    async def download(track: dict) -> Path:
        """Download a track from Deezer from a track dict."""
        cis = await asyncio.to_thread(DeezerChunkedInputStream, track)
        await asyncio.to_thread(cis.get_encrypted_stream)

        file_path = get_cache_path(str(track['id']).encode('utf-8'))

        if file_path.is_file():
            logging.info(f"Already cached: {track['id']}")
            return file_path

        async with aiofiles.open(file_path, 'wb') as file:
            while True:
                chunk = await asyncio.to_thread(
                    next,
                    cis.encrypted_stream.iter_content(2048 * 3),
                    None
                )

                if chunk is None:
                    # No more chunks to process
                    break

                if len(chunk) >= 2048:
                    # Offload decryption to a thread
                    decrypted = await asyncio.to_thread(
                        decryptChunk,
                        cis.blowfish_key,
                        chunk[:2048]
                    )
                    chunk = decrypted + chunk[2048:]

                # Write the chunk asynchronously
                await file.write(chunk)

        logging.info(f"Downloaded successfully: {track['id']}")
        return file_path
