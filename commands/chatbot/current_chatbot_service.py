from discord.ext import commands
import discord

from config import OPENAI_ENABLED, GEMINI_ENABLED

if GEMINI_ENABLED:
    from bot.chatbot.gemini import Gembot, active_chats


class CurrentChatbotService(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @discord.slash_command(
        name="current-chatbot-service",
        description="Check what service and model the chatbot is using.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def switch_model(self, ctx: discord.ApplicationContext) -> None:
        if not GEMINI_ENABLED:
            await ctx.respond("Chatbot features are not enabled.")
            return

        if not OPENAI_ENABLED:
            await ctx.respond("The chatbot is only using Gemini.")
            return

        id_ = Gembot.get_chat_id(ctx, ask_command=True)
        if not id_:
            await ctx.respond(
                "This channel or server is not allowed to use that command."
            )
            return

        # Create/Use a chat
        if id_ not in active_chats:
            chat = Gembot(id_, ugoku_chat=True)
        chat: Gembot = active_chats.get(id_)

        await ctx.respond(
            f"In the current chat, Ugoku is using **{chat.default_api.capitalize()}** "
            f"by default with the model **{chat.current_model_dn}**.",
            ephemeral=True,
        )


def setup(bot):
    bot.add_cog(CurrentChatbotService(bot))
