import discord
from discord.ext import commands
from bot.misc.quickstart_view import QuickstartView


class Quickstart(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="quickstart",
        description="Discover the features of Ugoku !",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def quickstart(self, ctx: discord.ApplicationContext) -> None:
        quickstart_view = QuickstartView()
        await quickstart_view.display(respond_func=ctx.respond, ephemeral=True)


def setup(bot):
    bot.add_cog(Quickstart(bot))
