from aiohttp_client_cache import CachedSession, SQLiteBackend
import asyncio
import os
import re
from pathlib import Path
from typing import Union
from datetime import datetime

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor

from typing import Optional

from bot.search import is_url
from bot.utils import get_cache_path, get_dominant_rgb_from_url
from bot.vocal.track_dataclass import Track
from config import YT_COOKIES_PATH


class SetCurrentMTimePP(PostProcessor):  # Change the file date to now
    def run(self, info):
        file_path = info["filepath"]
        current_time = datetime.now().timestamp()
        os.utime(file_path, (current_time, current_time))
        return [], info


yt_dlp.utils.bug_reports_message = lambda: ""  # disable yt_dlp bug report


def format_options(file_path: Union[str, Path]) -> dict:
    # See https://github.com/yt-dlp/yt-dlp/wiki/Extractors#po-token-guide
    # If Ugoku is detected as a bot
    return {
        "cookiefile": YT_COOKIES_PATH,
        "format": "bestaudio",
        "outtmpl": str(file_path),
        "restrictfilenames": True,
        "no-playlist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "geo-bypass": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "no_color": True,
        "age_limit": 100,
        "live_from_start": True,
    }


class Youtube:
    async def get_metadata(
        self, ytdl: yt_dlp.YoutubeDL, url: str, download: bool = True
    ) -> dict:
        try:
            metadata = await asyncio.to_thread(
                ytdl.extract_info, url=url, download=download
            )
        except Exception as e:
            raise e

        if download:
            # The download string doesn't end with \n
            print("")
        return metadata

    async def get_track(self, query: str) -> Optional[Track]:
        url = await self.validate_url(query)
        if not url:
            return

        file_path: Path = get_cache_path(url.encode("utf-8"))
        download = not file_path.is_file()
        ytdl = yt_dlp.YoutubeDL(format_options(file_path))
        ytdl.add_post_processor(SetCurrentMTimePP(ytdl))

        metadata = await self.get_metadata(ytdl, url, download)
        if "entries" in metadata:
            metadata = metadata["entries"][0]

        # Extract the metadata
        artist = metadata.get("uploader", "Unknown uploader")
        artist_url = metadata.get("uploader_url")
        cover_url = metadata.get("thumbnail", None)

        if cover_url:
            dominant_rgb = await get_dominant_rgb_from_url(cover_url)
        else:
            dominant_rgb = None

        track = Track(
            service="youtube",
            id=metadata.get("id", "Unknown ID"),
            title=metadata.get("title", "Unknown Title"),
            album="Youtube",
            cover_url=cover_url,
            duration=metadata.get("duration", "?"),
            stream_source=file_path,
            source_url=url,
            dominant_rgb=dominant_rgb,
        )
        track.set_artist(artist)
        track.create_embed(artist_urls=[artist_url])

        return track

    async def validate_url(self, query: str) -> Optional[str]:
        if is_url(query, from_=["youtube.com", "youtu.be"]):
            async with CachedSession(
                follow_redirects=True, cache=SQLiteBackend("cache")
            ) as session:
                async with session.get(query) as response:
                    if response.status != 200:
                        return
                    url = re.sub(r"&.*", "", query)

        # If not valid URLs, search the video and get the first result
        else:
            # Base URLs
            search = "https://www.youtube.com/results?search_query="
            watch = "https://www.youtube.com/watch?v="

            async with CachedSession(
                follow_redirects=True, cache=SQLiteBackend("cache")
            ) as session:
                async with session.get(search + query) as response:
                    response_content = await response.read()
                    search_results = re.findall(
                        r"watch\?v=(\S{11})", response_content.decode()
                    )

                    if not search_results:
                        return

                    url = watch + search_results[0]

        return url
