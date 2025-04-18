import asyncio
import discord
from discord.ext import commands

from bot.chatbot.gemini import Gembot
from bot.search import is_url
from bot.misc.summaries import Summaries


class Summarize(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.s = Summaries()

    @commands.slash_command(
        name="summarize",
        description="Summarize a given text, an audio file or a Youtube video.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def summarize(self, ctx: discord.ApplicationContext, query: str) -> None:
        if not Gembot.get_chat_id(ctx): # Can this server or channel use Gemini features ?
            await ctx.respond("Summaries are not available !")
            return

        defer_task = asyncio.create_task(ctx.defer())
        if is_url(query, ["youtube.com", "youtu.be"]):
            query = await self.s.get_youtube_transcript_text(url=query)
            if not query:
                await defer_task
                await ctx.respond("Video not found !")
                return

        # Prepare the summary
        text = "Something went wrong during the summary generation."
        try:
            text = await self.s.summarize(query)
        except Exception as e:
            await defer_task
            text += f"\n-# {repr(e)}"

        # Prepare the embed
        # ...
        await defer_task
        await ctx.respond(text)


def setup(bot):
    bot.add_cog(Summarize(bot))
