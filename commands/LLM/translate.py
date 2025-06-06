import asyncio
import discord
from discord.ext import commands
from config import LANGUAGES, GEMINI_ENABLED

if GEMINI_ENABLED:
    from bot.chatbot.gemini import Gembot


class Translate(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="translate",
        description="Translate any sentence to a language.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def translate(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, description="The message to translate"),  # type: ignore
        language: discord.Option(
            str,
            choices=LANGUAGES,
            required=True,
            default="English",
            description="The language to use",
        ),  # type: ignore
        nuance: discord.Option(
            str,
            choices=["Neutral", "Casual", "Formal"],
            required=True,
            default="Neutral",
            description="The style of the translation",
        ),  # type: ignore
        ephemeral: bool = False,
    ) -> None:
        asyncio.create_task(ctx.defer(ephemeral=ephemeral))
        await ctx.respond(
            content=await Gembot.translate(query, language=language, nuance=nuance),
            ephemeral=ephemeral,
        )


def setup(bot):
    bot.add_cog(Translate(bot))
