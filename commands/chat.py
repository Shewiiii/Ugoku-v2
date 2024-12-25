import logging

import discord
from discord.ext import commands

from config import (
    CHATBOT_WHITELIST,
    CHATBOT_ENABLED,
    ALLOW_CHATBOT_IN_DMS
)
from google.generativeai.types.generation_types import (
    BlockedPromptException,
    StopCandidateException
)

if CHATBOT_ENABLED:
    from bot.chatbot.gemini import Gembot, active_chats

    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot

        @commands.slash_command(
            name="reset_chatbot",
            description=(
                "Reset the chatbot instance. "
                "Useful when the bot starts to become crazy."
            ),
            integration_types={
                discord.IntegrationType.guild_install,
                discord.IntegrationType.user_install
            }
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
            if (not dm and id_ not in CHATBOT_WHITELIST) or (dm and not ALLOW_CHATBOT_IN_DMS):
                return

            # Ignore if the message is from Ugoku !
            if message.author == self.bot.user:
                return

            # Create/Use a chat
            if id_ not in active_chats:
                chat = Gembot(id_)
            chat = active_chats.get(id_)

            # Neko arius
            lowered_msg = message.content.lower()
            if any(lowered_msg.startswith(neko) for neko in ['-neko', '- neko']):
                await message.channel.send('Arius')
                return

            if await chat.is_interacting(message) or dm:
                async with message.channel.typing():
                    params = await chat.get_params(message)
                    try:
                        reply = await chat.send_message(*params)
                    except StopCandidateException:
                        await message.channel.send("*filtered*")
                        logging.error(
                            f"Response blocked by Gemini in {chat.id}")
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
                    id=id_,
                )
else:
    class Chatbot(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot


def setup(bot):
    bot.add_cog(Chatbot(bot))
