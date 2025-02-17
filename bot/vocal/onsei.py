import json
import os
from pathlib import Path
import logging
from typing import Literal, Optional
import aiohttp

from config import ONSEI_BLACKLIST, ONSEI_WHITELIST


class Onsei:
    """
    A class to interact with the Onsei API and process audio track information.
    """
    @staticmethod
    def get_cover(work_id: str) -> str:
        return f'https://api.asmr-200.com/api/cover/{work_id}.jpg'

    @staticmethod
    async def request(work_id: str, api: Literal['tracks', 'workInfo']) -> list:
        """Make an asynchronous HTTP GET request to the Onsei API."""
        url = f'https://api.asmr.one/api/{api}/{work_id}'
        logging.info(f'Requesting URL: {url}')

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.text()
                return json.loads(content)

    async def get_tracks_api(self, work_id: str) -> list:
        return await self.request(work_id, 'tracks')

    async def get_work_api(self, work_id: str) -> list:
        return await self.request(work_id, 'workInfo')

    @staticmethod
    def process_file(
        tracks_api: list,
        path: Path,
        ignore_whitelist: bool = False
    ) -> dict[dict]:
        file_type = tracks_api.get('type')
        duration = tracks_api.get('duration')
        title = os.path.splitext(tracks_api.get('title', ''))[0]
        media_stream_url = tracks_api.get('mediaStreamUrl')
        media_download_url = tracks_api.get('mediaDownloadUrl', '')
        extension = os.path.splitext(media_download_url)[1][1:].lower()

        def is_valid_file_type() -> bool:
            if ignore_whitelist:
                return file_type == 'audio'
            return file_type == 'audio' and extension in ONSEI_WHITELIST

        def has_valid_path() -> bool:
            if ignore_whitelist:
                return True
            return any(
                word.lower() in path.name.lower() for word in ONSEI_WHITELIST
            )

        def is_not_blacklisted() -> bool:
            return not any(
                word.lower() in title.lower() for word in ONSEI_BLACKLIST
            )

        if is_valid_file_type() and has_valid_path() and is_not_blacklisted():
            track_api = {
                title: {
                    'media_stream_url': media_stream_url,
                    'duration': duration
                }
            }
            return track_api

        return None

    def get_tracks(
        self,
        tracks_api: list,
        path: Path = Path('.'),
        final_tracks: Optional[dict] = None,
        ignore_whitelist: bool = False
    ) -> list:
        """Recursively retrieve tracks from API data."""
        if final_tracks is None:
            final_tracks = {}

        if 'error' in tracks_api:
            logging.error(tracks_api['error'])
            return final_tracks

        if isinstance(tracks_api, list):
            for element in tracks_api:
                self.get_tracks(element, path, final_tracks, ignore_whitelist)

        elif isinstance(tracks_api, dict):
            if tracks_api.get('type') == 'folder':
                folder_name = tracks_api.get('title', 'Unknown Folder')
                folder_path = path / folder_name
                self.get_tracks(
                    tracks_api.get('children', []),
                    folder_path,
                    final_tracks,
                    ignore_whitelist
                )
            else:
                file_info = self.process_file(
                    tracks_api, path, ignore_whitelist
                )
                if file_info:
                    final_tracks.update(file_info)

        return final_tracks

    def get_title(self, tracks_api: list) -> str:
        if isinstance(tracks_api, list):
            for children in tracks_api:
                result = self.get_title(children)
                if result:
                    return result

        elif isinstance(tracks_api, dict):
            if "workTitle" in tracks_api:
                return tracks_api["workTitle"]

        return '?'

    def get_all_tracks(self, tracks_api: list) -> dict[str, str]:
        tracks = self.get_tracks(tracks_api)

        if not tracks:
            logging.info(
                "No tracks found with whitelist filters. "
                "Retrying without whitelist."
            )
            tracks = self.get_tracks(
                tracks_api, ignore_whitelist=True)

        return tracks
