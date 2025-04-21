import asyncio
import discord
from discord.ext import commands
import spotipy
from typing import Optional

from bot.vocal.spotify import Spotify
from bot.vocal.server_session import ServerSession
from bot.vocal.session_manager import session_manager as sm
from config import SPOTIFY_API_ENABLED


class PlaylistDropdownView(discord.ui.View):
    def __init__(
        self,
        ctx: discord.ApplicationContext,
        bot: discord.bot,
        playlists: dict,
        offset: int,
    ):
        super().__init__()
        self.ctx: discord.ApplicationContext = ctx
        self.bot: discord.Bot = bot
        self.playlists: dict[str, str] = playlists
        self.offset: int = offset

        # Create a dropdown menu for playlists
        options = [
            discord.SelectOption(label="Play Liked Titles", value="liked_songs")
        ] + [
            discord.SelectOption(
                label=f"Play {name}",
                value=f"https://open.spotify.com/playlist/{playlist_id}",
            )
            for playlist_id, name in playlists.items()
        ]

        dropdown = discord.ui.Select(
            placeholder="Choose a playlist to play...",
            options=options,
            custom_id="playlist_dropdown",
        )
        dropdown.callback = self.dropdown_callback
        self.add_item(dropdown)

    async def dropdown_callback(self, interaction: discord.Interaction):
        defer_task = asyncio.create_task(interaction.response.defer())
        selected_value = interaction.data["values"][0]
        tracks = await self.bot.spotify.get_tracks(
            selected_value,
            self.offset,
            id_=selected_value,
            type="playlist",
            sp=self.bot.spotify.users[self.ctx.user.id],
        )

        # Connect to the voice channel
        session: Optional[ServerSession] = sm.connect(self.ctx, self.bot)
        if not session:
            await defer_task
            await self.ctx.respond(
                content="You are not in an active voice channel !", ephemeral=True
            )
            return

        await session.add_to_queue(
            self.ctx, tracks, show_wrong_track_embed=False, send=True
        )


class SpPlaylist(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="spotify-playlist", description="Play songs from your Spotify playlists !"
    )
    async def spotify_playlist(
        self,
        ctx: discord.ApplicationContext,
        authorize_url: discord.Option(
            str,
            description="Paste the URL you've got ridirected to after authorizing the bot.",
            default=None,
        ),  # type: ignore
        offset: discord.Option(
            int,
            description="Choose from what song index to start, defaults to 0.",
            default=0,
        ),  # type: ignore
    ) -> None:
        if not SPOTIFY_API_ENABLED:
            await ctx.respond("The Spotify API is not enabled.")
        defer_task = asyncio.create_task(ctx.defer(ephemeral=True))
        spotify: Spotify = self.bot.spotify

        async def respond(msg: str):
            await defer_task
            return await ctx.respond(msg)

        if not (sp := spotify.users.get(ctx.user.id)):
            if not authorize_url:
                client_id = spotify.sessions.config.client_id
                url = (
                    f"https://accounts.spotify.com/en/authorize?client_id={client_id}"
                    "&response_type=code&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&"
                    "scope=user-library-read%20playlist-read-private"
                )
                await respond(
                    "It looks like you are not logged in. "
                    f"[Click here]({url}) to authorize the Ugoku app, "
                    "then rerun the command and pass the URL you've got redirected to."
                )
                return

            if not await spotify.user_authorize(ctx.user.id, authorize_url):
                await respond("Invalid authorize URL. Please try again.")
                return

            sp: spotipy.Spotify = spotify.users.get(ctx.user.id)

        respond_task = respond("Logged in ! Select a playlist below:")

        playlists_dict = {}
        playlists_data = await asyncio.to_thread(sp.current_user_playlists)
        for playlist in playlists_data["items"]:
            playlist_id = playlist["id"]
            playlist_name = playlist["name"]
            playlists_dict[playlist_id] = playlist_name

        select_view = PlaylistDropdownView(ctx, self.bot, playlists_dict, offset)
        await (await respond_task).edit(view=select_view)


def setup(bot):
    bot.add_cog(SpPlaylist(bot))
