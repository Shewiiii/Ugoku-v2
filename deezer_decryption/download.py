import aiofiles
import asyncio
from deezer_decryption.api import Deezer
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from deezer_decryption.constants import EXTENSION
from deezer_decryption.crypto import decrypt_chunk
import discord
import logging
from deezer_decryption.search import get_closest_string
import httpx
from mutagen.flac import FLAC
from mutagen.flac import Picture
from pathlib import Path
from typing import Literal, Optional

from bot.utils import upload, cleanup_cache, get_cache_path, upload


class Download:
    def __init__(self, deezer: Optional[Deezer] = None):
        if deezer is None:
            deezer = Deezer()
        self.api = deezer

    async def tracks(
        self,
        gw_track_apis: list[dict],
        tracks_format: Literal['MP3_128', 'MP3_320', 'FLAC'] = 'FLAC',
        tag: bool = True
    ) -> list[Path]:
        await cleanup_cache()
        track_urls = await self.api.get_track_urls(
            [track['TRACK_TOKEN'] for track in gw_track_apis],
            tracks_format
        )
        paths = []

        for i in range(len(track_urls)):
            if track_urls[i] is None:
                paths.append(None)
                continue

            api = gw_track_apis[i]
            track_id = api['SNG_ID']
            cache_id = f"deezer{track_id}"
            file_path = get_cache_path(cache_id.encode('utf-8'))
            paths.append(file_path)
            if file_path.is_file():
                continue

            input_ = DeezerChunkedInputStream(track_id, track_urls[i])
            await input_.set_async_chunks()

            async with aiofiles.open(file_path, 'wb') as file:
                async for chunk in input_.async_chunks:
                    if chunk is None:
                        break
                    if len(chunk) >= 2048:
                        decrypted = decrypt_chunk(
                            input_.blowfish_key,
                            chunk[:2048]
                        )
                        chunk = decrypted + chunk[2048:]

                    await file.write(chunk)
            await input_.close()
            display_name = f"{api['ART_NAME']} - {api['SNG_TITLE']}"
            logging.info(f"Downloaded {display_name}")

            if tag:
                native_track_api = await self.api.get_native_track(track_id)
                await self.tag_file(file_path, native_track_api)

        return paths

    async def track(
        self,
        gw_track_api: list[dict],
        track_format: Literal['MP3_128', 'MP3_320', 'FLAC'] = 'FLAC',
        tag: bool = True
    ) -> Path:
        return (await self.tracks([gw_track_api], track_format, tag))[0]

    async def track_from_query(
        self,
        query: str,
        tracks_format: Literal['MP3_128', 'MP3_320', 'FLAC'] = 'FLAC',
        upload_: bool = False,
        bot: Optional[discord.Bot] = None,
        ctx: Optional[discord.ApplicationContext] = None,
        track_id: bool = False
    ) -> Path:
        if track_id:
            track_data = await self.api.get_track(query)
            if not track_data:
                return
        else:
            search_data = (await self.api.search(query))['TRACK']['data']
            if not search_data:
                return
            choices = [
                f"{t['ART_NAME']} {t['SNG_TITLE']}" for t in search_data]
            track_data = search_data[get_closest_string(query, choices)]

        path = await self.track(track_data, tracks_format)

        if upload_ and path:
            if bot and ctx:
                filename = f"{track_data['ART_NAME']} - {track_data['SNG_TITLE']}.{EXTENSION[tracks_format]}"
                await upload(bot, ctx, path, filename)
            else:
                logging.error("bot and ctx required for upload.")

        return path

    async def tag_file(self, file_path: Path, native_track_api: dict) -> None:
        audio = FLAC(file_path)
        picture = Picture()
        picture.type = 3  # Front Cover
        picture.width = 1000
        picture.height = 1000
        picture.mime = 'image/jpeg'
        picture.desc = 'Cover'
        album_cover_url = native_track_api['album']['cover_xl']
        if native_track_api['album'].get('cover_xl'):
            async with httpx.AsyncClient(follow_redirects=True) as session:
                response = await session.get(album_cover_url)
                response.raise_for_status()
                cover_bytes = response.content
            picture.data = cover_bytes

        audio['title'] = native_track_api['title']
        audio['artist'] = ', '.join(
            [c['name'] for c in native_track_api['contributors']])
        audio['album'] = native_track_api['album']['title']
        audio['date'] = native_track_api['release_date']
        audio['tracknumber'] = str(native_track_api['track_position'])
        audio['discnumber'] = str(native_track_api['disk_number'])
        audio.add_picture(picture)
        await asyncio.to_thread(audio.save, file_path)
