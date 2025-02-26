import asyncio
from deezer_decryption.constants import HEADERS, CHUNK_SIZE
from deezer_decryption.crypto import generate_blowfish_key, decrypt_chunk
import logging
from typing import Union, Optional
import httpx


class Sessions:
    async_client = httpx.AsyncClient(http2=True)
    client = httpx.Client(http2=True)


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

    async def set_async_chunks(self) -> None:
        """Set chunks in self.async_chunks for download."""
        self.async_stream_ctx = Sessions.async_client.stream(
            method='GET',
            url=self.stream_url,
            headers=self.headers,
            timeout=10
        )
        self.async_stream = await self.async_stream_ctx.__aenter__()
        self.async_chunks = self.async_stream.aiter_bytes(self.chunk_size)

    async def set_chunks(self) -> None:
        """Set chunks in self.chunks for streaming."""
        req = Sessions.client.build_request(
            method='GET',
            url=self.stream_url,
            headers=self.headers,
            timeout=10,
        )
        self.stream = await asyncio.to_thread(Sessions.client.send, req, stream=True)
        self.chunks = self.stream.iter_bytes(self.chunk_size)

    def read(self, size: Optional[int] = None, attempt: Optional[int] = None) -> bytes:
        if attempt is None:
            attempt = 1

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
        except httpx.ReadTimeout:
            if attempt == 10:
                logging.error(
                    f"Too much retry for reading stream of {self.track_id}")
                return b''
            logging.error(f"Read stream of {self.track_id} timeout, retrying")
            return self.read(attempt=attempt+1)
        except Exception as e:
            # Peer most likely closed the connection
            logging.error(str(e))

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
            self.stream.close()
        self.chunks = None
        del self.buffer
