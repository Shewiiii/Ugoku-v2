from aiohttp_client_cache import CachedSession, SQLiteBackend
import asyncio
from datetime import datetime
import os
import re
from pathlib import Path
from typing import Union
from urllib.parse import urlparse


import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor

from typing import Optional

from bot.search import is_url
from bot.utils import get_cache_path, get_dominant_rgb_from_url, clean_url
from bot.vocal.track_dataclass import Track
from bot.vocal.youtube_api import get_playlist_video_ids, get_videos_info
from config import YT_COOKIES_PATH, CACHE_EXPIRY, YTDLP_DOMAINS


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


class Ytdlp:
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

    async def check_youtube_playlist(self, query: str) -> list[Optional[Track]]:
        if not is_url(
            query,
            from_=["www.youtube.com", "youtu.be"],
            parts=["playlist"],
            include_last_part=True,
        ):
            return []
        video_ids = await get_playlist_video_ids(query)
        videos_info = await get_videos_info(video_ids)  # noqa: F704
        tracks = []

        for metadata in videos_info:
            if metadata is None:
                tracks.append(None)
                continue

        track = Track(
            service="ytdlp",
            id=metadata["id"],
            title=metadata["snippet"]["title"],
            album=f"https://www.youtube.com/channel/{metadata['snippet']['channelId']}",
            # Supporsing maxres is always available, to verify tho
            cover_url=metadata["snippet"]["thumbnails"]["maxres"],
            duration="?",
            stream_source=None,
            source_url=None,
            dominant_rgb=None,
            stream_generator=lambda: self.get_track(f"https://youtu.be/{metadata["id"]}")
        )
        track.set_artist(metadata["snippet"]["channelTitle"])
        print(track)
        
        # Create Tracks with ytdlp lambda functions as stream generators
        
        ...

    async def get_track(self, query: str) -> Optional[list[Track]]:
        url = await self.validate_url(query)
        # Remove URL params
        cleaned_url = clean_url(url)
        if not url:
            return

        file_path: Path = get_cache_path(cleaned_url.encode("utf-8"))
        download = not file_path.is_file()
        ytdl = yt_dlp.YoutubeDL(format_options(file_path))
        ytdl.add_post_processor(SetCurrentMTimePP(ytdl))

        # If a playlist url is parsed, append the remaining vids
        # with stream generators
        playlist_task = asyncio.create_task(self.check_youtube_playlist)

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
            service="ytdlp",
            id=metadata.get("id", "Unknown ID"),
            title=metadata.get("title", "Unknown Title"),
            album=urlparse(cleaned_url).netloc.split(".")[-2].capitalize(),
            cover_url=cover_url,
            duration=metadata.get("duration", "?"),
            stream_source=file_path,
            source_url=cleaned_url,
            dominant_rgb=dominant_rgb,
        )
        track.set_artist(artist)
        track.create_embed(artist_urls=[artist_url])

        return [track]

    async def validate_url(self, query: str) -> Optional[str]:
        if is_url(query, from_=YTDLP_DOMAINS):
            async with CachedSession(
                follow_redirects=True,
                cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
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
                follow_redirects=True,
                cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
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
