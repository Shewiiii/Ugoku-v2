import asyncio
from aiohttp_client_cache import CachedSession, SQLiteBackend
import json
import os
from typing import Literal, Union, Optional
import logging
from pathlib import Path
from bot.vocal.track_dataclass import Track
from bot.utils import get_dominant_rgb_from_url
from config import ONSEI_BLACKLIST, ONSEI_WHITELIST, DEFAULT_EMBED_COLOR


class Onsei:
    """
    A class to interact with the Onsei API and process audio track information.
    """

    @staticmethod
    def get_cover(work_id: str) -> str:
        return f"https://api.asmr-200.com/api/cover/{work_id}.jpg"

    @staticmethod
    async def request(work_id: str, api: Literal["tracks", "workInfo"]) -> list:
        """Make an asynchronous HTTP GET request to the Onsei API."""
        url = f"https://api.asmr.one/api/{api}/{work_id}"
        logging.info(f"Requesting URL: {url}")

        async with CachedSession(cache=SQLiteBackend("cache")) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.text()
                return json.loads(content)

    async def get_tracks_api(self, work_id: str) -> list:
        return await self.request(work_id, "tracks")

    async def get_work_api(self, work_id: str) -> list:
        return await self.request(work_id, "workInfo")

    def process_file(
        self,
        track_api: dict,
        work_api: dict,
        path: Path,
        ignore_whitelist: bool = False,
        track_number: int = 1,
        dominant_rgb: tuple = DEFAULT_EMBED_COLOR,
    ) -> dict[dict]:
        # track_api
        file_type = track_api.get("type")
        duration = track_api.get("duration")
        title = os.path.splitext(track_api.get("title", ""))[0]
        media_stream_url = track_api.get("mediaStreamUrl")
        media_download_url = track_api.get("mediaDownloadUrl", "")
        extension = os.path.splitext(media_download_url)[1][1:].lower()

        def is_valid_file_type() -> bool:
            if ignore_whitelist:
                return file_type == "audio"
            return file_type == "audio" and extension in ONSEI_WHITELIST

        def has_valid_path() -> bool:
            if ignore_whitelist:
                return True
            return any(word.lower() in path.name.lower() for word in ONSEI_WHITELIST)

        def is_not_blacklisted() -> bool:
            return not any(word.lower() in title.lower() for word in ONSEI_BLACKLIST)

        if is_valid_file_type() and has_valid_path() and is_not_blacklisted():
            id = work_api.get("id", 0)
            track = Track(
                service="onsei",
                id=id,
                cover_url=self.get_cover(id),
                title=title,
                album=work_api.get("title", "?"),
                duration=duration,
                stream_source=media_stream_url,
                source_url=media_stream_url,
                track_number=track_number,
                dominant_rgb=dominant_rgb,
            )
            track.set_artists([i["name"] for i in work_api["vas"]])
            track.create_embed()
            return track

        return None

    def get_tracks(
        self,
        track_api: Union[list, dict],
        work_api: dict,
        final_tracks: Optional[list] = None,
        ignore_whitelist: bool = False,
        dominant_rgb: tuple = DEFAULT_EMBED_COLOR,
        path: Path = Path("."),
    ) -> list:
        """Recursively retrieve tracks from API data."""
        if final_tracks is None:
            final_tracks = []

        params = (work_api, final_tracks, ignore_whitelist, dominant_rgb)

        if "error" in track_api:
            logging.error(track_api["error"])
            return final_tracks

        if isinstance(track_api, list):
            for element in track_api:
                self.get_tracks(element, *params, path)

        elif isinstance(track_api, dict):
            if track_api.get("type") == "folder":
                folder_name = track_api.get("title", "Unknown Folder")
                folder_path = path / folder_name
                self.get_tracks(
                    track_api.get("children", []),
                    *params,
                    folder_path,
                )
            else:
                file_info = self.process_file(
                    track_api,
                    work_api,
                    path,
                    ignore_whitelist,
                    len(final_tracks) + 1,
                    dominant_rgb,
                )
                if file_info:
                    final_tracks.append(file_info)

        return final_tracks

    async def get_all_tracks(self, work_id: str) -> list:
        tracks_api, work_api, dominant_rgb = await asyncio.gather(
            self.get_tracks_api(work_id),
            self.get_work_api(work_id),
            get_dominant_rgb_from_url(self.get_cover(work_id)),
        )

        tracks = self.get_tracks(tracks_api, work_api, dominant_rgb=dominant_rgb)

        if not tracks:
            logging.info(
                "No tracks found with whitelist filters. Retrying without whitelist."
            )
            tracks = self.get_tracks(
                tracks_api, work_api, dominant_rgb=dominant_rgb, ignore_whitelist=True
            )

        return tracks
