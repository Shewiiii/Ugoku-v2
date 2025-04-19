import asyncio
import discord
import logging
from discord.ext import commands
from config import GEMINI_ENABLED
from google.genai.errors import APIError

if GEMINI_ENABLED:
    from bot.chatbot.chat_dataclass import ChatbotMessage
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
        self, ctx: discord.ApplicationContext, query: str, ephemeral: bool = False
    ) -> None:
        if not GEMINI_ENABLED:
            await ctx.respond("Chatbot features are not enabled.")
            return

        id_ = Gembot.get_chat_id(ctx)
        if not id_:
            await ctx.respond(
                "This channel or server is not allowed to use that command."
            )
            return

        defer_task = asyncio.create_task(ctx.defer(ephemeral=ephemeral))

        # Create/Use a chat
        if id_ not in active_chats:
            chat = Gembot(id_, ugoku_chat=True)
        chat: Gembot = active_chats.get(id_)

        # Remove continuous chat notice (if enabled the msg before)
        if chat.status == 1:
            chat.status = 2

        # Create response
        await chat.interaction(ctx, query, ask_command=True)
        params = await chat.get_params(ctx, query)
        try:
            chatbot_message: ChatbotMessage = await chat.send_message(*params)

        except APIError as e:
            defer_task.cancel()
            await ctx.respond("*filtered*", ephemeral=ephemeral)
            logging.error(f"Response blocked by Gemini in {chat.id_}: {e.message}")
            return

        # Response
        formatted_response = chat.format_response(chatbot_message.response)
        formatted_reply = f"-# {ctx.author.name}: {query}\n{formatted_response}"
        tasks = []
        tasks.append(ctx.respond(formatted_reply, ephemeral=ephemeral))
        tasks.append(chat.memory.store(chat.history))
        defer_task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def setup(bot):
    bot.add_cog(Ask(bot))
