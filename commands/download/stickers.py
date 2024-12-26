import discord
from discord.ext import commands

import os

from bot.line import get_stickerpack
from bot.exceptions import IncorrectURL


class Stickers(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='get-stickers',
        description='Download a LINE sticker pack from a given URL.',
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install
        }
    )
    async def stickers(
        self,
        ctx: discord.ApplicationContext,
        url: discord.Option(
            str,
            required=True
        )  # type: ignore
    ) -> None:
        await ctx.respond('Give me a second~')

        try:
            zip_file = await get_stickerpack(url, ctx=ctx)
        except IncorrectURL:
            await ctx.edit(
                content="Invalid URL! Please check the URL and try again."
                "\nExample: "
                "https://store.line.me/stickershop/product/20347097/en"
                )
            return

        await ctx.edit(
            file=discord.File(zip_file),
            content="Here's the sticker pack you requested~"
        )
        # Clean up the file after sending
        os.remove(zip_file)


def setup(bot):
    bot.add_cog(Stickers(bot))
