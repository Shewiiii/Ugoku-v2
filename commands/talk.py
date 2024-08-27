from discord.ext import commands
import discord

import logging
import config


class Talk(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='talk',
        description='!'
    )
    async def talk(
        self,
        ctx: discord.ApplicationContext,
        message: str
    ) -> None:
        logging.info(f'{ctx.author.name} used /talk: "{message}"')
        await ctx.send(message)
        await ctx.respond('Done !', ephemeral=True)


def setup(bot):
    bot.add_cog(Talk(bot))
