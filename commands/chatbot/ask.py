import asyncio
import discord
import logging
from discord.ext import commands
from config import CHATBOT_WHITELIST, GEMINI_ENABLED
from google.generativeai.types.generation_types import BlockedPromptException

if GEMINI_ENABLED:
    from bot.chatbot.gemini import Gembot, active_chats


class Ask(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="ask",
        description="Ask Ugoku anything !",
        integration_types={
            discord.IntegrationType.user_install,
            discord.IntegrationType.guild_install,
        },
    )
    async def ask(
        self, ctx: discord.ApplicationContext, query: str, ephemeral: bool = True
    ) -> None:
        guild_id = ctx.guild.id
        author_name = ctx.author.global_name

        if not GEMINI_ENABLED:
            await ctx.respond("Chatbot features are not enabled.")
            return
        if ctx.guild.id not in CHATBOT_WHITELIST:
            await ctx.respond("This server is not allowed to use that command.")
            return

        asyncio.create_task(ctx.defer())

        # Create/Use a chat
        if guild_id not in active_chats:
            chat = Gembot(guild_id)
        chat = active_chats.get(guild_id)

        # Remove continuous chat notice (if enabled the msg before)
        if chat.status == 1:
            chat.status = 2

        # Create response
        try:
            reply = await chat.send_message(user_query=query, author=author_name)

        except BlockedPromptException:
            await ctx.respond("*filtered*", ephemeral=ephemeral)
            logging.error(f"Response blocked by Gemini in {chat.id_}")
            return

        except BlockedPromptException:
            logging.error(
                "Prompt against Gemini's policies! Please change it and try again."
            )
            return

        # Response
        formatted_reply = f"-# {author_name}: {query}\n{chat.format_reply(reply)}"
        asyncio.create_task(ctx.respond(formatted_reply, ephemeral=ephemeral))

        # Memory
        await chat.memory.store(query, author=author_name, id=guild_id)


def setup(bot):
    bot.add_cog(Ask(bot))
