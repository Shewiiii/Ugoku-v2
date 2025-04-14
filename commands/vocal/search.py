import asyncio
import discord
from discord.ext import commands
import re
import spotipy
from typing import Optional

from bot.utils import get_dominant_rgb_from_url, split_into_chunks
from bot.vocal.server_session import ServerSession
from bot.vocal.session_manager import session_manager as sm
from bot.vocal.track_dataclass import Track


class Search(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_search(
        self,
        ctx: discord.ApplicationContext,
        type: str,
        query: str,
        max_number_of_results: int = 100,
        play_next: bool = False,
        offset: int = 0,
        interaction: Optional[discord.Interaction] = None,
    ) -> None:
        defer_task = None if interaction else asyncio.create_task(ctx.defer())
        respond = interaction.channel.send if interaction else ctx.respond
        spotify = self.bot.spotify
        bot = self.bot
        embed_title = query
        playlist_match = re.findall(
            r"https?://open\.spotify\.com/(?:(?:intl-[a-z]{2})/)?"
            r"playlist/(?P<ID>[0-9a-zA-Z]{22})",
            query,
        )

        if type == "artist":
            artist = (await spotify.search(query, type="artist", limit=1))[0]
            tracks: list[Track] = await spotify.get_tracks(
                id_=artist["id"], offset=offset, type="artist"
            )
            cover = artist["images"][0]["url"] if artist.get("images") else None
        else:
            if playlist_match:
                try:
                    playlist_id = playlist_match[0]
                    playlist_info = await asyncio.to_thread(
                        spotify.sessions.sp.playlist, playlist_id
                    )
                    playlist_tracks = await asyncio.to_thread(
                        spotify.sessions.sp.playlist_tracks,
                        playlist_id=playlist_id,
                        offset=offset,
                    )
                    items = [t["track"] for t in playlist_tracks["items"]]
                    cover = (
                        playlist_info["images"][0]["url"]
                        if playlist_info.get("images")
                        else None
                    )
                    embed_title = playlist_info["name"]
                except spotipy.exceptions.SpotifyException:
                    if defer_task:
                        await defer_task
                    await respond(
                        "Content not found! Perhaps you are trying to play a private playlist?"
                    )
                    return
            else:
                items = await spotify.search(
                    query, min(max_number_of_results, 25), offset, type=type
                )
                artist = await asyncio.to_thread(
                    spotify.sessions.sp.artist, items[0]["artists"][0]["id"]
                )
                cover = artist["images"][0]["url"] if artist.get("images") else None

            tracks = [spotify.get_track(item) for item in items]

        dominant_rgb = await get_dominant_rgb_from_url(cover)
        display_names = [f"{track:markdown}" for track in tracks]

        search_embed = (
            discord.Embed(
                color=discord.Colour.from_rgb(*dominant_rgb),
            )
            .set_author(
                name=f"Play prompt - {embed_title}",
                icon_url=tracks[0].cover_url,
            )
            .set_thumbnail(url=cover)
        )

        # Defined here to access local variables
        class SelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=1800)
                self.page = 1
                self.max_per_page = 10
                self.update()

            def update(self) -> None:
                # Song list
                start_index = (self.page - 1) * self.max_per_page
                end_index = min(start_index + self.max_per_page, len(display_names))
                queue = "\n".join(
                    [
                        f"{i + 1}. {display_names[i]}"
                        for i in range(start_index, end_index)
                    ]
                )
                if not queue:
                    return
                splitted = split_into_chunks(queue)
                search_embed.fields = []
                search_embed.add_field(name="Results", value=splitted[0])
                [search_embed.add_field(name="", value=part) for part in splitted[1:]]

                # Buttons
                self.children[0].disabled = self.page <= 1
                self.children[1].disabled = (
                    len(display_names) <= self.page * self.max_per_page
                )

                # Select menu
                self.children[3].max_values = end_index - start_index
                self.children[3].options = [
                    discord.SelectOption(label=f"{i + 1}. {str(tracks[i])[:95]}")
                    for i in range(start_index, end_index)
                ]

            async def play(
                self, interaction: discord.Interaction, tracks: list[Track]
            ) -> None:
                interaction_voice = interaction.user.voice
                if not interaction_voice or (
                    interaction_voice
                    and ctx.author.voice.channel != interaction_voice.channel
                ):
                    return

                session: Optional[ServerSession] = sm.connect(ctx, bot)
                if not session:
                    return

                asyncio.create_task(
                    session.add_to_queue(
                        ctx,
                        tracks,
                        play_next=play_next,
                    )
                )
                await sent_embed.edit(view=view)

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
            async def previous_button(
                self, button: discord.ui.Button, interaction: discord.Interaction
            ) -> None:
                """Update the page on 'previous' click."""
                asyncio.create_task(interaction.response.defer())
                self.page -= 1
                self.update()
                await sent_embed.edit(embed=search_embed, view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
            async def next_button(
                self, button: discord.ui.Button, interaction: discord.Interaction
            ) -> None:
                """Update the page on 'Next' click."""
                asyncio.create_task(interaction.response.defer())
                self.page += 1
                self.update()
                await sent_embed.edit(embed=search_embed, view=self)

            @discord.ui.button(label="Play all", style=discord.ButtonStyle.blurple)
            async def play_all_button(
                self, button: discord.ui.Button, interaction: discord.Interaction
            ) -> None:
                """Update the page on 'previous' click."""
                asyncio.create_task(interaction.response.defer())
                await self.play(interaction, tracks)

            @discord.ui.select(
                placeholder="Select songs !",
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(label="1. You should not see this")],
            )
            async def select_callback(
                self, select, interaction: discord.Interaction
            ) -> None:
                asyncio.create_task(interaction.response.defer())
                selected_track_names: list = select.values
                await self.play(
                    interaction,
                    [
                        tracks[int(re.findall(r"\d+", tn)[0]) - 1]
                        for tn in selected_track_names
                    ],
                )

        view = SelectView()
        if defer_task:
            await defer_task
        sent_embed = await respond(embed=search_embed, view=view)

    @commands.slash_command(
        name="search", description="Search a song from Spotify to play in vc."
    )
    async def search(
        self,
        ctx: discord.ApplicationContext,
        type: discord.Option(
            str,
            description="The song to search. You can paste Spotify playlist URLs",
            choices=["track", "artist"],
            required=True,
        ),  # type: ignore
        query: discord.Option(str, description="The song to search.", required=True),  # type: ignore
        max_number_of_results: discord.Option(
            int,
            description="Fixed to 10 for artists. Default and max is 100 for tracks.",
            default=100,
        ),  # type: ignore
        play_next: discord.Option(
            bool,
            description="Add the song at the beginning of the queue.",
            default=False,
        ),  # type: ignore
        offset: discord.Option(
            int, description="Offset the search results.", default=0
        ),  # type: ignore
    ) -> None:
        await self.execute_search(ctx, type, query, max_number_of_results, play_next, offset)


def setup(bot):
    bot.add_cog(Search(bot))
