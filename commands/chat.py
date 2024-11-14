import logging

import discord
from discord.ext import commands

from config import (
    CHATBOT_WHITELIST,
    CHATBOT_ENABLED,
    GEMINI_UTILS_MODEL
)
import google.generativeai as genai

from google.generativeai.types.generation_types import (
    BlockedPromptException,
    StopCandidateException
)

if CHATBOT_ENABLED:
    from bot.chatbot.gemini import Gembot, active_chats

    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot

        @commands.Cog.listener()
        async def on_message(self, message: discord.Message) -> None:
            server = message.guild
            if not server:
                return
            server_id = server.id

            # Only allow whitelisted servers
            if not server_id in CHATBOT_WHITELIST:
                return

            # Ignore if the message is from Ugoku !
            if message.author == self.bot.user:
                return

            # Create/Use a chat
            if server_id not in active_chats:
                chat = Gembot(server_id)
            chat = active_chats.get(server_id)

            # Neko arius
            lowered_msg = message.content.lower()
            if any(lowered_msg.startswith(neko)
                   for neko in ['-neko', '- neko']):
                await message.channel.send('Arius')
                return

            if await chat.is_interacting(message):
                async with message.channel.typing():
                    params = await chat.get_params(message)
                    try:
                        reply = await chat.send_message(*params)
                    except StopCandidateException:
                        await message.channel.send("*filtered*")
                        logging.error(
                            f"Response blocked by Gemini in {chat.id_}")
                        return
                    except BlockedPromptException:
                        logging.error(
                            "Prompt against Gemini's policies! "
                            "Please change it and try again."
                        )
                        return

                    # Add chat status, remove default emoticons
                    formatted_reply = chat.format_reply(reply)
                await message.channel.send(formatted_reply)

                # Memory
                await chat.memory.store(
                    params[0],
                    author=message.author.global_name,
                    id=server_id,
                )
else:
    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot


def setup(bot):
    bot.add_cog(Chatbot(bot))
