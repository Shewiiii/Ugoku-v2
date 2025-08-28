import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="help",
        description="Show help menu.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def help_command(self, ctx: discord.ApplicationContext) -> None:
        """Slash command to show the help menu with a dropdown."""
        embed = discord.Embed(
            title="Help Menu",
            description=(
                "Get the list of commands on Ugoku's website [Ugoku.app](https://ugoku.app/commands) !\n"
                "Not sure where to start ? Try `/quickstart` !"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(Help(bot))
