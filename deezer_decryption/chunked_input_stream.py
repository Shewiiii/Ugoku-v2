import asyncio
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
import struct
from time import time
from typing import Union, Optional, TYPE_CHECKING

from deezer_decryption.constants import HEADERS, CHUNK_SIZE
from deezer_decryption.crypto import generate_blowfish_key, decrypt_chunk

if TYPE_CHECKING:
    from bot.vocal.track_dataclass import Timer

async_client = httpx.AsyncClient(http2=True)


class DeezerChunkedInputStream:
    def __init__(
        self,
        deezer_id: Union[str, int],
        stream_url: str,
        track_token: str,
        bot: Optional[discord.Bot] = None,
        display_name: Optional[str] = None,
        timer: Optional["Timer"] = None,
    ) -> None:
        self.display_name = display_name
        self.timer = timer
        self.stream_url: str = stream_url
        self.track_token: str = track_token
        self.blowfish_key: bytes = generate_blowfish_key(str(deezer_id))
        self.headers: dict = HEADERS
        self.chunk_size: int = CHUNK_SIZE
        self.current_position: int = 0
        self.stream = None
        self.async_stream = None
        self.chunks = None
        self.async_chunks = None
        self.seek_table = {}  # Second: byte
        self.seek_start = -1
        self.bot = bot
        self.header_cache: bytes = b""

    def __repr__(self):
        return f"DeezerChunkedInputStream of {self.display_name}"

    def reset_status(self) -> None:
        self.seek_start = -1
        self.current_position = 0
        self.chunks = None
        if self.stream:
            self.stream.close()
            self.stream = None

    async def set_async_chunks(self) -> None:
        """Set chunks in self.async_chunks for download."""
        self.async_stream_ctx = async_client.stream(
            method="GET", url=self.stream_url, headers=self.headers, timeout=10
        )
        self.async_stream = await self.async_stream_ctx.__aenter__()
        self.async_chunks = self.async_stream.aiter_bytes(self.chunk_size)

    def set_chunks(
        self, start_position: Optional[int] = None, force: bool = False
    ) -> None:
        """Set chunks in self.chunks for streaming.
        start_position is the position in the stream in bytes."""
        # If not seeking
        if self.seek_start == -1:
            # If chunks have already been loaded
            if not force and self.chunks is not None:
                return

            # Else, check if there is already a stream, but it should not be the case
            elif self.stream is not None:
                self.reset_status()

        if start_position is None:
            start_position = self.current_position

        if start_position > 0:
            headers = self.headers.copy()
            headers["Range"] = f"bytes={start_position}-"
        else:
            headers = self.headers

        self.stream = requests.get(
            url=self.stream_url, headers=headers, timeout=10, stream=True
        )
        self.stream.raise_for_status()
        self.chunks = self.stream.iter_content(self.chunk_size)

    def set_stream_headers(self, first_bytes: bytes) -> None:
        if first_bytes[:4] != b"fLaC":
            raise ValueError("Invalid FLAC file: Missing 'fLaC' marker")

        offset = 4  # Skip the flaC marker
        last_header_offset = 4

        while offset + 4 <= len(first_bytes):
            block_header = first_bytes[offset]
            block_length = int.from_bytes(
                first_bytes[offset + 1 : offset + 4], byteorder="big"
            )
            total_block_size = (
                4 + block_length
            )  # 4 bytes for the header plus the block's content
            block_type = block_header & 0x7F  # Lower 7 bits determine the block type
            block_data = first_bytes[offset + 4 : offset + 4 + block_length]

            # Type 3 is the seektable
            if block_type == 3:
                for i in range(0, block_length, 18):  # One entry is 18 bytes
                    entry_data = block_data[i : i + 18]
                    if len(entry_data) < 18:
                        break
                    # two 8-byte big‑endian integers and one 2‑byte unsigned short
                    sample_number, stream_offset, _ = struct.unpack(">QQH", entry_data)
                    self.seek_table[sample_number // 44100] = stream_offset

            offset += total_block_size
            last_header_offset = offset - 1

            # If the block's MSB is 1, this is the last metadata block !
            if block_header & 0x80:
                break

        self.header_cache = first_bytes[: last_header_offset + 1]

    def seek(self, second: int) -> None:
        """Seek in the track based on the seek table."""
        if not self.seek_table:
            raise ValueError(
                f"Trying to seek with an empty seek table in {self.display_name}"
            )

        # Find the appropriate anchor
        nearest_anchor = max([key for key in self.seek_table.keys() if key <= second])
        aligned_position = (self.seek_table[nearest_anchor] // CHUNK_SIZE) * CHUNK_SIZE
        self.seek_start = self.current_position = aligned_position

        # Timer
        self.timer._start_time = time()
        self.timer._elapsed_time_accumulator = nearest_anchor

    def read(self, size: Optional[int] = None) -> bytes:
        try:
            chunk = next(self.chunks)

        except StopIteration:
            # Failed reading the first chunk
            if self.current_position <= CHUNK_SIZE and self.bot:
                logging.error(
                    f"Reading of {self} failed, requesting a new stream URL..."
                )
                new_stream_url = self.bot.deezer.get_stream_url_sync(self.track_token)
                if not new_stream_url:
                    logging.error(f"New stream URL request failed for {self}")
                self.stream_url = new_stream_url
                self.set_chunks(force=True)
                return self.read()

            # Finished reading
            logging.info(f"Finished reading stream of {self}, closing")
            self.reset_status()
            return b""

        except (RequestsConnectionError, ReadTimeout, ChunkedEncodingError) as e:
            logging.error(f"{repr(e)}, requesting a new stream...")
            self.chunks = None
            self.set_chunks(self.current_position)
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
            # Set the seek table at first reading
            if self.current_position == 0 and not self.header_cache:
                self.set_stream_headers(decrypted_chunk)

            # After seeking: prepend cached header
            if self.current_position == self.seek_start and self.header_cache:
                decrypted_chunk = self.header_cache + decrypted_chunk
                self.current_position += len(self.header_cache)
                self.seek_start = -1  # Not seeking anymore

            self.current_position += len(decrypted_chunk)
            return decrypted_chunk
        else:
            self.current_position += len(chunk)
            return chunk

    async def close_streams(self):
        if self.async_stream:
            try:
                await self.async_stream_ctx.__aexit__(None, None, None)
            except Exception as e:
                logging.error(repr(e))
            finally:
                self.async_stream = None
                self.async_stream_ctx = None

        if self.stream:
            try:
                await asyncio.to_thread(self.stream.close)
            except Exception as e:
                logging.error(repr(e))
            finally:
                self.stream = None

        self.reset_status()

    async def close(self) -> None:
        logging.info(f"Closing {self}")
        await self.close_streams()
        self.seek_table.clear()
        self.timer = None
        self.__dict__.clear()
