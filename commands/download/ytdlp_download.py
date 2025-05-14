import asyncio

import discord
from discord.errors import Forbidden
from discord.ext import commands

from bot.utils import upload, process_song_query
from bot.vocal.track_dataclass import Track


class YtdlpDownload(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="ytdlp",
        description="Download songs from Youtube (or Soundcloud with an URL).",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def ytdlp(self, ctx: discord.ApplicationContext, query: str) -> None:
        defer_task = asyncio.create_task(ctx.respond("Give me a second~"))

        # Convert the query
        try:
            query = await process_song_query(
                query, ctx.bot, get_title=True, spotify=self.bot.spotify
            )
        except Forbidden:
            await defer_task
            await ctx.edit(content="I don't have access to that message !")
            return

        # Get the tracks, pick the first one
        try:
            tracks = await ctx.bot.ytdlp.get_tracks(query=query, download=True)
            if not tracks:
                await ctx.edit(content="No track has been found!")
                return
            track: Track = tracks[0]
        except Exception as e:
            await ctx.edit(
                content="Oops, it didn't work ! "
                f"Please check the URL again or contact the developper.\n-# {repr(e)}"
            )
            return

        # stream_source is a Path in this case
        file_path = track.stream_source
        await upload(self.bot, ctx, file_path, f"{track}.{track.file_extension}")


def setup(bot):
    bot.add_cog(YtdlpDownload(bot))
