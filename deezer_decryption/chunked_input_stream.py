import asyncio
from deezer_decryption.constants import HEADERS, CHUNK_SIZE
from deezer_decryption.crypto import generate_blowfish_key, decrypt_chunk
import logging
from typing import Union, Optional
import httpx
import http.client
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError, ReadTimeout, ChunkedEncodingError


async_client = httpx.AsyncClient(http2=True)


class DeezerChunkedInputStream:
    def __init__(self, track_id: Union[int, str], stream_url: str) -> None:
        self.track_id = track_id
        self.stream_url: str = stream_url
        self.buffer: bytes = b''
        self.blowfish_key: bytes = generate_blowfish_key(str(track_id))
        self.headers: dict = HEADERS
        self.chunk_size: int = CHUNK_SIZE
        self.current_position: int = 0
        self.stream = None
        self.async_stream = None
        self.chunks = None

    async def set_async_chunks(self) -> None:
        """Set chunks in self.async_chunks for download."""
        self.async_stream_ctx = async_client.stream(
            method='GET',
            url=self.stream_url,
            headers=self.headers,
            timeout=10
        )
        self.async_stream = await self.async_stream_ctx.__aenter__()
        self.async_chunks = self.async_stream.aiter_bytes(self.chunk_size)

    def set_chunks(self, start_position: int = 0) -> None:
        """Set chunks (once) in self.chunks for streaming."""
        if self.chunks is not None:
            return

        headers = self.headers.copy()
        if start_position > 0:
            headers['Range'] = f'bytes={start_position}-'

        self.stream = requests.get(
            url=self.stream_url,
            headers=headers,
            timeout=10,
            stream=True
        )
        self.chunks = self.stream.iter_content(self.chunk_size)

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
            logging.info(
                f"Finished reading stream of {self.track_id}, closing")
            self.stream.close()
            return b''
        except (RequestsConnectionError, ReadTimeout, ChunkedEncodingError) as e:
            logging.error(f"{str(e)}, requesting a new stream...")
            self.chunks = None
            self.set_chunks(start_position=self.current_position)
            return self.read()
        except http.client.IncompleteRead as e:
            chunk = e.partial
        except Exception as e:
            logging.error(str(e))
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
            self.current_position += len(chunk)
            return chunk

    async def close(self):
        if self.async_stream:
            await self.async_stream_ctx.__aexit__(None, None, None)
        if self.stream:
            self.stream.close()
        self.chunks = None
        del self.buffer
