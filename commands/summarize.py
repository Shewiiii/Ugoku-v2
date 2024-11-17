import discord
from discord.ext import commands

from config import CHATBOT_ENABLED, CHATBOT_WHITELIST


if CHATBOT_ENABLED:
    from bot.summaries import Summaries

    class Summarize(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot

        @commands.slash_command(
            name='summarize',
            description='Summarize a given text, an audio file or a Youtube video.'
        )
        async def summarize(
            self,
            ctx: discord.ApplicationContext,
            query: str,
            type: discord.Option(
                str,
                choices=['Text', 'Youtube video']
            )  # type: ignore
        ) -> None:
            if not CHATBOT_ENABLED or not ctx.guild.id in CHATBOT_WHITELIST:
                await ctx.respond('Summaries are not available in your server~')
                return

            await ctx.respond('Give me a second~')
            if type == 'Youtube video':
                query = await Summaries.get_youtube_transcript_text(url=query)

            # Prepare the summary
            text = await Summaries.summarize(query)
            if not text:
                await ctx.edit(
                    content='An error occured during the summary genetation!')

            # Prepare the embed
            # ...
            await ctx.respond(text)
else:
    class Summarize(commands.Cog):
        def __init__(self, bot) -> None:
            self.bot = bot


def setup(bot):
    bot.add_cog(Summarize(bot))
