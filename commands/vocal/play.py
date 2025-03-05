from typing import Optional

from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.vocal.audio_service_handlers import play_spotify, play_custom, play_onsei, play_youtube
from bot.utils import is_onsei, send_response, vocal_action_check
from bot.search import is_url
from config import (
    SPOTIFY_ENABLED,
    DEFAULT_STREAMING_SERVICE,
    DEEZER_ENABLED,
    SPOTIFY_API_ENABLED,
    IMPULSE_RESPONSE_PARAMS
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
        effect: str = 'default'
    ) -> None:
        await ctx.defer()
        if interaction:
            respond = interaction.response.send_message
            edit = interaction.edit_original_response
        else:
            respond = ctx.respond
            edit = ctx.edit

        # Connect to the voice channel
        session: Optional[ServerSession] = await sm.connect(ctx, self.bot)
        if not await vocal_action_check(session, ctx, ctx.respond, check_queue=False):
            return

        # Applying audio effects
        p = IMPULSE_RESPONSE_PARAMS.get(effect)
        if p:
            session.audio_effect.effect = effect
            attrs = {
                'left_ir_file': p.get('left_ir_file', ''),
                'right_ir_file': p.get('right_ir_file', ''),
                'effect_only': False,
                'wet': p.get('wet', 0),
                'dry': p.get('dry', 0),
                'volume_multiplier': p.get('volume_multiplier', 1)
            }
            for attr, value in attrs.items():
                setattr(session.audio_effect, attr, value)

        youtube_domains = ['youtube.com', 'www.youtube.com', 'youtu.be']
        spotify_domains = ['open.spotify.com']

        if service == 'onsei' or is_onsei(query):
            await play_onsei(ctx, query, session)

        elif service == 'custom' or (is_url(query) and not is_url(query, from_=spotify_domains+youtube_domains)):
            await play_custom(ctx, query, session)

        elif service == 'youtube' or is_url(query, from_=youtube_domains):
            await play_youtube(ctx, query, session, interaction)

        elif service == 'spotify/deezer':
            if not SPOTIFY_API_ENABLED or (not SPOTIFY_ENABLED and not DEEZER_ENABLED):
                await edit(content=f'Spotify API or no audio streaming service is enabled.')
                return
            await play_spotify(
                ctx, query, session, interaction,
                offset, artist_mode, album
            )
        else:
            await edit(content='wut duh')

    @commands.slash_command(
        name='play',
        description='Select a song to play.'
    )
    async def play(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        service: discord.Option(
            str,
            description="The streaming service you want to use.",
            choices=['Spotify/Deezer', 'Youtube', 'Custom', 'Onsei'],
            default=DEFAULT_STREAMING_SERVICE
        ),  # type: ignore
        playlist_offset: discord.Option(
            int,
            description="If the query is a playlist, choose from what song index to start, defaults to 0.",
            default=0
        ),  # type: ignore
        artist_mode: discord.Option(
            bool,
            description="Plays the 10 first tracks of the queried artist if enabled.",
            default=0
        ),  # type: ignore
        album: discord.Option(
            bool,
            description="Add an album to queue. Can't combine with artist mode.",
            default=0
        ),  # type: ignore
        effect: discord.Option(
            str,
            description="The audio effect to apply.",
            choices=['default']+[effect for effect in IMPULSE_RESPONSE_PARAMS],
            default='default'
        )  # type: ignore
    ) -> None:
        await self.execute_play(
            ctx,
            query,
            service.lower(),
            offset=playlist_offset,
            artist_mode=artist_mode,
            album=album,
            effect=effect
        )


def setup(bot):
    bot.add_cog(Play(bot))
