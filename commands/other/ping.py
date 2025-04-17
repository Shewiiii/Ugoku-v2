import discord
from discord.ext import commands
import time


class Ping(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="ping",
        description="Test the reactivity of Ugoku !",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def ping(self, ctx: discord.ApplicationContext) -> None:
        # Bot latency
        bot_latency = round(self.bot.latency * 1000, 2)
        start = time.perf_counter()
        response = f"あわあわあわわわ ! \n> Bot latency: {bot_latency}ms\n> Reponse latency: ..."
        await ctx.respond(response)

        # Response latency
        delta = time.perf_counter() - start
        response_latency = round(delta * 1000, 2)
        response = response.replace("...", f"{response_latency}ms")
        await ctx.edit(content=response)


def setup(bot):
    bot.add_cog(Ping(bot))
