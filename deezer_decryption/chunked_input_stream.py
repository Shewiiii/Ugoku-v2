import asyncio
from deezer_decryption.constants import HEADERS, CHUNK_SIZE
from deezer_decryption.crypto import generate_blowfish_key, decrypt_chunk
import logging
from typing import Union, Optional
import httpx
import requests


class DeezerChunkedInputStream:
    def __init__(self, track_id: Union[int, str], stream_url: str) -> None:
        self.stream_url: str = stream_url
        self.buffer: bytes = b''
        self.blowfish_key: bytes = generate_blowfish_key(str(track_id))
        self.headers: dict = HEADERS
        self.chunk_size: int = CHUNK_SIZE
        self.current_position: int = 0
        self.session = httpx.AsyncClient()
        self.stream = None
        self.async_stream = None

    async def set_async_chunks(self) -> None:
        """Set chunks in self.async_chunks for download"""
        self.async_stream_ctx = await self.session.stream(
            method='GET',
            url=self.stream_url,
            headers=self.headers,
            timeout=10
        )
        self.async_stream = await self.async_stream_ctx.__aenter__()
        self.async_chunks = self.async_stream.aiter_bytes(self.chunk_size)

    async def set_chunks(self) -> None:
        """Set chunks in self.chunks for ffmpeg pipe"""
        self.stream = await asyncio.to_thread(
            requests.get,
            url=self.stream_url,
            headers=self.headers,
            timeout=10
        )
        self.chunks = await asyncio.to_thread(self.stream.iter_content, self.chunk_size)

    def read(self, size: Optional[int] = None) -> bytes:
        # Chunk in buffer
        if self.current_position < len(self.buffer):
            end_position = self.current_position + self.chunk_size
            data = self.buffer[self.current_position:end_position]
            self.current_position += len(data)
            return data

        # New chunk
        try:
            chunk = next(self.chunks)
        except StopIteration:
            return b''
        except Exception as e:
            logging.error(e)
            return b''

        if len(chunk) >= 2048:
            decrypted_chunk = decrypt_chunk(
                self.blowfish_key,
                chunk[0:2048]
            ) + chunk[2048:]
            self.buffer += decrypted_chunk
            self.current_position += len(decrypted_chunk)
            return decrypted_chunk
        else:
            return chunk

    async def close(self):
        if self.async_stream:
            await self.async_stream_ctx.__aexit__(None, None, None)
        if self.stream:
            await self.stream_ctx.__aexit__(None, None, None)
        self.chunks = None
        del self.buffer
