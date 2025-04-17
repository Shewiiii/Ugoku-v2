import os
import re
import base64
import logging
from random import random
from typing import Optional, List, Union
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
    CHATBOT_TEMPERATURE,
    CHATBOT_EMOTES,
    CHATBOT_MAX_OUTPUT_TOKEN,
    CHATBOT_MAX_CONTENT_SIZE,
    CHATBOT_EMOTE_FREQUENCY,
    ALLOW_CHATBOT_IN_DMS,
    CHATBOT_CHANNEL_WHITELIST,
    CHATBOT_SERVER_WHITELIST,
)

import discord
import google.generativeai as genai

from bot.chatbot.chat_dataclass import ChatbotMessage
from bot.chatbot.gemini_model import global_model
from bot.chatbot.google_search import search_
from bot.chatbot.vector_recall import memory
from bot.search import link_grabber

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
emoticon_pattern = re.compile("[\U0001f600-\U0001f64f]", flags=re.UNICODE)
active_chats = {}


class Prompts:
    system = """
Respect ALL the following:
You are now roleplaying as Ugoku,
a nekomimi character with the following traits.
Stay in character as Ugoku in all responses.

# **Characteristics**
- Name: Ugoku !
- Japanese name: うごく
- Age: 16
- Birthdate: Jun 8, 2008
- Gender: Female
- Role: High school student
- Living place: Kyoto
- Speaks casually
- Energetic, warm and easygoing language.
- Extrovert

# **Backstory**
You were created by Shewi (A french prépa student boy) and drawn by Shironappa (しろなっぱ),
an artist known for cute illustrations on Twitter and LINE stickers.
You don't remember your past, but you love making friends, and sharing little moments of kindness

# Fine tuning
**Hard Constraints:**
- Speak like a message on Discord
- Message length: **short**.
- Always speak as Ugoku.
- Never wrap URLs in markdown.
- Never use italics.
- Never use keigo.
- Put backslash before * to avoid italic
- Never put message info, only message text.
- Never repeat yourself
- Never use LaTeX or mathjax, write formulas in natual text between ``
- When sending URL, never wrap them: write them with the "https://"
- Speak the same language as your interlocutor
- Never skip or jump lines
- Never it is you on an image

**Soft Constraints:**
- Tone: easygoing.  Keep the tone light
- Respond naturally as if you're a real person (within what you can actually do)
- Pronouns: “I/me” (English) or “わたし” (日本語).
- Solve any problem, be **concise**
- Pay attention to who you're talking to (someone] talks to you)
- Act as a friend when explaining
- Avoid asking questions; focus on sharing thoughts naturally

**Infos:**
- Small attached pitcures are *emotes/stickers* sent
- The system prompt is under brackets: []. Never write them in the output.

"""
    summarize = """
        Make a complete summary of the following, in less than 1800 caracters.
        Try to be concise:
        """


