from deepgram import (
    DeepgramClient,
    PrerecordedOptions,
    FileSource,
)
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Union, Optional
import logging
import asyncio


from bot.chatbot import Prompts, Chat
from bot.utils import extract_video_id, get_cache_path

from youtube_transcript_api import YouTubeTranscriptApi


logger = logging.getLogger(__name__)
load_dotenv()
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')


# main.py (python example)


load_dotenv()

# URL to the audio file
AUDIO_URL = {
    "url": "https://media.discordapp.net/attachments/1281632213078900847/1298783494721241200/1213487565525753876.ogg?ex=671ad1e3&is=67198063&hm=2f3bdda80e62fe9650a3b3dbbd4ac20e81d96ae084a1dd3f7fe93011638d5af4&"
}


class AudioAi:
    def __init__(self) -> None:
        pass

    @staticmethod
    def transcribe(audio: Union[Path, str]) -> Optional[str]:
        """Simple function to transcribe audio into text using Nova-2.

        Args:
            audio (Union[Path, str]): A Path to a local file or an URL.

        Returns:
            Optional[str]: The transcription.
        """
        try:
            # Create a Deepgram client using the API key
            deepgram = DeepgramClient(DEEPGRAM_API_KEY)

            # Configure Deepgram options for audio analysis
            options = PrerecordedOptions(
                model="nova-2",
                smart_format=True,
                detect_language=True
            )

            if isinstance(audio, Path):
                # Buffer the local audio file
                with open(audio, "rb") as file:
                    buffer_data = file.read()

                payload: FileSource = {
                    "buffer": buffer_data,
                }
                response = deepgram.listen.prerecorded.v("1").transcribe_file(
                    payload,
                    options
                )

            else:
                # URL to the audio file
                AUDIO_URL = {
                    "url": audio
                }
                response = deepgram.listen.rest.v("1").transcribe_url(
                    AUDIO_URL,
                    options
                )

            # Return
            text = response.results.channels[0].alternatives[0].transcript
            return text

        except Exception as e:
            logging.error(e)

    @staticmethod
    async def summarize(text: str) -> Optional[str]:
        """Make a summary from a text using GPT-4o Mini."""
        prompt = Prompts.summarize
        response = await Chat.simple_prompt(prompt+text)
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
        text = AudioAi.get_youtube_transcript_text(url)
        if text:
            path = get_cache_path(text.encode('utf-8'))
            with open(path, 'w') as file:
                file.write(text)
            return path
