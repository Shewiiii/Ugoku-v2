import asyncio
import logging
from typing import Optional
from config import (
    SPOTIFY_API_ENABLED,
    DEFAULT_EMBED_COLOR,
    GEMINI_ENABLED,
    DEFAULT_STREAMING_SERVICE,
    LANGUAGES,
)

import discord
from discord.ext import commands

from bot.misc.lyrics import BotLyrics
from bot.vocal.session_manager import session_manager
from bot.utils import get_dominant_rgb_from_url, split_into_chunks
from bot.vocal.track_dataclass import Track
from commands.vocal.play import Play


logger = logging.getLogger(__name__)

# Create the view if Spotify enabled (buttons)


class lyricsView(discord.ui.View):
    def __init__(
        self, bot: discord.bot, ctx: discord.ApplicationContext, source_url: str
    ) -> None:
        super().__init__()
        self.bot = bot
        self.ctx = ctx
        self.source_url: str = source_url

        spotify_button = discord.ui.Button(
            label="Spotify Link",
            style=discord.ButtonStyle.link,
            url=self.source_url,
        )
        self.add_item(spotify_button)

    @discord.ui.button(
        label="Play it",
        style=discord.ButtonStyle.primary,
    )
    async def play_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        play_cog: Play = self.bot.get_cog("Play")
        asyncio.create_task(interaction.response.defer())
        asyncio.create_task(
            play_cog.execute_play(
                self.ctx,
                self.source_url,
                DEFAULT_STREAMING_SERVICE,
                interaction=interaction,
                play_next=True,
            )
        )

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.secondary,
    )
    async def close_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await interaction.message.delete()
        self.clear_items()
        self.ctx = self.bot = None


class Lyrics(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_lyrics(
        self,
        ctx: discord.ApplicationContext,
        query: Optional[str],
        convert_to: Optional[str] = None,
        silent: bool = False,
    ) -> None:
        if not query:
            guild_id = ctx.guild.id
            session = session_manager.server_sessions.get(guild_id)
            if not (session and session.queue):
                if not silent:
                    await ctx.respond("No song is playing !")
                return
            track: Track = session.queue[0]

        elif SPOTIFY_API_ENABLED:
            # Use Spotify features for more precise results
            tracks: Track = await self.bot.spotify.get_tracks(query)
            if not tracks:
                if not silent:
                    await ctx.respond("No lyrics found !")
                return
            track: Track = tracks[0]

        lyrics = await BotLyrics.get(track)
        if not lyrics:
            if not silent:
                await ctx.respond(lyrics or "No lyrics found !")
            return

        # CONVERT
        if convert_to:
            if not GEMINI_ENABLED:
                if not silent:
                    await ctx.respond(
                        "Chatbot features need to be enabled in "
                        "order to use lyrics conversion."
                    )
                return
            asyncio.create_task(ctx.respond("Converting~"))
            lyrics = await BotLyrics.convert(lyrics, convert_to)

        # Split the lyrics in case it's too long
        splitted_lyrics: list = split_into_chunks(lyrics)

        # Create the embed
        if track.cover_url:
            dominant_rgb = await get_dominant_rgb_from_url(track.cover_url)
            color = discord.Colour.from_rgb(*dominant_rgb)
        else:
            color = discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR)

        # Embed body
        embed = discord.Embed(title=str(track), color=color)
        for part in splitted_lyrics:
            embed.add_field(name="", value=part, inline=False)

        if SPOTIFY_API_ENABLED:
            # Add a cover to the embed
            embed.set_author(name="Lyrics", icon_url=track.cover_url)
            if not silent:
                asyncio.create_task(
                    ctx.respond(embed=embed, view=lyricsView(self.bot, ctx, track.source_url))
                )
        else:
            asyncio.create_task(ctx.respond(embed=embed))

    @commands.slash_command(
        name="lyrics",
        description="Get the lyrics of a song, or the currently playing one.",
    )
    async def lyrics(
        self,
        ctx: discord.ApplicationContext,
        query: Optional[str],
        convert_to: discord.Option(
            str,
            choices=["Romaji", "Japanese Kana"]
            + LANGUAGES[:-2],  # To not hit the option limit
            required=False,
        ),  # type: ignore
        # Uncomment the following if Spotify features are disabled
        # artist: str = Optional[str]
    ) -> None:
        asyncio.create_task(ctx.defer())
        await self.execute_lyrics(ctx, query, convert_to)


def setup(bot):
    bot.add_cog(Lyrics(bot))
