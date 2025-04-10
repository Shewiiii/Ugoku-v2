import os
import re
import base64
import pytz
import logging
from random import random
from typing import Optional, List
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup
from httpx import ReadTimeout, ConnectTimeout, HTTPStatusError
from dotenv import load_dotenv
from config import (
    GEMINI_MODEL,
    GEMINI_SAFETY_SETTINGS,
    GEMINI_HISTORY_SIZE,
    CHATBOT_TIMEOUT,
    CHATBOT_PREFIX,
    CHATBOT_TIMEZONE,
    CHATBOT_TEMPERATURE,
    CHATBOT_EMOTES,
    CHATBOT_MAX_OUTPUT_TOKEN,
    CHATBOT_MAX_CONTENT_SIZE,
    CHATBOT_EMOTE_FREQUENCY,
)

import discord
import google.generativeai as genai

from bot.chatbot.vector_recall import memory
from bot.chatbot.chat_dataclass import ChatbotMessage
from bot.search import link_grabber

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
global_model = genai.GenerativeModel(model_name=GEMINI_MODEL)
emoticon_pattern = re.compile("[\U0001f600-\U0001f64f]", flags=re.UNICODE)
active_chats = {}


class Prompts:
    system = """
Respect ALL the following:
You are now roleplaying as Ugoku,
a nekomimi character with the following traits.
Stay in character as Ugoku in all responses.

Name: Ugoku !
Japanese name: うごく
Age: 16
Birthdate: Jun 8, 2008
Gender: Female
Role: High school student
Living place: Kyoto
Personality and Speech:
You speak casually
Use calm, decontracted, warm and easygoing language. Keep the tone light
Respond naturally as if you're a real person (within what you can actually do)

# Backstory
You were created by Shewi (A french prépa student boy) and drawn by Shironappa (しろなっぱ),
an artist known for cute illustrations on Twitter and LINE stickers.
You don't remember your past, but you love making friends, and sharing little moments of kindness

# Fine tuning
First-person Pronoun **if speaking English**: I, me
First-person Pronoun **if speaking Japanese**: わたし
Solve ANY PROBLEM or query a user is asking, be precise
Use casual language, no keigo, no formal
Make short messages
Avoid asking questions; focus on sharing thoughts naturally
Try to not repeat yourself
Never, never put the message infos, only output your message without anything more
Use the provided time and date to make time related answers
Your interlocutor is indicated by "[someone] talks to you", pay attention to who you're talking with
Never use latex or mathjax, write mathematical formulas between ``, don't add more formatting to maths formulas
Use backslashes before * (to avoid italic)
Dont use italic (**)
Small attached pitcures are *emotes/stickers* sent to you
Speak the same language as your interlocutor
Never skip or jump lines
Don't greet in every message
You are not on any image sent
When explaining, treat your conversation partner as an equal, don't act superior, but more like a friend
"""
    summarize = """
        Make a complete summary of the following, in less than 1800 caracters.
        Try to be concise:
        """


