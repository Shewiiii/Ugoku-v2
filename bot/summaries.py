from pathlib import Path
from typing import Optional
import asyncio

import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi

from bot.chatbot.gemini import Prompts, Gembot
from bot.utils import extract_video_id, get_cache_path
from config import GEMINI_UTILS_MODEL


class Summaries:
    def __init__(self) -> None:
        pass

    @staticmethod
    async def summarize(text: str) -> Optional[str]:
        """Make a summary from a text using GPT-4o Mini."""
        prompt = Prompts.summarize
        response = await Gembot.simple_prompt(
            prompt+text,
            model=genai.GenerativeModel(
                model_name=GEMINI_UTILS_MODEL
            )
        )
        return response

    @staticmethod
    async def get_youtube_transcript_text(url: str) -> Optional[str]:
        video_id = extract_video_id(url)
        if not video_id:
            return

        transcript_list = await asyncio.to_thread(
            YouTubeTranscriptApi.list_transcripts,
            video_id
        )

        transcripts: dict = (
            transcript_list._manually_created_transcripts
            or transcript_list._generated_transcripts
        )
        if transcripts:
            transcript_data = list(transcripts.values())[0].fetch()
            text = '\n'.join(entry['text'] for entry in transcript_data)

            return text

    @staticmethod
    async def get_youtube_transcript_path(url: str) -> Optional[Path]:
        text = Summaries.get_youtube_transcript_text(url)
        if text:
            path = get_cache_path(text.encode('utf-8'))
            with open(path, 'w') as file:
                file.write(text)
            return path
