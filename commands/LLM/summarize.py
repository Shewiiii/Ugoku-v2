import asyncio
import discord
from discord.ext import commands

from config import GEMINI_ENABLED
from bot.search import is_url


if GEMINI_ENABLED:
    from bot.misc.summaries import Summaries

    class Summarize(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot

        @commands.slash_command(
            name='summarize',
            description='Summarize a given text, an audio file or a Youtube video.',
            integration_types={
                discord.IntegrationType.guild_install,
                discord.IntegrationType.user_install
            }
        )
        async def summarize(
            self,
            ctx: discord.ApplicationContext,
            query: str
        ) -> None:
            if not GEMINI_ENABLED:
                await ctx.respond('Summaries are not available !')
                return

            asyncio.create_task(ctx.defer())
            if is_url(query, ['youtube.com', 'www.youtube.com', 'youtu.be']):
                query = await Summaries.get_youtube_transcript_text(url=query)

            # Prepare the summary
            text = "Something went wrong during the summary generation."
            try:
                text = await Summaries.summarize(query)
            except Exception as e:
                text += f"\n -# {str(e)}"

            # Prepare the embed
            # ...
            await ctx.respond(text)
else:
    class Summarize(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot


def setup(bot):
    bot.add_cog(Summarize(bot))
