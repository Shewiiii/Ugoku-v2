from aiohttp_client_cache import CachedSession, SQLiteBackend
import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import functools
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse
import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor
import sqlite3
import json

from typing import Optional, Callable

from bot.search import is_url
from bot.utils import get_dominant_rgb_from_url, clean_url, get_cache_path
from bot.vocal.track_dataclass import Track
from bot.vocal.youtube_api import get_playlist_video_ids, get_videos_info
from config import (
    COOKIES_PATH,
    CACHE_EXPIRY,
    MAX_DUMMY_LOAD_INDEX,
    MAX_PROCESS_POOL_WORKERS,
    AGRESSIVE_CACHING,
)

# Yt-dlp config
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ""  # disable yt_dlp bug report
playlist_grabber = re.compile(r"list=([a-zA-Z0-9_-]+)")
video_grabber = re.compile(r"v=([a-zA-Z0-9_-]+)")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


class SetCurrentMTimePP(PostProcessor):  # Change the file date to now
    def run(self, info):
        file_path = info["filepath"]
        current_time = datetime.now().timestamp()
        os.utime(file_path, (current_time, current_time))
        return [], info


def ytdlp_options(file_path: Optional[Path] = None, ext: str = "bestaudio") -> dict:
    ytdlp_options = {
        "cookiefile": COOKIES_PATH,
        "format": ext,
        "restrictfilenames": True,
        "no_playlist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "geo_bypass": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "no_color": True,
        "age_limit": 100,
        "live_from_start": True,
        "playlist_items": "1",
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
        self.shutdown_task = asyncio.create_task(self.check_ppe())

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
        self.db_conn = sqlite3.connect("ytdlp_cache.sqlite")
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute(
            "CREATE TABLE IF NOT EXISTS metadata_cache (query TEXT PRIMARY KEY, metadata TEXT)"
        )
        self.db_conn.commit()

    @staticmethod
    def get_ext(url: str) -> str:
        # Tl;dr: opus at 64kbps is not as good as mp3 128 kbps, so we force the latter
        ext = "mp3" if is_url(url, from_=["soundcloud.com"]) else "bestaudio"
        ...
        return ext

    @staticmethod
    def get_info(url, file_path: Optional[Path] = None):
        # No need to download if the file already exists
        download = bool(file_path) and not file_path.is_file()
        ext = Ytdlp.get_ext(url)

        with yt_dlp.YoutubeDL(ytdlp_options(file_path, ext)) as ytdl:
            if file_path:
                ytdl.add_post_processor(SetCurrentMTimePP(ytdl))

            raw_info = ytdl.extract_info(url, download=download)
            sanitized_info = ytdl.sanitize_info(raw_info)

            final_info = sanitized_info
            if "entries" in sanitized_info and sanitized_info.get("entries"):
                final_info = sanitized_info["entries"][0]

        # For Youtube urls, use the audio codec as the extension instead of the container
        # So the file can be played in Discord
        if is_url(url, from_=["youtube.com", "youtu.be"]):
            final_info["audio_ext"] = "opus"
        else:
            final_info["audio_ext"] = final_info.get("audio_ext")

        return final_info

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
                stream_generator=lambda url=url: self.get_tracks(url, from_dummy=True),
            )

            track.set_artist(metadata["snippet"]["channelTitle"])
            tracks.append(track)

        return tracks

    async def get_tracks(
        self,
        query: str,
        load_dummies: bool = True,
        download: bool = False,
        offset: int = 0,
        from_dummy: bool = False,
    ) -> list[Optional[Track]]:
        """If download is None, Only content with a duration of less than 10 minutes will be downloaded."""
        dummy_tracks = []
        url = await self.validate_url(query)
        if not url:
            return []
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
            and not download
        )

        metadata = None
        # Check cache if not a playlist and query is present
        if url:
            # url is the validated and cleaned query or a search result
            self.db_cursor.execute(
                "SELECT metadata FROM metadata_cache WHERE query = ?", (url,)
            )
            row = self.db_cursor.fetchone()
            if row:
                logging.info(f"Cache hit for {url}")
                metadata = json.loads(row[0])

        # YOUTUBE PLAYLISTS
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
                start_index = video_ids.index(video_id) + offset

            url = f"https://www.youtube.com/watch?v={video_ids[start_index]}"
            dummy_tracks = await self.create_dummy_tracks_from_playlist(
                video_ids[start_index + 1 :]
            )

            # Preload the dummy tracks for a smoother experience
            if load_dummies:
                tasks = [t.load_stream() for t in dummy_tracks[:MAX_DUMMY_LOAD_INDEX]]
                asyncio.create_task(gather(tasks))

        file_path = get_cache_path(url)
        cached = file_path.is_file()
        # If not found in cache, get metadata
        if not metadata or ("url" not in metadata and not cached):
            # Extract the metadata
            metadata = await self.get_metadata(url, file_path if download else None)
            # Store in cache if not a playlist and if the vid is less than 20 mins
            if "duration" in metadata and metadata["duration"] <= 1200:
                db_metadata = metadata.copy()
                del db_metadata["url"]  # No URLs as they expire
                self.db_cursor.execute(
                    "INSERT OR REPLACE INTO metadata_cache (query, metadata) VALUES (?, ?)",
                    (url, json.dumps(db_metadata)),
                )
                self.db_conn.commit()
                logging.info(f"Cached metadata for {url}")

        title = metadata.get("title", "?")
        artist = metadata.get("uploader", "?")
        artist_url = metadata.get("uploader_url", "")
        cover_url = metadata.get("thumbnail", "")
        audio_ext: str = metadata.get("audio_ext", "webm")
        duration = round(metadata.get("duration", 114514))

        if cover_url:
            dominant_rgb = await get_dominant_rgb_from_url(cover_url)
        else:
            dominant_rgb = None

        track = Track(
            service="ytdlp",
            id=metadata["id"],
            title=title,
            album=urlparse(url).netloc.split(".")[-2].capitalize()
            if url
            else "Unknown",
            cover_url=cover_url,
            duration=duration,
            stream_source=file_path if download or cached else metadata["url"],
            source_url=url,
            dominant_rgb=dominant_rgb,
            file_extension=audio_ext,
        )
        track.set_artist(artist)
        track.create_embed(artist_urls=[artist_url] if artist_url else None)

        # Cache !
        should_cache = (
            not from_dummy
            and not download
            and AGRESSIVE_CACHING
            and duration <= 1200
            and not cached
        )
        
        if should_cache:
            cache_future = self.ppe_manager.add_task(
                functools.partial(self.cache_task, file_path, url, metadata)
            )
            cache_future.add_done_callback(
                lambda fut: setattr(track, "stream_source", file_path)
                if fut.result()
                else None
            )

        return [track] + dummy_tracks

    @staticmethod
    def cache_task(file_path: Path, url: str, metadata: dict) -> bool:
        try:
            with yt_dlp.YoutubeDL(ytdlp_options(file_path, Ytdlp.get_ext(url))) as ytdl:
                ytdl.process_ie_result(ie_result=metadata)
                os.utime(file_path, (time.time(), time.time()))
        except Exception as e:
            logging.error(f"Error caching a ytdlp source: {e}")
            return False

        logging.info(f"Cached {url}")
        return True

    async def validate_url(self, query: str) -> Optional[str]:
        """If the query is not an url, search a video on Youtube."""
        if is_url(query):
            url = clean_url(query)
            return url
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
