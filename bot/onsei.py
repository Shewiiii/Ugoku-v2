import json
from pathlib import Path
import os
import logging
import aiohttp

from config import ONSEI_BLACKLIST, ONSEI_WHITELIST

logger = logging.getLogger(__name__)


class Onsei:
    def get_cover(self, work_id: str) -> str:
        return f'https://api.asmr-200.com/api/cover/{work_id}.jpg'

    async def request(self, work_id: str, api: str) -> list | dict:
        url = f'https://api.asmr.one/api/{api}/{work_id}'
        logging.info(f'Request: {url}')

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                response_content = await response.text()
                tracks_api = json.loads(response_content)
                return tracks_api

    async def get_tracks_api(self, work_id: str) -> list | dict:
        return await self.request(work_id, 'tracks')

    async def get_work_api(self, work_id: str) -> list | dict:
        return await self.request(work_id, 'workInfo')

    def process_file(
        self,
        tracks_api: dict,
        path: Path
    ) -> dict | None:
        file_type = tracks_api['type']
        title = os.path.splitext(tracks_api['title'])[0]
        media_stream_url = tracks_api['mediaStreamUrl']
        # stream_urls can have a different format
        media_download_url = tracks_api['mediaDownloadUrl']
        extension = os.path.splitext(media_download_url)[1]

        def is_valid_file_type() -> bool:
            return file_type == 'audio' and extension[1:] in ONSEI_WHITELIST

        def has_valid_path() -> bool:
            return any(
                word.lower() in path.name.lower() for word in ONSEI_WHITELIST
            )

        def is_not_blacklisted() -> bool:
            return not any(word in title for word in ONSEI_BLACKLIST)

        if is_valid_file_type() and has_valid_path() and is_not_blacklisted():
            return {title: media_stream_url}

        return None

    def get_tracks(
        self,
        tracks_api: list | dict,
        path: Path = Path('.'),
        tracks: dict = {}
    ) -> dict:
        if 'error' in tracks_api:
            logging.error(tracks_api['error'])
            return tracks

        # Folder/file list at a certain folder depth
        if isinstance(tracks_api, list):
            for element in tracks_api:
                self.get_tracks(
                    element,
                    path,
                    tracks
                )
        # Folder API dict
        elif tracks_api['type'] == 'folder':
            folder_name: str = tracks_api['title']
            folder_path = path / folder_name
            self.get_tracks(
                tracks_api['children'],
                folder_path,
                tracks
            )
        # File API dict
        else:
            file_info = self.process_file(
                tracks_api,
                path
            )
            if file_info:
                tracks.update(file_info)

        return tracks

    def get_title(self, tracks_api: dict) -> str | None:
        # If the input data is a list, iterate through each item
        if isinstance(tracks_api, list):
            for children in tracks_api:
                result = self.get_title(children)
                if result:
                    return result

        # If the input data is a dictionary, check for the "workTitle" key
        elif isinstance(self, tracks_api, dict):
            if "workTitle" in tracks_api:
                return tracks_api["workTitle"]

        # If neither a list nor a dictionary, return None
        return None
