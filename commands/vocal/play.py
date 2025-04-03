import asyncio
from typing import Optional
from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.vocal.audio_service_handlers import (
    play_spotify,
    play_custom,
    play_onsei,
    play_ytdlp,
)
from bot.utils import is_onsei
from bot.search import is_url
from config import (
    SPOTIFY_ENABLED,
    DEFAULT_STREAMING_SERVICE,
    DEEZER_ENABLED,
    SPOTIFY_API_ENABLED,
    IMPULSE_RESPONSE_PARAMS,
    ONSEI_SERVER_WHITELIST,
    YTDLP_DOMAINS,
)


class Play(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_play(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        service: str,
        interaction: Optional[discord.Interaction] = None,
        offset: int = 0,
        artist_mode: bool = False,
        album: bool = False,
        effect: str = "default",
        play_next: bool = False,
    ) -> None:
        defer_task = None if interaction else asyncio.create_task(ctx.defer())
        respond = interaction.response.send_message if interaction else ctx.respond

        # Connect to the voice channel
        session: Optional[ServerSession] = sm.connect(ctx, self.bot)
        if not session:
            if defer_task:
                await defer_task
            await respond(content="You are not in an active voice channel !")
            return

        # Applying audio effects
        p = IMPULSE_RESPONSE_PARAMS.get(effect)
        if p:
            session.audio_effect.effect = effect
            attrs = {
                "left_ir_file": p.get("left_ir_file", ""),
                "right_ir_file": p.get("right_ir_file", ""),
                "effect_only": "raum" in effect.lower(),
                "wet": p.get("wet", 0),
                "dry": p.get("dry", 0),
                "volume_multiplier": p.get("volume_multiplier", 1),
            }
            for attr, value in attrs.items():
                setattr(session.audio_effect, attr, value)

        spotify_domains = ["open.spotify.com"]
        custom_domains = spotify_domains + YTDLP_DOMAINS
        if not (is_url_ := is_url(query)):
            query = query.lower()

        if service == "onsei" or is_onsei(query):
            if defer_task:
                await defer_task
            if session.guild_id not in ONSEI_SERVER_WHITELIST:
                await respond("You can't stream audio works here.")
                return
            await play_onsei(ctx, query, session, play_next, defer_task)

        elif (
            service == "custom"
            or is_url_
            and not is_url(query, from_=custom_domains)
        ):
            await play_custom(ctx, query, session, play_next, defer_task)

        elif service == "ytdlp" or is_url(query, from_=YTDLP_DOMAINS):
            await play_ytdlp(ctx, query, session, interaction, play_next, defer_task)

        elif service == "spotify/deezer":
            if not (SPOTIFY_API_ENABLED and (SPOTIFY_ENABLED or DEEZER_ENABLED)):
                if defer_task:
                    await defer_task
                await respond(
                    content="Spotify API or no music streaming service is enabled."
                )
                return
            await play_spotify(
                ctx,
                query,
                session,
                interaction,
                offset,
                artist_mode,
                album,
                play_next,
                defer_task,
            )
        else:
            await respond(content="wut duh")

    @commands.slash_command(name="play", description="Select a song to play.")
    async def play(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        service: discord.Option(
            str,
            description="The streaming service you want to use.",
            choices=["Spotify/Deezer", "Ytdlp", "Custom", "Onsei"],
            default=DEFAULT_STREAMING_SERVICE,
        ),  # type: ignore
        play_next: discord.Option(
            bool,
            description="Add the song at the beginning of the queue.",
            default=False,
        ),  # type: ignore
        playlist_offset: discord.Option(
            int,
            description="If the query is a playlist, choose from what song index to start, defaults to 0.",
            default=0,
        ),  # type: ignore
        artist_mode: discord.Option(
            bool,
            description="Plays the 10 first tracks of the queried artist if enabled.",
            default=0,
        ),  # type: ignore
        album: discord.Option(
            bool,
            description="Add an album to queue. Can't combine with artist mode.",
            default=0,
        ),  # type: ignore
        effect: discord.Option(
            str,
            description="The audio effect to apply.",
            choices=["default"] + [effect for effect in IMPULSE_RESPONSE_PARAMS],
            default="default",
        ),  # type: ignore
    ) -> None:
        await self.execute_play(
            ctx,
            query,
            service.lower(),
            offset=playlist_offset,
            artist_mode=artist_mode,
            album=album,
            effect=effect,
            play_next=play_next,
        )


def setup(bot):
    bot.add_cog(Play(bot))
