from discord.ext import commands
import discord

from bot.vocal import *
from config import SPOTIFY_ENABLED


# Reminder/TODO: delete downloaded tracks at the end of the session (?)

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
            choices=['Spotify', 'Custom'],
            default='Spotify'
        )  # type: ignore
    ) -> None:
        # Connect to the voice channel
        session = await connect(ctx)
        if not session:
            await ctx.respond('You are not in a voice channel!')
            return
        
        await ctx.respond('Give me a second~')

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

        else:
            await ctx.edit(content='wut duh')


def setup(bot):
    bot.add_cog(Play(bot))
