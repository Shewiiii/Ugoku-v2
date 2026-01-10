from aiohttp_client_cache import CachedSession, SQLiteBackend
from aiohttp import ClientResponseError
import asyncio
import os
import re
import logging
from openai import AsyncOpenAI, BadRequestError
from random import random
from typing import Optional, List, Union, Literal
from datetime import datetime, timedelta
from config import (
    GEMINI_MODEL,
    GEMINI_SAFETY_SETTINGS,
    CHATBOT_HISTORY_SIZE,
    GEMINI_ENABLED,
    CHATBOT_TIMEOUT,
    CHATBOT_PREFIX,
    GEMINI_PREFIX,
    CHATBOT_TEMPERATURE,
    CHATBOT_MAX_OUTPUT_TOKEN,
    CHATBOT_MAX_CONTENT_SIZE,
    CHATBOT_EMOTE_FREQUENCY,
    ALLOW_CHATBOT_IN_DMS,
    CACHE_EXPIRY,
    PINECONE_RECALL_WINDOW,
    OPENAI_ENABLED,
    OPENAI_MODEL,
    PINECONE_INDEX_NAME,
    GEMINI_MODEL_DISPLAY_NAME,
    OPENAI_MODEL_DISPLAY_NAME,
    PINECONE_ENABLED,
)
import urllib3

import discord
from google.genai import types, errors
from google.genai.types import Tool, GoogleSearch

from bot.chatbot.chat_dataclass import ChatbotMessage, ChatbotHistory
from bot.chatbot.gemini_client import client, utils_models_manager
from bot.chatbot.prompts import Prompts
from bot.chatbot.vector_recall import memory
from bot.config.sqlite_config_manager import get_all_chatbot_emotes, get_whitelist


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
emoticon_pattern = re.compile("[\U0001f600-\U0001f64f]", flags=re.UNICODE)
google_search_tool = Tool(google_search=GoogleSearch())


