from aiohttp_client_cache import CachedSession, SQLiteBackend
import aiofiles
import asyncio
from deezer_decryption.api import Deezer
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from deezer_decryption.crypto import decrypt_chunk
import discord
import logging
from deezer_decryption.search import get_closest_string
from mutagen.flac import FLAC
from mutagen.flac import Picture
from pathlib import Path
from typing import Literal, Optional

from bot.utils import get_cache_path
from config import CACHE_EXPIRY


class Download:
    def __init__(
        self, deezer: Optional[Deezer] = None, bot: Optional[discord.Bot] = None
    ):
        if deezer is None:
            deezer = Deezer()
        self.api = deezer
        self.bot = bot

    async def tracks(
        self,
        gw_track_apis: list[dict],
        tracks_format: Literal["MP3_128", "MP3_320", "FLAC"] = "FLAC",
        tag: bool = True,
    ) -> list[Path]:
        stream_urls = await self.api.get_stream_urls(
            [track["TRACK_TOKEN"] for track in gw_track_apis], tracks_format
        )
        paths = []

        for i in range(len(stream_urls)):
            if stream_urls[i] is None:
                paths.append(None)
                continue

            api = gw_track_apis[i]
            track_id = api["SNG_ID"]
            cache_id = f"deezer{track_id}"
            file_path = get_cache_path(cache_id)
            paths.append(file_path)
            if file_path.is_file():
                continue

            stream = DeezerChunkedInputStream(
                track_id,
                stream_urls[i],
                gw_track_apis[i]["TRACK_TOKEN"],
                deezer=self.api,
            )

            # Retry 10 times get stream data
            for attempt in range(10):
                await stream.set_async_chunks()
                wrote_chunk = False
                async with aiofiles.open(file_path, "wb") as file:
                    async for chunk in stream.async_chunks:
                        if chunk is None:
                            break
                        if len(chunk) >= 2048:
                            chunk = (
                                decrypt_chunk(stream.blowfish_key, chunk[:2048])
                                + chunk[2048:]
                            )
                        await file.write(chunk)
                        wrote_chunk = True
                if wrote_chunk:
                    await stream.close()
                    break
                logging.error(
                    f"Reading of {track_id} failed, requesting a new stream URL..."
                )
                stream_url = await self.api.get_stream_urls(
                    [gw_track_apis[i]["TRACK_TOKEN"]], tracks_format
                )
                stream.stream_url = stream_url[0]
            else:
                paths.append(None)
                continue

            display_name = f"{api['ART_NAME']} - {api['SNG_TITLE']}"
            logging.info(f"Downloaded {display_name}")

            if tag:
                native_track_api = await self.api.get_native_track(track_id)
                await self.tag_file(file_path, native_track_api)

        return paths

    async def track(
        self,
        gw_track_api: list[dict],
        track_format: Literal["MP3_128", "MP3_320", "FLAC"] = "FLAC",
        tag: bool = True,
    ) -> Path:
        return (await self.tracks([gw_track_api], track_format, tag))[0]

    async def track_from_query(
        self,
        query: str,
        tracks_format: Literal["MP3_128", "MP3_320", "FLAC"] = "FLAC",
        track_id: bool = False,
    ) -> Optional[tuple[Path, dict]]:
        if track_id:
            track_data = await self.api.get_track(query)
            if not track_data:
                return None, None
        else:
            search_data = (await self.api.search(query))["TRACK"]["data"]
            if not search_data:
                return None, None
            choices = [f"{t['ART_NAME']} {t['SNG_TITLE']}" for t in search_data]
            track_data = search_data[get_closest_string(query, choices)]

        path = await self.track(track_data, tracks_format)
        return path, track_data

    async def tag_file(self, file_path: Path, native_track_api: dict) -> None:
        audio = FLAC(file_path)
        picture = Picture()
        picture.type = 3  # Front Cover
        picture.width = 1000
        picture.height = 1000
        picture.mime = "image/jpeg"
        picture.desc = "Cover"
        album_cover_url = native_track_api["album"]["cover_xl"]
        if native_track_api["album"].get("cover_xl"):
            async with CachedSession(
                follow_redirects=True,
                cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
            ) as session:
                async with session.get(album_cover_url) as response:
                    response.raise_for_status()
                    cover_bytes = await response.read()
            picture.data = cover_bytes

        audio["title"] = native_track_api["title"]
        audio["artist"] = ", ".join(
            [c["name"] for c in native_track_api["contributors"]]
        )
        audio["album"] = native_track_api["album"]["title"]
        audio["date"] = native_track_api["release_date"]
        audio["tracknumber"] = str(native_track_api["track_position"])
        audio["discnumber"] = str(native_track_api["disk_number"])
        audio.add_picture(picture)
        await asyncio.to_thread(audio.save, file_path)
