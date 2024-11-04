from typing import Optional

from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.vocal.audio_source_handlers import play_spotify, play_custom, play_onsei, play_youtube
from bot.utils import is_onsei, send_response
from bot.search import is_url
from config import SPOTIFY_ENABLED


default = 'Spotify' if SPOTIFY_ENABLED else 'Youtube'


class Play(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def execute_play(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        source: str,
        interaction: Optional[discord.Interaction] = None
    ) -> None:
        if interaction:
            respond = interaction.response.send_message
            edit = interaction.edit_original_response
        else:
            respond = ctx.respond
            edit = ctx.edit

        # Connect to the voice channel
        session: Optional[ServerSession] = await sm.connect(ctx, self.bot)
        if not session:
            await respond('You are not in a voice channel!')
            return

        await send_response(respond, "Give me a second~", session.guild_id)

        source = source.lower()
        youtube_domains = ['youtube.com', 'www.youtube.com', 'youtu.be']
        spotify_domains = ['open.spotify.com']

        # Detect if the query refers to an Onsei
        if source == 'onsei' or is_onsei(query):
            await play_onsei(ctx, query, session)

        # If the query is custom or an URL not from Spotify/Youtube
        elif (source == 'custom'
              or (is_url(query)
                  and not is_url(query,
                                 from_=spotify_domains+youtube_domains))):
            await play_custom(ctx, query, session)

        # Else, search Spotify or Youtube
        elif (source == 'youtube'
              or is_url(query, from_=youtube_domains)):
            await play_youtube(ctx, query, session, interaction)

        elif source == 'spotify':
            if not SPOTIFY_ENABLED:
                await edit(
                    content=('Spotify features are not enabled.')
                )
                return

            await play_spotify(ctx, query, session, interaction)

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
        source: discord.Option(
            str,
            choices=['Spotify', 'Youtube', 'Custom', 'Onsei'],
            default=default
        )  # type: ignore
    ) -> None:
        await self.execute_play(ctx, query, source)


def setup(bot):
    bot.add_cog(Play(bot))
