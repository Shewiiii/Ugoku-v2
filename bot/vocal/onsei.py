import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import aiohttp

from bot.vocal.types import OnseiAPIResponse
from config import ONSEI_BLACKLIST, ONSEI_WHITELIST

logger = logging.getLogger(__name__)


class Onsei:
    def get_cover(self, work_id: str) -> str:
        """Construct the cover image URL."""
        return f'https://api.asmr-200.com/api/cover/{work_id}.jpg'

    async def request(self, work_id: str, api: str) -> OnseiAPIResponse:
        """Make an asynchronous HTTP GET request."""
        url = f'https://api.asmr.one/api/{api}/{work_id}'
        logger.info(f'Requesting URL: {url}')

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.text()
                return json.loads(content)

    async def get_tracks_api(self, work_id: str) -> OnseiAPIResponse:
        """Retrieve the tracks API data."""
        return await self.request(work_id, 'tracks')

    async def get_work_api(self, work_id: str) -> OnseiAPIResponse:
        """Retrieve the work information API data."""
        return await self.request(work_id, 'workInfo')

    def process_file(
        self,
        tracks_api: OnseiAPIResponse,
        path: Path,
        ignore_whitelist: bool = False
    ) -> Optional[Dict[str, str]]:
        """Process a single track file."""
        file_type = tracks_api.get('type')
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
            return {title: media_stream_url}

        return None

    def get_tracks(
        self,
        tracks_api: OnseiAPIResponse,
        path: Path = Path('.'),
        tracks: Optional[Dict[str, str]] = None,
        ignore_whitelist: bool = False
    ) -> Dict[str, str]:
        """Recursively retrieve tracks from API data."""
        if tracks is None:
            tracks = {}

        if 'error' in tracks_api:
            logger.error(tracks_api['error'])
            return tracks

        if isinstance(tracks_api, list):
            for element in tracks_api:
                self.get_tracks(element, path, tracks, ignore_whitelist)

        elif isinstance(tracks_api, dict):
            if tracks_api.get('type') == 'folder':
                folder_name = tracks_api.get('title', 'Unknown Folder')
                folder_path = path / folder_name
                self.get_tracks(
                    tracks_api.get('children', []),
                    folder_path,
                    tracks,
                    ignore_whitelist
                )
            else:
                file_info = self.process_file(
                    tracks_api, path, ignore_whitelist
                )
                if file_info:
                    tracks.update(file_info)

        return tracks

    def get_title(
        self,
        tracks_api: OnseiAPIResponse
    ) -> Optional[str]:
        """Extract the work title from API data."""
        if isinstance(tracks_api, list):
            for children in tracks_api:
                result = self.get_title(children)
                if result:
                    return result

        elif isinstance(tracks_api, dict):
            if "workTitle" in tracks_api:
                return tracks_api["workTitle"]

        return None

    def get_all_tracks(
        self,
        tracks_api: OnseiAPIResponse
    ) -> Dict[str, str]:
        """Retrieve all tracks, retrying without whitelist if needed."""
        tracks = self.get_tracks(tracks_api, tracks={})

        if not tracks:
            logger.info(
                "No tracks found with whitelist filters. "
                "Retrying without whitelist."
            )
            tracks = self.get_tracks(
                tracks_api,
                ignore_whitelist=True,
                tracks={}
            )

        return tracks
