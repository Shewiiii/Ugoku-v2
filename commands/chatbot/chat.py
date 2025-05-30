import logging

import discord
from discord.ext import commands

from config import GEMINI_ENABLED, CHATBOT_PREFIX
from google.genai.errors import APIError

if GEMINI_ENABLED:
    from bot.chatbot.chat_dataclass import ChatbotMessage
    from bot.chatbot.gemini import Gembot, active_chats
    from bot.utils import split_into_chunks
    from bot.config.sqlite_config_manager import get_whitelist

    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot: discord.Bot = bot

        @commands.slash_command(
            name="reset-chatbot",
            description=(
                "Reset the chatbot instance. "
                "Useful when the bot starts to become crazy."
            ),
            integration_types={
                discord.IntegrationType.guild_install,
                discord.IntegrationType.user_install,
            },
        )
        async def reset_chatbot(self, ctx: discord.ApplicationContext) -> None:
            id_ = Gembot.get_chat_id(ctx)
            if not id_ or id_ not in active_chats:
                await ctx.respond("Invalid or inactive chat !")
                return
            del active_chats[id_]
            await ctx.respond("Success !")

        @commands.Cog.listener()
        async def on_message(self, message: discord.Message) -> None:
            # Ignore if the message is from Ugoku !
            if message.author == self.bot.user:
                return

            id_ = Gembot.get_chat_id(message)
            if not id_:
                return

            # Variables relative to response generation
            dm = isinstance(message.channel, discord.DMChannel)
            premium_chat = (
                message.author.id in get_whitelist("premium_gemini_user_id") and dm
            )

            # Create/Use a chat
            if id_ not in active_chats:
                chat = Gembot(
                    id_,
                    ugoku_chat=True,
                    premium_chat=premium_chat,
                )
            chat: Gembot = active_chats.get(id_)

            # Neko arius
            p = CHATBOT_PREFIX
            low = message.content.lower()
            if any(low.startswith(neko) for neko in [f"{p}neko", f"{p} neko"]):
                await message.channel.send("Arius")
                return

            if not (
                await chat.interact(message, message.content, self.bot.user.id) or dm
            ):
                return

            async with message.channel.typing():
                params = await chat.get_params(message, message.content)
                try:
                    chatbot_message: ChatbotMessage = await chat.send_message(*params)
                except APIError as e:
                    await message.channel.send("*filtered*")
                    logging.error(
                        f"Response blocked by Gemini in {chat.id_}:{e.message}"
                    )
                    return

            # Add chat status, remove default emoticons
            formatted_response = chat.format_response(chatbot_message.response)
            chunked_message = split_into_chunks(formatted_response, 2000)

            # Max the number of successive message to 5
            first_msg = await message.channel.send(chunked_message[0])
            for i in range(1, min(len(chunked_message), 4)):
                await message.channel.send(chunked_message[i])

            # Send the sources if any
            if chatbot_message.sources:
                source_chunks = split_into_chunks(chatbot_message.sources)
                for chunk in source_chunks:
                    await message.channel.send(chunk)

            # Memory
            # if await chat.memory.store(chatbot_message):
            if await chat.memory.store(chat.history):
                await first_msg.edit(
                    f"-# Ugoku will remember about this. \n{chunked_message[0]}"
                )
else:

    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot


def setup(bot):
    bot.add_cog(Chatbot(bot))
