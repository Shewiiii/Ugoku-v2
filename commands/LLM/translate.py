import discord
import logging
from discord.ext import commands
from config import (
    LANGUAGES,
    GEMINI_ENABLED
)

if GEMINI_ENABLED:
    from bot.chatbot.gemini import Gembot


class Translate(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='translate',
        description='Translate any sentence to a language.',
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install
        }
    )
    async def translate(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        language: discord.Option(
            str,
            choices=LANGUAGES,
            required=True,
            default='English'

        ),  # type: ignore
        nuance: discord.Option(
            str,
            choices=['Neutral', 'Casual', 'Formal'],
            required=True,
            default='Neutral'

        ),  # type: ignore
        ephemeral: bool = True
    ) -> None:
        await ctx.defer()
        await ctx.respond(
            content=await Gembot.translate(
                query,
                language=language,
                nuance=nuance
            ),
            ephemeral=ephemeral
        )


def setup(bot):
    bot.add_cog(Translate(bot))
