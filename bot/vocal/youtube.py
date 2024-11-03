import asyncio
import re
from pathlib import Path
from typing import Union

import yt_dlp
from typing import Optional
import aiohttp

from bot.search import is_url
from bot.utils import get_cache_path, get_dominant_rgb_from_url
from bot.vocal.custom import generate_info_embed


yt_dlp.utils.bug_reports_message = lambda: ''  # disable yt_dlp bug report


def format_options(file_path: Union[str, Path]) -> dict:
    # See https://github.com/yt-dlp/yt-dlp/wiki/Extractors#po-token-guide
    # If Ugoku is detected as a bot
    po_token = ''
    return {
        'format': 'bestaudio',
        'outtmpl': str(file_path),
        'restrictfilenames': True,
        'no-playlist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'geo-bypass': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'no_color': True,
        'age_limit': 100,
        'live_from_start': True,
        'quiet': True,
        
        # 'extractor-args': 'youtube:player-client=web,default;po_token=web+'+po_token,
        # 'cookies': './cookies.json'
    }


class Youtube:
    async def get_metadata(
        self,
        ytdl: yt_dlp.YoutubeDL,
        url: str,
        download: bool = True
    ) -> dict:
        try:
            metadata = await asyncio.to_thread(
                ytdl.extract_info,
                url=url,
                download=download
            )
        except Exception as e:
            raise e

        if download:
            # The download string doesn't end with \n
            print('')
        return metadata

    async def get_track_info(self, query: str) -> Optional[dict]:
        url = await self.validate_url(query)
        if not url:
            return

        file_path: Path = get_cache_path(url.encode('utf-8'))
        download = False if file_path.is_file() else True
        ytdl = yt_dlp.YoutubeDL(format_options(file_path))

        metadata = await self.get_metadata(ytdl, url, download)
        if 'entries' in metadata:
            metadata = metadata['entries'][0]

        # Extract the metadata
        title = metadata.get('title', 'Unknown Title')
        album = 'Youtube'
        display_name = title
        id = metadata.get('id', 'Unknown ID')
        artists = [metadata.get('uploader', 'Unknown uploader')]
        cover_url = metadata.get('thumbnail', None)
        if cover_url:
            dominant_rgb = await get_dominant_rgb_from_url(cover_url)
        else:
            dominant_rgb = None
        # Duration in seconds
        duration = metadata.get('duration', 0)

        # Prepare the track/video
        def embed():
            return generate_info_embed(
                url=url,
                title=title,
                album=album,
                artists=artists,
                cover_url=cover_url,
                dominant_rgb=dominant_rgb
            )

        track_info = {
            'display_name': display_name,
            'title': title,
            'artist': artists[0],
            'album': album,
            'cover': cover_url,
            'duration': duration,
            'source': file_path,
            'url': url,
            'embed': embed,
            'id': id
        }

        return track_info

    async def validate_url(self, query: str) -> Optional[str]:
        if is_url(query, from_=['youtube.com', 'youtu.be']):
            async with aiohttp.ClientSession() as session:
                async with session.get(query) as response:
                    if response.status != 200:
                        return
                    url = re.sub(r"&.*", "", query)

        # If not valid URLs, search the video and get the first result
        else:
            # Base URLs
            search = "https://www.youtube.com/results?search_query="
            watch = "https://www.youtube.com/watch?v="

            async with aiohttp.ClientSession() as session:
                async with session.get(search+query) as response:
                    response_content = await response.read()
                    search_results = re.findall(
                        r"watch\?v=(\S{11})",
                        response_content.decode()
                    )

                    if not search_results:
                        return

                    url = watch+search_results[0]

        return url
