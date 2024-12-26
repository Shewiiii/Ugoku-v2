import discord
from discord.ext import commands

import logging


class Ping(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="ping",
        description='Test the reactivity of Ugoku !',
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install
        }
    )
    async def ping(self, ctx: discord.ApplicationContext) -> None:
        latency = round(self.bot.latency*1000, 2)
        await ctx.respond(f'あわあわあわわわ ! {latency}ms')
        logging.info(f'Pinged latency: {latency}ms.')


def setup(bot):
    bot.add_cog(Ping(bot))
