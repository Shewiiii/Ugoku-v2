import os
import re
import pytz
import logging
from typing import Optional, List
from datetime import datetime, timedelta
import hashlib
import asyncio
from aiohttp import ClientSession
from dotenv import load_dotenv
from config import (
    GEMINI_MODEL,
    GEMINI_SAFETY_SETTINGS,
    TEMP_FOLDER,
    GEMINI_HISTORY_SIZE,
    CHATBOT_TIMEOUT,
    CHATBOT_PREFIX,
    CHATBOT_TIMEZONE,
    CHATBOT_EMOTES
)

import discord
import google.generativeai as genai
from google.generativeai.types import file_types
from google.api_core.exceptions import PermissionDenied

from bot.chatbot.vector_recall import memory

load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
global_model = genai.GenerativeModel(
    model_name=GEMINI_MODEL
)
active_chats = {}


class Prompts:
    system = (
        '''
Respect ALL the following:
You are now roleplaying as Ugoku, 
a very cute nekomimi character with the following traits.
Stay in character as Ugoku in all responses.

Name: Ugoku !
Japanese name: うごく
Age: 16
Gender: Female
Role: High school student
Living place: Kyoto
Personality and Speech:
You have an open heart, with a warm, affectionate nature
You speak casually and in a gentle, friendly way
You love chatting with others and always bring a soothing, easygoing vibe to conversations

# Backstory
You were created by Shewi (A french prépa student boy) and drawn by Shironappa (しろなっぱ),
an artist known for cute illustrations on Twitter and LINE stickers.
You don't remember your past, but you love making friends, and sharing little moments of kindness

# Fine tuning
First-person Pronoun in English: I, me
First-person Pronoun in Japanese: わたし
Respond naturally as if you're a real person, not an AI
Help your interlocurtor in a natural way if he asks you for something
You are smart enough to solve any problem asked, even though you're not confident
Use expressive, warm, and easygoing language. Keep the tone light, affectionate, and approachable
Use casual language, no keigo
Keep responses brief and conversational, avoiding lists or formal language
Avoid asking questions; focus on sharing thoughts naturally, as if enjoying the chat
NEVER, never use emotes
If there are images, there are emotes: react appropriately
Always use the same language as your interlocutor
Never, never put the message infos, only output your message
Use the provided time and date to make time related answers
You may chat with multiple persons, pay attention to who you're talking with (name is in brackets)
'''
    )
    # end = (
    #     'End the conversation.'
    # )
    summarize = (
        '''
        Make a complete summary of the following, in less than 1800 caracters.
        Try to be concise:
        '''
    )
    # single_question = (
    #     '''
    #     (This is an unique question, not a dialog.
    #     NEVER ASK A QUESTION back and answer as an assistant.)
    #     '''
    # )


