import requests
import asyncio
import urllib.parse
import aiohttp
import logging
from typing import Optional
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()
MUSIXMATCH_TOKEN = os.getenv('MUSIXMATCH_TOKEN')


async def get_lyrics(track_info: dict) -> Optional[str]:
    """Get the lyrics of a song from a track info dictionary.
    """
    base_url = (
        'https://apic-desktop.musixmatch.com/ws/1.1/macro.subtitles.get'
        '?format=json'
        '&namespace=lyrics_richsynched'
        '&subtitle_format=mxm&app_id=web-desktop-app-v1.0&'
    )

    params = {
        'q_album': track_info.get('album', ''),
        'q_artist': track_info.get('artist', ''),
        'q_artists': track_info.get('artist', ''),
        'q_track': track_info.get('title', ''),
        'track_spotify_id': track_info.get('id', ''),
        'usertoken': MUSIXMATCH_TOKEN
    }

    final_url = base_url + \
        "&".join(
            [f"{key}={urllib.parse.quote(str(value))}" for key, value in params.items()])

    response = await asyncio.to_thread(requests.get, final_url)
    response.raise_for_status()
    json = response.json()
    message = json['message']['body']['macro_calls']['track.lyrics.get']['message']
    # wtf bro its longer than the lyrics itself 
    if not 'body' in message:
        return
    lyrics = message['body']['lyrics']['lyrics_body']
    return lyrics