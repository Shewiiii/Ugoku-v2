import os
import asyncio
from typing import Optional, Callable
import logging
from requests import get, Response

import spotipy

from deezer import Deezer
from deemix import generateTrackItem, parseLink
from deemix.utils import getBitrateNumberFromText
from deemix.utils.crypto import generateBlowfishKey, decryptChunk
from deemix.types.Track import Track
from deemix.utils import USER_AGENT_HEADER
from deemix.plugins.spotify import Spotify as Sp_plugin

from config import SPOTIFY_ENABLED
from bot.search import is_url

SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
DEEZER_ARL = os.getenv('DEEZER_ARL')


class DeezerChunkedInputStream:
    def __init__(self, track: Track) -> None:
        self.track: Track = track
        self.buffer: bytes = b''
        self.blowfish_key: bytes = generateBlowfishKey(str(track.id))
        self.headers: dict = {'User-Agent': USER_AGENT_HEADER}
        # Do not change the chunk size
        self.chunk_size = 2048 * 3
        self.finished = False
        self.current_position = 0

    async def get_encrypted_stream(self) -> None:
        self.encrypted_stream: Response = await asyncio.to_thread(
            get,
            self.track.downloadURL,
            headers=self.headers,
            stream=True,
            timeout=10
        )
        self.chunks = self.encrypted_stream.iter_content(self.chunk_size)

    def read(self, size: Optional[int] = None) -> Optional[bytes]:
        if self.finished:
            return
        # If chunk in buffer, return it directly
        if self.current_position < len(self.buffer):
            end_position = self.current_position + self.chunk_size
            data = self.buffer[self.current_position:end_position]
            self.current_position += len(data)
            return data
        # Request a new chunk
        try:
            chunk = next(self.chunks)
            if len(chunk) >= self.chunk_size // 3:
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
            return

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
    def __init__(self, sp: Optional[spotipy.Spotify]) -> None:
        self.dz = None
        self.sp = sp
        self.format = 'FLAC'

    async def init_deezer(self) -> None:
        self.dz = Deezer()
        await asyncio.to_thread(
            self.dz.login_via_arl,
            DEEZER_ARL
        )
        # Create DEEZER_ENABLED variable in config file
        if SPOTIFY_ENABLED:
            self.spotify = Sp_plugin()
            self.spotify.enabled = True
            self.spotify.sp = self.sp
        else:
            self.spotify = None
        logging.info("Deezer has been initialized successfully")

    async def get_link_id(self, url: str) -> Optional[str]:
        # Extract track/link ID from URL
        from_spotify = is_url(url, ['open.spotify.com'])
        parsed_url: Optional[tuple] = (
            self.spotify.parseLink(url) if from_spotify
            else parseLink(url)
        )

        if not parsed_url[2]:
            # Not found!
            return

        if from_spotify:
            if not self.spotify:
                return

            spotify_track_data = await asyncio.to_thread(
                self.spotify.getTrack,
                parsed_url[2]
            )
            if not spotify_track_data:
                return

            link_id = f"isrc:{spotify_track_data['isrc']}"
        else:
            link_id = parsed_url[2]

        return link_id

    async def get_track(self, link_id: str) -> Track:
        # Prepare track object
        download_object = await asyncio.to_thread(
            generateTrackItem,
            self.dz,
            link_id=link_id,
            bitrate=getBitrateNumberFromText(self.format)
        )

        # Acquire track data
        extra_data = download_object.single
        trackAPI = extra_data.get('trackAPI')
        track = await asyncio.to_thread(
            Track().parseData,
            dz=self.dz,
            track_id=extra_data.get('trackAPI')['id'],
            trackAPI=trackAPI
        )
        # Track URL
        track.downloadURL = await asyncio.to_thread(
            self.dz.get_track_url,
            track.trackToken,
            'FLAC'
        )

        return track

    @staticmethod
    async def stream(track: Track) -> DeezerChunkedInputStream:
        stream = DeezerChunkedInputStream(track)
        await stream.get_encrypted_stream()
        return stream
