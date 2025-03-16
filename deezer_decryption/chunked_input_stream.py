import discord
import httpx
import http.client
import logging
import requests
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    ReadTimeout,
    ChunkedEncodingError,
)
from time import perf_counter
from typing import Union, Optional, TYPE_CHECKING

from deezer_decryption.constants import HEADERS, CHUNK_SIZE
from deezer_decryption.crypto import generate_blowfish_key, decrypt_chunk

if TYPE_CHECKING:
    from bot.vocal.track_dataclass import Track

async_client = httpx.AsyncClient(http2=True)


class DeezerChunkedInputStream:
    def __init__(
        self,
        deezer_id: Union[str, int],
        stream_url: str,
        track_token: str,
        bot: Optional[discord.Bot] = None,
        track: Optional["Track"] = None,
    ) -> None:
        self.track: "Track" = track
        self.stream_url: str = stream_url
        self.track_token: str = track_token
        self.blowfish_key: bytes = generate_blowfish_key(str(deezer_id))
        self.headers: dict = HEADERS
        self.chunk_size: int = CHUNK_SIZE
        self.current_position: int = 0
        self.stream = None
        self.async_stream = None
        self.chunks = None
        self.bot = bot

    def __repr__(self):
        return f"DeezerChunkedInputStream of {self.track}"

    def create_buffer(self) -> None:
        if not hasattr(self, "buffer"):
            self.buffer = b""

    async def set_async_chunks(self) -> None:
        """Set chunks in self.async_chunks for download."""
        self.async_stream_ctx = async_client.stream(
            method="GET", url=self.stream_url, headers=self.headers, timeout=10
        )
        self.async_stream = await self.async_stream_ctx.__aenter__()
        self.async_chunks = self.async_stream.aiter_bytes(self.chunk_size)

    def set_chunks(
        self, start_position: int = 0, timer_start: Optional[float] = None
    ) -> None:
        """Set chunks (once) in self.chunks for streaming."""
        if self.chunks is not None:
            return

        self.create_buffer()
        headers = self.headers.copy()

        if start_position > 0:
            headers["Range"] = f"bytes={start_position}-"

        self.stream = requests.get(
            url=self.stream_url, headers=headers, timeout=10, stream=True
        )
        self.stream.raise_for_status()
        self.chunks = self.stream.iter_content(self.chunk_size)

        if timer_start:
            logging.info(
                f"Loaded chunks of {self.track} in {(perf_counter() - timer_start):.3f}s"
            )

    def read(self, size: Optional[int] = None) -> bytes:
        # Chunk in buffer
        if self.current_position < len(self.buffer):
            end_position = self.current_position + self.chunk_size
            data = self.buffer[self.current_position : end_position]
            self.current_position += len(data)
            return data

        # New chunk
        try:
            chunk = next(self.chunks)
        except StopIteration:
            # Failed reading the first chunk
            if len(self.buffer) <= CHUNK_SIZE and self.bot:
                logging.error(
                    f"First reading of {self} failed, requesting a new stream URL..."
                )
                new_stream_url = self.bot.deezer.get_stream_url_sync(self.track_token)
                if not new_stream_url:
                    logging.error(f"New stream URL request failed for {self}")
                self.stream_url = new_stream_url
                self.chunks = None
                self.set_chunks()
                return self.read()

            # Finished reading
            logging.info(f"Finished reading stream of {self}, closing")
            self.stream.close()
            return b""
        except (RequestsConnectionError, ReadTimeout, ChunkedEncodingError) as e:
            logging.error(f"{repr(e)}, requesting a new stream...")
            self.chunks = None
            self.set_chunks(start_position=self.current_position)
            return self.read()
        except http.client.IncompleteRead as e:
            chunk = e.partial
        except Exception as e:
            logging.error(repr(e))
            return b""

        if len(chunk) >= 2048:
            decrypted_chunk = (
                decrypt_chunk(self.blowfish_key, chunk[0:2048]) + chunk[2048:]
            )
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
        if hasattr(self, "buffer"):
            del self.buffer
            logging.info(f"Buffer of {self.track} deleted")
        self.chunks = None