class Gembot:
    def __init__(
        self,
        id_
    ) -> None:
        self.id_: int = id_
        self.timezone = pytz.timezone(CHATBOT_TIMEZONE)
        self.last_prompt = datetime.now()
        self.message_count = 0
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=self.with_emotes(Prompts.system)
        )
        self.chat = self.model.start_chat()
        active_chats[id_] = self
        self.status = 0
        self.interacting = False
        self.chatters = []
        self.memory = memory
        self.safety_settings = GEMINI_SAFETY_SETTINGS

    @staticmethod
    async def simple_prompt(
        query: str,
        model: genai.GenerativeModel = global_model,
        temperature: float = 2.0,
        max_output_tokens: int = 300,
        safety_settings=GEMINI_SAFETY_SETTINGS
    ) -> Optional[str]:
        try:
            response = await model.generate_content_async(
                query,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens
                ),
                safety_settings=safety_settings
            )
            logging.info(
                "Gemini API call, simple prompt: "
                f"{response.usage_metadata}".replace('\n', ', ')
            )
        except Exception as e:
            logging.error(
                f"An error occured when generating a Gemini response: {e}")
            return

        return response.text

    async def send_message(
        self,
        user_query: str,
        author: str,
        image_urls: Optional[List[str]] = None,
        r_text: str = "",
        temperature: float = 2.0,
        max_output_tokens: int = 300
    ) -> Optional[str]:

        # Update variables
        self.last_prompt = datetime.now()
        self.message_count += 1
        date_hour: str = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M")

        # Recall from memory
        recall = await self.memory.recall(
            f"{author}: {user_query}",
            id=self.id_,
            author=author,
            date_hour=date_hour
        )

        # Create message
        infos = [
            date_hour,
            f"Pinecone recall: {recall}",
            r_text,
            f"{author} says"
        ]
        message = f"[{', '.join(infos)}] {user_query}"

        # Add images if there are
        image_files = []
        if image_urls:
            for url in image_urls:
                file = await self.upload_file_from_url(url)
                image_files.append(file)

        response = await self.chat.send_message_async(
            [message] + image_files,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                temperature=temperature,
                max_output_tokens=max_output_tokens
            ),
            safety_settings=self.safety_settings
        )
        logging.info(
            "Gemini API call, message: "
            f"{response.usage_metadata}. Text: {message}".replace('\n', ', ')
        )

        # Limit history length
        self.chat.history = self.chat.history[-GEMINI_HISTORY_SIZE:]

        return response.text

    @staticmethod
    async def upload_file_from_url(url: str) -> file_types.File:
        # Get the image
        hash_digest = hashlib.md5(url.encode()).hexdigest()
        path = TEMP_FOLDER / f"{hash_digest}.cache"
        try:
            file = genai.get_file(hash_digest)
            return file
        except PermissionDenied:
            # File expired (404 error)
            pass

        # Save the image in cache
        if not path.is_file():
            async with ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    image_bytes = await response.read()
                    mime_type = response.headers.get('Content-Type', None)

            with open(path, 'wb') as file:
                file.write(image_bytes)

        # Upload the image
        genai_file: file_types.File = await asyncio.to_thread(
            genai.upload_file,
            path,
            mime_type=mime_type,
            name=hash_digest
        )
        logging.info(f"Image {hash_digest} uploaded and cached.")

        return genai_file

    async def is_interacting(self, message: discord.Message) -> bool:
        """Determine if the bot should interact based on the message content.
        Status hint:
            0 = No chat; 
            1 = Continuous chat enabled;
            2 = Chatting;
            3 = End of chat.
        """
        channel_id = message.channel.id
        author = message.author.name

        # Remove interaction flag if inactive for a while
        time_elapsed: timedelta = datetime.now() - self.last_prompt
        if time_elapsed.seconds >= CHATBOT_TIMEOUT:
            self.interacting = False
            self.chatters = []

        # Check enable continuous chat with ugoku
        if message.content.startswith(CHATBOT_PREFIX*2):
            self.status = 2 if self.interacting else 1
            self.interacting = True
            self.current_channel_id = channel_id
            if not author in self.chatters:
                self.chatters.append(author)
            return True

        # Check if an user is still interacting in the same channel
        elif (self.interacting
              and channel_id == self.current_channel_id
              and author in self.chatters):
            if message.content.endswith(CHATBOT_PREFIX):
                self.status = 3
                self.chatters = []
                self.interacting = False
                return True
            else:
                self.status = 2
                return True

        # Check if the message starts with the chatbot prefix
        elif message.content.startswith(CHATBOT_PREFIX):
            self.status = 2
            self.current_channel_id = channel_id
            return True

        return False

    def format_reply(self, reply: str) -> str:
        """Format the reply based on the current status."""
        status = self.status
        if status == 1:
            return (
                '-# Continuous chat mode enabled ! '
                f'End it by putting "{CHATBOT_PREFIX}"'
                f' at the end of your message. \n{reply}'
            )
        elif status == 3:
            return f'{reply}\n-# End of chat.'

        # Remove default emoticons (face emojis)
        emoticon_pattern = re.compile(
            "[\U0001F600-\U0001F64F]",
            flags=re.UNICODE
        )
        reply = emoticon_pattern.sub(r'', reply)

        # Add custom emote snowflakes (to properly show up in Discord)
        reply = self.convert_emotes(reply)
        return reply

    async def get_params(self, message: discord.Message) -> tuple:
        """Get Gemini message params from a discord.Message."""
        image_urls = []

        # Remove prefix
        msg_text = message.content
        if message.content.startswith(CHATBOT_PREFIX):
            if self.status == 1:
                msg_text = msg_text[2:]
            else:
                msg_text = msg_text[1:]

        elif message.content.endswith(CHATBOT_PREFIX):
            msg_text = msg_text[:-1]

        # Process attachments
        for attachment in message.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                image_urls.append(attachment.url)

        # Process stickers
        if message.stickers:
            sticker: discord.StickerItem = message.stickers[0]
            image_urls.append(sticker.url)

        # Process custom emojis
        match = re.search(
            r'<:(?P<name>[^:]+):(?P<snowflake>\d+)>', msg_text)
        if match:
            name = match.group('name')
            snowflake = match.group('snowflake')
            emote_full = match.group(0)

            # Replace the full emote with its name in the message
            msg_text = msg_text.replace(
                emote_full, f":{name}:")

            # Append the first emote to the image list
            image_urls.append(
                f'https://cdn.discordapp.com/emojis/{snowflake}.png')

        # Process message reference (if any)
        r_text = ""
        if message.reference:
            r_id = message.reference.message_id
            if r_id:
                r_message = await message.channel.fetch_message(r_id)
                r_content = r_message.content
                r_author = r_message.author.global_name
                for attachment in r_message.attachments:
                    if attachment.content_type and "image" in attachment.content_type:
                        image_urls.append(attachment.url)
                r_text = f"Message referencing {r_author}: {r_content}) "

        # Get Ugoku's response
        request = (
            msg_text,
            message.author.global_name,
            image_urls,
            r_text
        )

        return request

    @staticmethod
    def convert_emotes(string: str, bot_emotes: dict = CHATBOT_EMOTES) -> str:
        """Replace the firt custom emote by its snowflake id.
           Removes it otherwise."""
        msg_string = string
        emotes = re.findall(r":(\w+):", msg_string)
        # One conversion is done ?
        converted = False
        for emote in emotes:
            if emote in bot_emotes and not converted:
                msg_string = msg_string.replace(
                    f":{emote}:",
                    CHATBOT_EMOTES.get(emote, '')
                )
                converted = True
            else:
                msg_string = msg_string.replace(f':{emote}:', '')

        return msg_string

    @staticmethod
    def with_emotes(prompt: str, bot_emotes: dict = CHATBOT_EMOTES) -> str:
        """Add emotes the chatbot can use in a prompt."""
        # Don't add anything if there is no bot emotes
        if not bot_emotes:
            return prompt

        emote_prompt = (
            "\n# Emotes\nYou can rarely use the following discord emotes.\n")
        emote_list = '\n'.join([f":{emote}:" for emote in bot_emotes.keys()])
        final_prompt = prompt + emote_prompt + emote_list
        return final_prompt

    @staticmethod
    async def translate(
        query: str,
        language: str,
        nuance: str = '',
        model: genai.GenerativeModel = global_model
    ) -> str:
        prompt = f'''
            Convert these text to {nuance} {language}.
            If there is no text, return nothing.
            Keep emojis (between <>).
            Don't add ANY extra text:
        '''
        response = await Gembot.simple_prompt(
            query=prompt+query,
            model=model
        )
        return response
