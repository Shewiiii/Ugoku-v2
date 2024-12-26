from discord.ext import commands
import discord

import logging


class Echo(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @discord.slash_command(
        name='echo',
        description='Echo any message !',
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def echo(
        self,
        ctx: discord.ApplicationContext,
        message
    ) -> None:
        logging.info(f'{ctx.author.name} used /echo.')
        if not ctx.guild.me:
            # If using the bot as an user application
            # (Bot not in the server)
            await ctx.respond(content=message)
        else:
            await ctx.send(content=message)
            await ctx.respond('Done !', ephemeral=True)


def setup(bot):
    bot.add_cog(Echo(bot))