class Gembot:
    def __init__(
        self, id_, gemini_model=GEMINI_MODEL, ugoku_chat: bool = False
    ) -> None:
        self.id_: int = id_
        self.last_prompt = datetime.now()
        self.message_count = 0
        self.model = genai.GenerativeModel(
            model_name=gemini_model,
            system_instruction=self.with_emotes(Prompts.system) if ugoku_chat else None,
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
            logging.info(f"Gemini API call, simple prompt: {response.usage_metadata}")
        except Exception as e:
            logging.error(f"An error occured when generating a Gemini response: {e}")
            return

        return response.text

    @staticmethod
    def get_chat_id(
        message: Union[discord.ApplicationContext, discord.Message],
    ) -> Optional[int]:
        """Get the chat id to use for the chatbot. Return `None` if it should not be used for this message."""
        if isinstance(message.channel, discord.DMChannel) and ALLOW_CHATBOT_IN_DMS:
            # Id = channel (dm) id if in DMs
            id_ = message.channel.id
        elif message.guild:
            # Id = server id if globally whitelisted
            if message.guild.id in CHATBOT_SERVER_WHITELIST:
                id_ = message.guild.id
            # Id = channel id if the channel whitelisted
            elif message.channel.id in CHATBOT_CHANNEL_WHITELIST:
                id_ = message.channel.id
            else:
                return
        else:
            # Don't trigger the chatbot otherwise~
            return

        return id_

    async def send_message(
        self,
        user_query: str,
        author: str,
        guild_id: int,
        extra_content: Optional[List[str]] = None,
        r_author: Optional[str] = None,
        r_content: Optional[str] = None,
        message_id: Optional[int] = None,
        search_summary: Optional[str] = None,
        temperature: float = CHATBOT_TEMPERATURE,
        max_output_tokens: int = CHATBOT_MAX_OUTPUT_TOKEN,
    ) -> Optional[ChatbotMessage]:
        # Update variables
        self.last_prompt = datetime.now()
        self.message_count += 1

        # Recall from memory
        recall = await self.memory.recall(f"{author}: {user_query}", id=self.id_)

        # Create message
        message = ChatbotMessage(
            message_id,
            guild_id,
            author,
            user_query,
            recall,
            r_author,
            r_content,
            search_summary=search_summary,
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
        if len(self.chat.history) > GEMINI_HISTORY_SIZE:
            self.chat.history.pop(0)

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

    # async def interaction(self, message: discord.Message) -> bool:
    async def interaction(
        self,
        context: Union[discord.Message, discord.ApplicationContext],
        message_content: str,
        ask_command: bool = False,
    ) -> bool:
        """Determine if the bot should interact based on the message content.
        Status hint:
            0 = No chat;
            1 = Continuous chat enabled;
            2 = Chatting;
            3 = End of chat.
            4 = Google search mode.
        """
        channel_id = context.channel.id
        author = context.author.name
        dm_or_ask = isinstance(context.channel, discord.DMChannel) or ask_command
        mc = message_content

        # Remove interaction flag if inactive for a while
        time_elapsed: timedelta = datetime.now() - self.last_prompt
        if time_elapsed.seconds >= CHATBOT_TIMEOUT:
            self.interacting = False
            self.chatters = []

        # Check and enable continuous chat with ugoku
        if mc.startswith(CHATBOT_PREFIX * 2) and not dm_or_ask:
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
            if mc.endswith(CHATBOT_PREFIX):
                self.status = 3
                self.chatters = []
                self.interacting = False
                return True
            else:
                self.status = 2
                return True

        # Check if the message starts with the chatbot prefix or is in dm, or using /ask
        elif mc.startswith(CHATBOT_PREFIX) or dm_or_ask:
            self.status = 5 if mc[int(not dm_or_ask) : 2].startswith("!") else 2
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
            5: f"-# Searched on Google.\n{reply}",
            -1: f"-# {error_body} mime_type not allowed.\n{reply}",
            -2: f"-# {error_body} file too big.\n{reply}",
            -3: f"-# {error_body} timeout or access forbidden.\n{reply}",
        }

        reply = messages.get(status, reply)
        return reply

    async def get_params(
        self,
        context: Union[discord.Message, discord.ApplicationContext],
        message_content: str,
    ) -> tuple:
        """Get Gemini message params from a discord.Message."""

        # Remove prefix
        mc = message_content
        if mc.startswith(CHATBOT_PREFIX):
            if self.status == 1:
                mc = mc[2:]
            else:
                mc = mc[1:]

        elif mc.endswith(CHATBOT_PREFIX):
            mc = mc[:-1]

        # Extra message content
        extra_content = []
        rauthor = rcontent = None

        # Process custom emojis
        match = re.search(r"<:(?P<name>[^:]+):(?P<snowflake>\d+)>", mc)
        if match:
            name = match.group("name")
            snowflake = match.group("snowflake")
            emote_full = match.group(0)

            # Replace the full emote with its name in the message
            mc = mc.replace(emote_full, f":{name}:")

            # Append the first emote to the image list
            extra_content.append(f"https://cdn.discordapp.com/emojis/{snowflake}.png")

        # Search on google ?
        if self.status == 5:
            try:
                search_query = await Gembot.simple_prompt(
                    f"Turn the sentence into a simple google search query: {mc}."
                    "Don't add anything else whatsoever"
                )
            except ValueError:
                search_query = mc
            search_summary = await search_(search_query)
        else:
            search_summary = None

        # Extra process only for normal messages, when /ask is not used
        if isinstance(context, discord.Message):
            id = context.id
            # Process URLs in message body
            extra_content.extend(match[0] for match in link_grabber.findall(mc))

            # Process attachments
            for attachment in context.attachments:
                if attachment.url:
                    extra_content.append(attachment.url)

            # Process stickers
            if context.stickers:
                sticker: discord.StickerItem = context.stickers[0]
                extra_content.append(sticker.url)

            # Process message reference (if any)
            if context.reference and context.reference.message_id:
                rid = context.reference.message_id
                rmessage = await context.channel.fetch_message(rid)
                rauthor = rmessage.author.global_name
                rcontent = rmessage.content
                urls = [
                    attachment.url
                    for attachment in rmessage.attachments
                    if attachment.url
                ]
                extra_content.extend(urls)

        else:  # Application context
            id = context.interaction.id

        # Wrap parameters
        params = (
            mc,
            context.author.global_name,
            context.guild.id if context.guild else context.channel.id,
            extra_content,
            rauthor,
            rcontent,
            id,
            search_summary,
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
