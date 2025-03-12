import logging

import discord
from discord.ext import commands

from config import (
    CHATBOT_WHITELIST,
    GEMINI_ENABLED,
    ALLOW_CHATBOT_IN_DMS,
    CHATBOT_PREFIX,
)
from google.generativeai.types.generation_types import (
    BlockedPromptException,
    StopCandidateException,
)

if GEMINI_ENABLED:
    from bot.chatbot.gemini import Gembot, active_chats
    from bot.utils import split_into_chunks

    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot

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
            channel = ctx.channel
            dm = isinstance(channel, discord.DMChannel)
            Gembot(ctx.guild_id if not dm else channel.id)
            await ctx.respond("Success !")

        @commands.Cog.listener()
        async def on_message(self, message: discord.Message) -> None:
            dm = isinstance(message.channel, discord.DMChannel)
            server = message.guild
            if not server and not dm:
                return

            id_ = server.id if server else message.channel.id

            # Only allow whitelisted servers / dms if enabled
            if (not dm and id_ not in CHATBOT_WHITELIST) or (
                dm and not ALLOW_CHATBOT_IN_DMS
            ):
                return

            # Ignore if the message is from Ugoku !
            if message.author == self.bot.user:
                return

            # Create/Use a chat
            if id_ not in active_chats:
                chat = Gembot(id_)
            chat = active_chats.get(id_)

            # Neko arius
            p = CHATBOT_PREFIX
            low = message.content.lower()
            if any(low.startswith(neko) for neko in [f"{p}neko", f"{p} neko"]):
                await message.channel.send("Arius")
                return

            if await chat.is_interacting(message) or dm:
                async with message.channel.typing():
                    params = await chat.get_params(message)
                    try:
                        reply = await chat.send_message(*params)
                    except StopCandidateException:
                        await message.channel.send("*filtered*")
                        logging.error(f"Response blocked by Gemini in {chat.id_}")
                        return
                    except BlockedPromptException:
                        logging.error(
                            "Prompt against Gemini's policies! "
                            "Please change it and try again."
                        )
                        return

                    # Add chat status, remove default emoticons
                    formatted_reply = chat.format_reply(reply)
                chunked_message = split_into_chunks(formatted_reply, 2000)
                # Max the number of successive message to 5
                for i in range(min(len(chunked_message), 5)):
                    if i == 0:
                        first_msg = await message.channel.send(chunked_message[i])

                # Memory
                if await chat.memory.store(
                    params[0],
                    author=message.author.global_name,
                    id=id_,
                ):
                    await first_msg.edit(
                        f"-# Ugoku will remember about this. \n{chunked_message[-1]}"
                    )
else:

    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot


def setup(bot):
    bot.add_cog(Chatbot(bot))
