from discord.ext import commands
import discord

from config import OPENAI_ENABLED, GEMINI_ENABLED, GEMINI_MODEL_DISPLAY_NAME, OPENAI_MODEL_DISPLAY_NAME

if GEMINI_ENABLED:
    from bot.chatbot.gemini import Gembot, active_chats


class SwitchChatbotService(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @discord.slash_command(
        name="switch-chatbot-service",
        description="Switch the service to use for the chatbot (Openai or Gemini).",
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

        id_ = Gembot.get_chat_id(ctx, gemini_command=True)
        if not id_:
            await ctx.respond(
                "This channel or server is not allowed to use that command.",
                ephemeral=True
            )
            return

        # Create/Use a chat
        if id_ not in active_chats:
            chat = Gembot(id_, ugoku_chat=True)
        chat: Gembot = active_chats.get(id_)

        if chat.default_api == "openai":
            chat.default_api = "gemini"
            chat.current_model_dn = GEMINI_MODEL_DISPLAY_NAME
        else:
            chat.default_api = "openai"
            chat.current_model_dn = OPENAI_MODEL_DISPLAY_NAME

        await ctx.respond(
            f"Switched the chatbot service to {chat.default_api.capitalize()}"
        )


def setup(bot):
    bot.add_cog(SwitchChatbotService(bot))
