from discord.ext import commands
import discord

from bot.vocal.session_manager import session_manager
from bot.vocal.audio_source_handlers import play_spotify, play_custom, play_onsei
from config import SPOTIFY_ENABLED


class Play(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

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
            choices=['Spotify', 'Custom', 'Onsei'],
            default='Spotify'
        )  # type: ignore
    ) -> None:
        await ctx.respond('Give me a second~')
        # Connect to the voice channel
        session = await session_manager.connect(ctx, self.bot)
        if not session:
            await ctx.respond('You are not in a voice channel!')
            return
        source = source.lower()

        if source == 'spotify':
            if not SPOTIFY_ENABLED:
                await ctx.edit(content='Spotify features are not enabled.')
                return
            await play_spotify(ctx, query, session)

        # elif source == 'youtube':
        #     await play_youtube(ctx, query, session)

        elif source == 'custom':
            await play_custom(ctx, query, session)

        elif source == 'onsei':
            await play_onsei(ctx, query, session)

        else:
            await ctx.edit(content='wut duh')


def setup(bot):
    bot.add_cog(Play(bot))
