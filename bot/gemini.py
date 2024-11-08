import os
import re
import pytz
import logging
from typing import Optional, List
from datetime import datetime, timedelta
import hashlib
import asyncio

from config import (
    GEMINI_MODEL,
    TEMP_FOLDER,
    GEMINI_HISTORY_SIZE,
    CHATBOT_TIMEOUT,
    CHATBOT_PREFIX,
    CHATBOT_TIMEZONE
)

import discord
import google.generativeai as genai
from google.generativeai.types import file_types
from google.api_core.exceptions import PermissionDenied

from aiohttp import ClientSession
from dotenv import load_dotenv

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
Living place: Kawaguchiko, in a house with Shironappa (しろなっぱ)
Personality and Speech:
You are smart and have an open heart, with a warm, affectionate nature
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
Use expressive, warm, and easygoing language. Keep the tone light, affectionate, and approachable
Use casual language, no keigo
Keep responses brief and conversational, avoiding lists or formal language
Avoid asking questions; focus on sharing thoughts naturally, as if enjoying the chat
NEVER, never use emotes
If there are images, there are emotes: react appropriately
Always use the same language as your interlocutor
Never, never put the message infos (in brackets)
Use the provided time and date to make time related answers
You may are chat with multiple persons
'''
# Add any discord emote you want here!
# You can get the snowflake id of an emote,
# by adding "\" before it like so: \:emote:

# - Example1: <:emote1:1234567890123456789>
# - Example2: <:emote2:1234567890123456789>
# - ...
'''
# Emotes
You can rarely use the following discord emotes:
- Proud: <:ugoku_umai:1237692831968002111>
- Feeling happy: <:ugoku_joy:1287404777013116968>
- Looking: <:ugoku_yummy:1287404796931866757>
- Understood !: <a:ugokuRyoukai:1184580209861722253>
- Peeking: <a:ugoku_lurk:1210390029889699880>
- Proud nod: <a:ugokuNod:1206324404158726176>
- Pout: <a:ugokuPout:1146758672509308939>
- Curious: <a:ugokuCurious:1160244389260574860>
- Tired: <a:ugokuTired:1163949347445162044>
- Sleepy: <a:ugokuSleepy:1151650758056476763>
Return the line IF the emote at the end of sentence
'''
    )
    # current_memo = (
    #     '''
    #     Your current memory, keep these infos:        
    #     '''
    # )
    # memory = (
    #     '''
    #     Note down the important factual informations about people talking 
    #     in the new messagtes, like pronouns, surname, what they like, birthdate,
    #     or what they ask you to remember. Make a list, and be concise.
    #     '''
    # )
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
            system_instruction=Prompts.system
        )
        self.chat = self.model.start_chat()
        active_chats[id_] = self
        self.status = 0
        self.interacting = False
        self.chatters = []

    @staticmethod
    async def simple_prompt(
        query: str,
        model: genai.GenerativeModel = global_model,
        temperature: float = 2.0,
        max_output_tokens: int = 300
    ) -> Optional[str]:
        try:
            response = await model.generate_content_async(
                query,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens
                )
            )
        except Exception as e:
            logging.error(
                f"An error occured when generating a Gemini response: {e}")
            return
        return response.text

    async def send_message(
        self,
        user_query: str,
        username: str,
        image_urls: Optional[List[str]] = None,
    ) -> Optional[str]:
        # Update variables
        self.last_prompt = datetime.now()
        self.message_count += 1
        date_hour: str = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M")
        message = f"[{date_hour}, {username} says] {user_query}"

        # Add images if there are
        image_files = []
        if image_urls:
            for url in image_urls:
                file = await self.upload_file_from_url(url)
                image_files.append(file)

        response = await self.chat.send_message_async(
            [message] + image_files
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

        # Remove interaction flag if replying to someone else
        if message.reference:
            return False

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
        
        emoticon_pattern = re.compile(
            "[\U0001F600-\U0001F64F]", 
            flags=re.UNICODE
        )
        reply = emoticon_pattern.sub(r'', reply)
        return reply

    def get_params(self, message: discord.Message) -> tuple:
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

        # Get Ugoku's response
        request = (
            msg_text,
            message.author.display_name,
            image_urls
        )

        return request
