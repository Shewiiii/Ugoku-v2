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
        description='Download a LINE sticker pack from a given URL.'
    )
    async def stickers(
        self,
        ctx: discord.ApplicationContext,
        url: str
    ) -> None:
        if not url:
            await ctx.respond(
                'Please specify a URL to a sticker pack. '
                'E.g: https://store.line.me/stickershop/product/1472670/'
            )
            return

        await ctx.respond('Give me a second~')

        try:
            zip_file = await get_stickerpack(url, ctx=ctx)
        except IncorrectURL:
            await ctx.edit(content='Invalid URL! Please check the URL and try again.')
            return

        await ctx.send(
            file=discord.File(zip_file),
            content=f"Sorry for the wait, <@{
                ctx.author.id}>! Here's the sticker pack you requested."
        )

        # Clean up the file after sending
        os.remove(zip_file)

        await ctx.edit(content='Done!')


def setup(bot):
    bot.add_cog(Stickers(bot))