class Gembot:
    def __init__(
        self,
        id_,
        gemini_model=GEMINI_MODEL,
        ugoku_chat: bool = False,
    ) -> None:
        self.id_: int = id_
        self.last_prompt = datetime.now()
        active_chats[id_] = self

        if ugoku_chat:
            # Chat emotes
            current_bot_emotes = get_all_chatbot_emotes()
            system_prompt_text = Gembot.with_emotes(
                Prompts.system, bot_emotes=current_bot_emotes
            )

            chat_client = client
            chat_model = gemini_model
            self.current_model_dn = (
                OPENAI_MODEL_DISPLAY_NAME
                if OPENAI_ENABLED
                else GEMINI_MODEL_DISPLAY_NAME
            )
            self.default_api = "openai" if OPENAI_ENABLED else "gemini"

            # Create the chat
            self.chat = chat_client.aio.chats.create(
                model=chat_model,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt_text,
                    candidate_count=1,
                    temperature=CHATBOT_TEMPERATURE,
                    max_output_tokens=CHATBOT_MAX_OUTPUT_TOKEN,
                    safety_settings=GEMINI_SAFETY_SETTINGS,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                    tools=[google_search_tool] if ugoku_chat else [],
                    thinking_config=types.ThinkingConfig(include_thoughts=False),
                ),
            )
            self.status = 0
            self.interacting = False
            self.chatters = []
            self.memory = memory
            self.history = ChatbotHistory(id_)
            self.openai = (
                AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_ENABLED else None
            )
            self.message_count = 0

    @staticmethod
    async def simple_prompt(
        query: str,
        model: Optional[str] = None,
        temperature: float = 1.0,
        max_output_tokens: int = CHATBOT_MAX_OUTPUT_TOKEN,
    ) -> Optional[str]:
        try:
            model = utils_models_manager.pick()
            response: types.GenerateContentResponse = (
                await client.aio.models.generate_content(
                    model=model,
                    contents=query,
                    config=types.GenerateContentConfig(
                        candidate_count=1,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        safety_settings=GEMINI_SAFETY_SETTINGS,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                    ),
                )
            )
            logging.info(
                f"Gemini API call, simple prompt: {
                    response.usage_metadata.total_token_count
                } tokens"
            )
        except errors.APIError as e:
            if e.code == 429:
                utils_models_manager.add_down_model(model)
                return await Gembot.simple_prompt(
                    query, None, temperature, max_output_tokens
                )
            logging.error(f"An error occured when generating a Gemini response: {e}")
            return
        except RuntimeError as e:
            if str(e) == "No more model available":
                return "Resource exhausted: please try again in a few minutes."

        return response.text

    @staticmethod
    def get_chat_id(
        message: Union[discord.ApplicationContext, discord.Message],
        gemini_command: bool = False,
    ) -> Optional[int]:
        """Get the chat id to use for the chatbot. Return `None` if it should not be used for this message."""
        if not GEMINI_ENABLED:
            return

        chatbot_ids = get_whitelist("chatbot_ids")

        if (
            isinstance(message.channel, discord.DMChannel)
            and ALLOW_CHATBOT_IN_DMS
            or message.channel.id in chatbot_ids
        ):
            # Id = channel (dm) id if in DMs
            return message.channel.id

        elif message.guild:
            # Id = server id if the server is globally whitelisted
            # Fetch whitelists from DB

            gemini_servers = get_whitelist("gemini_servers")
            should_respond = (
                message.guild.id in chatbot_ids
                or gemini_command
                and message.guild.id in gemini_servers
            )

            if should_respond:
                return message.guild.id

    async def send_message(
        self,
        user_query: str,
        author: str,
        guild_id: int,
        urls: Optional[List[str]] = None,
        r_author: Optional[str] = None,
        r_content: Optional[str] = None,
        message_id: Optional[int] = None,
        api: str = "openai" if OPENAI_ENABLED else "gemini",
    ) -> Optional[ChatbotMessage]:
        # Update variables
        self.last_prompt = datetime.now()
        self.message_count += 1

        # Recall from memory
        # Remove already prompted vectors + default value
        recall_vectors = []
        if PINECONE_ENABLED:
            try:
                results: list = await self.memory.get_vectors(
                    f"{author}: {user_query}", id=self.id_, top_k=PINECONE_RECALL_WINDOW
                )
                for v in results:
                    if v["id"] not in self.history.recalled_vector_ids:
                        recall_vectors.append(v)
            except urllib3.exceptions.ProtocolError:
                logging.error(
                    "Pinecone: An existing connection was forcibly closed by the remote host. "
                    "Restarting Pinecone..."
                )
                await memory.init_pinecone(PINECONE_INDEX_NAME)

        # Create message
        message = ChatbotMessage(
            message_id,
            guild_id,
            author,
            user_query,
            recall_vectors,
            r_author,
            r_content,
            urls=urls,
        )

        prompt = message.prompt()
        parts = await self.request_chat_response(
            message, prompt=prompt, urls=urls, api=api
        )

        # Add to (custom) history if successful
        self.history.store_recall(recall_vectors)
        self.history.add(message)
        if api == "openai":
            self.history.add_openai_assistant_response(message.response)
            # Add to Gemini history as well
            user_input = types.Content(parts=parts, role="user")
            model_output = types.Content(
                parts=[types.Part(text=message.response)], role="model"
            )
            self.chat.record_history(
                user_input=user_input,
                model_output=[model_output],
                automatic_function_calling_history=[],
                is_valid=True,
            )
            self.limit_gemini_history()

        return message

    def limit_gemini_history(self):
        while len(self.chat._curated_history) > CHATBOT_HISTORY_SIZE * 2:
            self.chat._curated_history.pop(0)

    async def request_chat_response(
        self,
        chatbot_message: ChatbotMessage,
        prompt: str,
        urls: Optional[list] = None,
        api: Literal["gemini", "openai"] = "gemini",
    ) -> list[types.Part]:
        """Add a response to a given message based on the current message history.
        urls is a list of URLs. Return a list of parts."""
        chatbot_message.response = "*filtered*"  # By default
        parts = [types.Part(text=prompt)]
        if urls:
            for url in urls:
                part = await self.get_part_from_url(url)
                if part:
                    parts.append(part)

        if api == "gemini":
            response = await self.chat.send_message(parts)
            if response.text:
                chatbot_message.response = response.text
            logging.info(
                f"Gemini API call, total token count: {response.usage_metadata.total_token_count}."
                f" Prompt: {prompt}".replace("\n", ", ")
            )

            # Sources at the end of message
            # The checks needed are so stupid
            sources = []
            if (
                response.candidates
                and response.candidates[0].grounding_metadata
                and response.candidates[0].grounding_metadata.grounding_chunks
            ):
                sources = [
                    f"[{chunk.web.title}](<{chunk.web.uri}>)"
                    for chunk in response.candidates[
                        0
                    ].grounding_metadata.grounding_chunks
                    if chunk.web
                ]
            if sources:
                chatbot_message.sources = "\n> -# Sources\n" + "\n".join(
                    [f"> -# {source}" for source in sources]
                )

            # Limit history length
            self.limit_gemini_history()

        elif api == "openai":  # Text and images supported only
            if not self.openai:
                raise ValueError("OpenAI not enabled")

            openai_input = self.history.create_openai_input(prompt, urls)
            try:
                response = await self.openai.responses.create(
                    instructions=self.with_emotes(Prompts.system),
                    model=OPENAI_MODEL,
                    input=openai_input,
                )
                chatbot_message.response = response.output_text
            except BadRequestError as e:
                if e.status_code == 400:
                    logging.error(repr(e))
                    # Incompatible file, retry without URLs
                    self.status = -1
                    chatbot_message.urls = None
                    return await self.request_chat_response(
                        chatbot_message,
                        prompt,
                        api="openai",
                    )

                logging.error(repr(e))

        return parts

    async def get_part_from_url(self, url: str) -> Optional[types.Part]:
        """Returns a dict containing the base64 bytes data and the mime_type from an URL."""
        try:
            async with CachedSession(
                follow_redirects=True,
                cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
            ) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    mime_type = response.headers.get("content-type", "")
                    # E.g: audio, text..
                    content_type = mime_type.split("/")[0]
                    max_size = CHATBOT_MAX_CONTENT_SIZE.get(content_type, 0)

                    if content_type in ["image", "audio", "application"]:
                        content = await response.read()

                    else:
                        self.status = -1
                        logging.warning(
                            f"{url} has not been processed: mime_type not allowed"
                        )
                        return

                # Size check
                if len(content) > max_size:
                    self.status = -2
                    logging.warning(f"{url} has not been processed: File too big")
                    return

                part = types.Part.from_bytes(data=content, mime_type=mime_type)
                return part

        except (ClientResponseError, asyncio.TimeoutError):
            self.status = -3
            logging.warning(
                f"{url} has not been processed due to timeout or incompatibility"
            )
            return

        except Exception as e:
            logging.error(f"Error processing {url}: {e}")
            return

    async def interact(
        self,
        context: Union[discord.Message, discord.ApplicationContext],
        message_content: str,
        bot_user_id: int,
        ask_command: bool = False,
    ) -> bool:
        """Determine if the bot should interact based on the message content, and update the chat status.
        Status hint:
            0 = No chat;
            1 = Continuous chat enabled;
            2 = Chatting;
            3 = End of chat;
            4 = New chat.
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

        # Check if the message starts with the chatbot prefix, is in dm, using /ask,
        # or pings the bot (<@...>)
        elif (
            mc.startswith(CHATBOT_PREFIX)
            or dm_or_ask
            or re.search(rf"<@!?{bot_user_id}>", mc)
        ):
            # Determine which model to use
            use_openai = (
                OPENAI_ENABLED
                and not mc.startswith(f"{CHATBOT_PREFIX}{GEMINI_PREFIX}")
                and not self.default_api == "gemini"
            )
            selected_model_dn = (
                OPENAI_MODEL_DISPLAY_NAME if use_openai else GEMINI_MODEL_DISPLAY_NAME
            )

            # If the model has changed or there is no history, notify what model is used
            if self.current_model_dn != selected_model_dn or not self.history.messages:
                self.status = 4
                self.current_model_dn = selected_model_dn
            # Don't otherwise
            else:
                self.status = 2

            self.current_channel_id = channel_id
            return True

        return False

    def format_response(self, reply: str) -> str:
        """Format the reply based on the current status."""
        # Remove double skip lines
        parts = re.split(r"(```[\s\S]*?```)", reply)
        for i, part in enumerate(parts):
            if not part.startswith("```"):
                parts[i] = re.sub(r"\n{2,}", "\n", part)
        reply = "".join(parts)

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
            4: f"-# Using {self.current_model_dn}.\n{reply}",
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
        api: Optional[Literal["gemini", "openai"]] = None,
    ) -> tuple:
        """Get Gemini message params from a discord.Message."""
        mc = message_content
        starts_with_gemini_prefix = mc.startswith(f"{CHATBOT_PREFIX}{GEMINI_PREFIX}")

        # api
        if not api:
            if OPENAI_ENABLED and starts_with_gemini_prefix:
                api = "gemini"
            else:
                api = self.default_api

        # Remove prefix
        if mc.startswith(CHATBOT_PREFIX):
            if self.status == 1 or starts_with_gemini_prefix:
                mc = mc[2:]
            else:
                mc = mc[1:]

        elif mc.endswith(CHATBOT_PREFIX):
            mc = mc[:-1]

        # Extra message content
        urls = []
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
            urls.append(f"https://cdn.discordapp.com/emojis/{snowflake}.png")

        # Extra process only for normal messages, when /ask is not used
        if isinstance(context, discord.Message):
            id = context.id

            # Process attachments
            for attachment in context.attachments:
                if attachment.url:
                    urls.append(attachment.url)

            # Process stickers
            if context.stickers:
                sticker: discord.StickerItem = context.stickers[0]
                urls.append(sticker.url)

            # Process message reference (if any)
            if context.reference and context.reference.message_id:
                rid = context.reference.message_id
                rmessage = await context.channel.fetch_message(rid)
                rauthor = rmessage.author.global_name or rmessage.author.name
                rcontent = rmessage.content
                urls = [
                    attachment.url
                    for attachment in rmessage.attachments
                    if attachment.url
                ]
                urls.extend(urls)

        else:  # Application context
            id = context.interaction.id

        # Wrap parameters
        params = (
            mc,
            context.author.global_name,
            context.guild.id if context.guild else context.channel.id,
            urls,
            rauthor,
            rcontent,
            id,
            api,
        )

        return params

    @staticmethod
    def convert_emotes(msg: str, bot_emotes: Optional[dict] = None) -> str:
        """Convert and filter emotes in the message."""
        if bot_emotes is None:
            bot_emotes = get_all_chatbot_emotes()

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
    def with_emotes(prompt: str, bot_emotes: Optional[dict] = None) -> str:
        """Add emotes the chatbot can use in a prompt."""
        if bot_emotes is None:
            bot_emotes = get_all_chatbot_emotes()

        # Don't add anything if there is no bot emotes
        if not bot_emotes:
            return prompt

        emote_prompt = (
            "# Emotes\n"
            "Occasionally, you can only use the following discord emotes, "
            "only at the end of a message.\n"
        )
        emote_list = "\n".join([f":{emote}:" for emote in bot_emotes.keys()])
        final_prompt = prompt + emote_prompt + emote_list
        return final_prompt

    @staticmethod
    async def translate(
        query: str,
        language: str,
        nuance: str = "",
    ) -> str:
        prompt = f"""
            Translate the following text to {nuance} {language}.
            If there is no text, return nothing.
            Don't change emoji strings (<:Example:1200797674031566958>).
            Don't add ANY extra text:
        """
        response = await Gembot.simple_prompt(query=prompt + query)
        return response


active_chats: dict[int, Gembot] = {}
