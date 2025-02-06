import requests
import asyncio
import urllib.parse
import logging
from typing import Optional
import os
from dotenv import load_dotenv

from config import CHATBOT_ENABLED, GEMINI_UTILS_MODEL
if CHATBOT_ENABLED:
    from bot.chatbot.gemini import Gembot
    import google.generativeai as genai

logger = logging.getLogger(__name__)
load_dotenv()
MUSIXMATCH_TOKEN = os.getenv('MUSIXMATCH_TOKEN')


class BotLyrics:

    @staticmethod
    async def get(track_info: dict) -> Optional[str]:
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
        path = ['message', 'body', 'macro_calls', 'track.lyrics.get',
                'message', 'body', 'lyrics', 'lyrics_body']
        # wtf bro its longer than the lyrics itself
        element = json
        for key in path:
            if key not in element:
                return
            element = element[key]

        # element is the lyrics_body
        return element

    @staticmethod
    async def convert(lyrics: str, to: str) -> str:
        """Convert lyrics to kana or romaji using GPT-4o Mini.
        """
        prompt = f'''
            Convert these lyrics to {to}.
            Don't add ANY extra text:
        '''
        response = await Gembot.simple_prompt(
            query=prompt+lyrics,
            model=genai.GenerativeModel(
                model_name=GEMINI_UTILS_MODEL
            )
        )
        return response