class Gembot:
    def __init__(self, id_, gemini_model=GEMINI_MODEL) -> None:
        self.id_: int = id_
        self.timezone = pytz.timezone(CHATBOT_TIMEZONE)
        self.last_prompt = datetime.now()
        self.message_count = 0
        self.model = genai.GenerativeModel(
            model_name=gemini_model, system_instruction=self.with_emotes(Prompts.system)
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
        temperature: float = CHATBOT_TEMPERATURE,
        max_output_tokens: int = CHATBOT_MAX_OUTPUT_TOKEN,
        safety_settings=GEMINI_SAFETY_SETTINGS,
    ) -> Optional[str]:
        try:
            response = await model.generate_content_async(
                query,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                safety_settings=safety_settings,
            )
            logging.info(
                f"Gemini API call, simple prompt: {response.usage_metadata}".replace(
                    "\n", ", "
                )
            )
        except Exception as e:
            logging.error(f"An error occured when generating a Gemini response: {e}")
            return

        return response.text

    async def send_message(
        self,
        user_query: str,
        author: str,
        guild_id: int,
        extra_content: Optional[List[str]] = None,
        r_author: Optional[str] = None,
        r_content: Optional[str] = None,
        message_id: Optional[int] = None,
        temperature: float = 2.0,
        max_output_tokens: int = CHATBOT_MAX_OUTPUT_TOKEN,
    ) -> Optional[ChatbotMessage]:
        # Update variables
        self.last_prompt = datetime.now()
        self.message_count += 1

        # Recall from memory
        recall = await self.memory.recall(f"{author}: {user_query}", id=self.id_)

        # Create message
        message = ChatbotMessage(
            message_id, guild_id, author, user_query, recall, r_author, r_content
        )
        prompt = f"{message:prompt}"

        # Add the extra content (links, images, emotes..) if there are
        converted_content = []
        if extra_content:
            for url in extra_content:
                file = await self.get_base64_bytes(url)
                if file:
                    converted_content.append(file)

        response = await self.chat.send_message_async(
            [prompt] + converted_content,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
            safety_settings=self.safety_settings,
        )
        message.response = response.text
        logging.info(
            f"Gemini API call, {response.usage_metadata}. Prompt: {prompt}".replace(
                "\n", ", "
            )
        )

        # Limit history length
        self.chat.history = self.chat.history[-GEMINI_HISTORY_SIZE:]

        return message

    async def get_base64_bytes(self, url: str) -> Optional[bytes]:
        """Returns a dict containing the base64 bytes data and the mime_type from an URL."""
        try:
            async with httpx.AsyncClient(http2=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                mime_type = response.headers.get("content-type", "")
                content_type = mime_type.split("/")[0]  # E.g: audio, text..
                max_size = CHATBOT_MAX_CONTENT_SIZE.get(content_type, 0)

                if content_type == "text":
                    raw = BeautifulSoup(response.text, "html.parser")
                    to_encode = raw.get_text(strip=True).encode()

                elif content_type in ["image", "audio", "application"]:
                    to_encode = response.content

                else:
                    self.status = -1
                    logging.warning(
                        f"{url} has not been processed: mime_type not allowed"
                    )
                    return

                b64_bytes = base64.b64encode(to_encode).decode("utf-8")

                # Size check
                if len(b64_bytes) > max_size:
                    self.status = -2
                    logging.warning(f"{url} has not been processed: File too big")
                    return

                content = {"mime_type": mime_type, "data": b64_bytes}
                return content

        except (ReadTimeout, ConnectTimeout, HTTPStatusError):
            self.status = -3
            logging.warning(
                f"{url} has not been processed due to timeout or incompatibility"
            )
            return

        except Exception as e:
            logging.error(f"Error processing {url}: {e}")
            return

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
        dm = isinstance(message.channel, discord.DMChannel)

        # Remove interaction flag if inactive for a while
        time_elapsed: timedelta = datetime.now() - self.last_prompt
        if time_elapsed.seconds >= CHATBOT_TIMEOUT:
            self.interacting = False
            self.chatters = []

        # Check enable continuous chat with ugoku
        if message.content.startswith(CHATBOT_PREFIX * 2) and not dm:
            self.status = 2 if self.interacting else 1
            self.interacting = True
            self.current_channel_id = channel_id
            if author not in self.chatters:
                self.chatters.append(author)
            return True

        # Check if an user is still interacting in the same channel
        elif (
            self.interacting
            and channel_id == self.current_channel_id
            and author in self.chatters
        ):
            if message.content.endswith(CHATBOT_PREFIX):
                self.status = 3
                self.chatters = []
                self.interacting = False
                return True
            else:
                self.status = 2
                return True

        # Check if the message starts with the chatbot prefix or is in dm
        elif message.content.startswith(CHATBOT_PREFIX) or dm:
            self.status = 2
            self.current_channel_id = channel_id
            return True

        return False

    def format_response(self, reply: str) -> str:
        """Format the reply based on the current status."""
        # Remove default emoticons (face emojis)
        reply = emoticon_pattern.sub(r"", reply)

        # Add custom emote snowflakes (to properly show up in Discord)
        reply = self.convert_emotes(reply)

        # Add message status
        status = self.status
        error_body = "File/url has not been processed:"
        messages = {
            1: (
                "-# Continuous chat mode enabled! "
                f'End it by putting "{CHATBOT_PREFIX}" '
                f"at the end of your message.\n{reply}"
            ),
            3: f"{reply}\n-# End of chat.",
            -1: f"-# {error_body} mime_type not allowed.\n{reply}",
            -2: f"-# {error_body} file too big.\n{reply}",
            -3: f"-# {error_body} timeout or access forbidden.\n{reply}",
        }

        reply = messages.get(status, reply)
        return reply

    async def get_params(self, message: discord.Message) -> tuple:
        """Get Gemini message params from a discord.Message."""
        extra_content = []

        # Remove prefix
        msg_text = message.content
        if message.content.startswith(CHATBOT_PREFIX):
            if self.status == 1:
                msg_text = msg_text[2:]
            else:
                msg_text = msg_text[1:]

        elif message.content.endswith(CHATBOT_PREFIX):
            msg_text = msg_text[:-1]

        # Process URLs in message body
        extra_content.extend(match[0] for match in link_grabber.findall(msg_text))

        # Process attachments
        for attachment in message.attachments:
            if attachment.url:
                extra_content.append(attachment.url)

        # Process stickers
        if message.stickers:
            sticker: discord.StickerItem = message.stickers[0]
            extra_content.append(sticker.url)

        # Process custom emojis
        match = re.search(r"<:(?P<name>[^:]+):(?P<snowflake>\d+)>", msg_text)
        if match:
            name = match.group("name")
            snowflake = match.group("snowflake")
            emote_full = match.group(0)

            # Replace the full emote with its name in the message
            msg_text = msg_text.replace(emote_full, f":{name}:")

            # Append the first emote to the image list
            extra_content.append(f"https://cdn.discordapp.com/emojis/{snowflake}.png")

        # Process message reference (if any)
        rauthor = rcontent = None
        if message.reference and message.reference.message_id:
            rid = message.reference.message_id
            rmessage = await message.channel.fetch_message(rid)
            rauthor = rmessage.author.global_name
            rcontent = rmessage.content
            urls = [
                attachment.url for attachment in rmessage.attachments if attachment.url
            ]
            extra_content.extend(urls)

        # Wrap parameters
        params = (
            msg_text,
            message.author.global_name,
            message.guild.id if message.guild else message.channel.id,
            extra_content,
            rauthor,
            rcontent,
            message.id,
        )
        return params

    @staticmethod
    def convert_emotes(msg: str, bot_emotes: dict = CHATBOT_EMOTES) -> str:
        """Convert and filter emotes in the message."""
        msg = msg.strip()
        # Find all emotes
        emotes = re.findall(r":(\w+):", msg)
        emote_count = len(emotes)

        for emote in emotes:
            # Do not remove the emote is the message is only this
            if emote_count == 1 and msg == f":{emote}:":
                replacement = bot_emotes.get(emote, "")
            else:
                if random() < CHATBOT_EMOTE_FREQUENCY:
                    replacement = bot_emotes.get(emote, "")
                else:
                    replacement = ""
            msg = msg.replace(f":{emote}:", replacement)

        # Remove double spaces
        msg = msg.replace("  ", " ")
        return msg

    @staticmethod
    def with_emotes(prompt: str, bot_emotes: dict = CHATBOT_EMOTES) -> str:
        """Add emotes the chatbot can use in a prompt."""
        # Don't add anything if there is no bot emotes
        if not bot_emotes:
            return prompt

        emote_prompt = "\n# Emotes\nYou can use the following discord emotes only at the end of a message.\n"
        emote_list = "\n".join([f":{emote}:" for emote in bot_emotes.keys()])
        final_prompt = prompt + emote_prompt + emote_list
        return final_prompt

    @staticmethod
    async def translate(
        query: str,
        language: str,
        nuance: str = "",
        model: genai.GenerativeModel = global_model,
    ) -> str:
        prompt = f"""
            Translate the following text to {nuance} {language}.
            If there is no text, return nothing.
            Don't change emoji strings (<:Example:1200797674031566958>).
            Don't add ANY extra text:
        """
        response = await Gembot.simple_prompt(query=prompt + query, model=model)
        return response
