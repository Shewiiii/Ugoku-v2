from aiohttp_client_cache import CachedSession, SQLiteBackend
import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import functools
import logging
import os
from pathlib import Path
import re
from urllib.parse import urlparse
import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor

from typing import Optional, Callable

from bot.search import is_url
from bot.utils import get_dominant_rgb_from_url, clean_url, get_cache_path
from bot.vocal.track_dataclass import Track
from bot.vocal.youtube_api import get_playlist_video_ids, get_videos_info
from config import (
    YT_COOKIES_PATH,
    CACHE_EXPIRY,
    YTDLP_DOMAINS,
    MAX_DUMMY_LOAD_INDEX,
    MAX_PROCESS_POOL_WORKERS,
)

# Yt-dlp config
yt_dlp.utils.bug_reports_message = lambda: ""  # disable yt_dlp bug report
playlist_grabber = re.compile(r"list=([a-zA-Z0-9_-]+)")
video_grabber = re.compile(r"v=([a-zA-Z0-9_-]+)")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


class SetCurrentMTimePP(PostProcessor):  # Change the file date to now
    def run(self, info):
        file_path = info["filepath"]
        current_time = datetime.now().timestamp()
        os.utime(file_path, (current_time, current_time))
        return [], info


def ytdlp_options(file_path: Optional[Path] = None, ext: Optional[str] = None) -> dict:
    if ext is None:  # Should not be necessary but just in case
        ext = "bestaudio"
    ytdlp_options = {
        "cookiefile": YT_COOKIES_PATH,
        "format": ext,
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
    if file_path:
        ytdlp_options["outtmpl"] = str(file_path)
    return ytdlp_options


async def gather(tasks: list[asyncio.Task]) -> None:
    await asyncio.gather(*tasks)


class PpeManager:
    def __init__(self):
        self.ppe: Optional[ProcessPoolExecutor] = None
        self.loop = asyncio.get_event_loop()
        self.futures: set[asyncio.Future] = set()
        self.shudown_task = asyncio.create_task(self.check_ppe())

    def add_task(self, func: Callable) -> asyncio.Future:
        if not self.ppe:
            logging.info("Ppe created")
            self.ppe = ProcessPoolExecutor(max_workers=MAX_PROCESS_POOL_WORKERS)
        # Lambda or partial function to process a Track
        future = self.loop.run_in_executor(self.ppe, func)
        self.futures.add(future)
        return future

    async def check_ppe(self) -> None:
        """Shutdown the ProcessPoolExecutor if inactive."""
        # Kind of a naive approach to limit RAM usage, but should work
        while True:
            await asyncio.sleep(13)
            if not self.ppe:
                continue
            # Remove done futures
            to_remove = []
            for future in self.futures:
                if future.done():
                    to_remove.append(future)
            for f in to_remove:
                self.futures.remove(f)

            # Shutdown the ProcessPoolExecutor if no future is remaining
            if self.ppe and not self.futures:
                logging.info("Ppe incative, shutting down..")
                self.ppe.shutdown()
                self.ppe = None


class Ytdlp:
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.ppe_manager = PpeManager()

    @staticmethod
    def get_info(url, file_path: Optional[Path] = None):
        # No need to download if the file already exists
        download = bool(file_path) and not file_path.is_file()
        # Tl;dr: opus at 64kbps is not as good as mp3 128 kbps, so we force the latter
        ext = (
            "mp3" if download and is_url(url, from_=["soundcloud.com"]) else "bestaudio"
        )

        with yt_dlp.YoutubeDL(ytdlp_options(file_path, ext)) as ytdl:
            if file_path:
                ytdl.add_post_processor(SetCurrentMTimePP(ytdl))
            return ytdl.sanitize_info(ytdl.extract_info(url, download=download))

    async def get_metadata(self, url: str, file_path: Optional[Path] = None) -> dict:
        """Scrap metadata from Yt-dlp"""
        metadata = await self.ppe_manager.add_task(
            functools.partial(self.get_info, url, file_path)
        )
        return metadata

    async def create_dummy_tracks_from_playlist(
        self,
        video_ids: list[str],
    ) -> list[Optional[Track]]:
        """Create dummy tracks for remaining videos in a Youtube playlist."""
        videos_info = await get_videos_info(video_ids)
        tracks = []

        for metadata in videos_info:
            if metadata is None:
                tracks.append(None)
                continue

            # Create dummy Tracks with ytdlp lambda functions as stream generators
            url = f"https://www.youtube.com/watch?v={metadata['id']}"
            track = Track(
                service="ytdlp",
                id=metadata["id"],
                title=metadata["snippet"]["title"],
                album="Youtube",
                source_url=url,
                stream_generator=lambda url=url: self.get_tracks(url),
            )

            track.set_artist(metadata["snippet"]["channelTitle"])
            tracks.append(track)

        return tracks

    async def get_tracks(
        self, query: str, load_dummies: bool = True, download: bool = False
    ) -> list[Optional[Track]]:
        url = await self.validate_url(query)
        if not url:
            return

        dummy_tracks = []
        search = playlist_grabber.search(query)
        should_check_playlist = (
            YOUTUBE_API_KEY
            and search
            and is_url(
                query,
                from_=["youtube.com", "youtu.be"],
                include_last_part=True,
            )
            and "list=" in query
        )

        if should_check_playlist:
            # URL of a playlist (!= Video URL in a playlist)
            playlist_url = is_url(
                query,
                parts=["playlist"],
                include_last_part=True,
            )
            playlist_id = search.group(1)
            video_ids = await get_playlist_video_ids(playlist_id)

            if playlist_url:
                start_index = 0
            else:
                # It's a youtube video URL but in a playlist
                # So we ignore videos before
                video_id = video_grabber.search(query).group(1)
                start_index = video_ids.index(video_id)

            url = f"https://www.youtube.com/watch?v={video_ids[start_index]}"
            dummy_tracks = await self.create_dummy_tracks_from_playlist(
                video_ids[start_index + 1 :]
            )

            # Preload the dummy tracks for a smoother experience
            if load_dummies:
                tasks = [t.load_stream() for t in dummy_tracks[:MAX_DUMMY_LOAD_INDEX]]
                asyncio.create_task(gather(tasks))

        # Ytdlp processing with the 1st video/audio
        file_path = get_cache_path(url) if download else None

        # Extract the metadata
        metadata = await self.get_metadata(url, file_path)
        if "entries" in metadata:
            metadata = metadata["entries"][0]

        artist = metadata.get("uploader", "?")
        artist_url = metadata.get("uploader_url")
        cover_url = metadata.get("thumbnail")
        codec: str = metadata.get("acodec", "opus")

        if cover_url:
            dominant_rgb = await get_dominant_rgb_from_url(cover_url)
        else:
            dominant_rgb = None

        track = Track(
            service="ytdlp",
            id=metadata.get("id", 0),
            title=metadata.get("title", "?"),
            album=urlparse(url).netloc.split(".")[-2].capitalize(),
            cover_url=cover_url,
            duration=metadata.get("duration", "?"),
            stream_source=file_path if download else metadata.get("url"),
            source_url=url,
            dominant_rgb=dominant_rgb,
            file_extension=codec.lower(),
        )
        track.set_artist(artist)
        track.create_embed(artist_urls=[artist_url])
        return [track] + dummy_tracks

    async def validate_url(self, query: str) -> Optional[str]:
        """Verify that the url is valid and remove extra params."""
        if is_url(query, from_=YTDLP_DOMAINS):
            url = clean_url(query)
            async with CachedSession(
                follow_redirects=True,
                cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return

        # If not a valid URL, search the video and get the first result
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
