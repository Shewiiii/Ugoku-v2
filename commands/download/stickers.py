import asyncio
import discord
from discord.ext import commands

from bot.misc.line import get_stickerpack


class Stickers(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="get-stickers",
        description="Download a LINE sticker pack from a given URL.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def stickers(
        self,
        ctx: discord.ApplicationContext,
        url: discord.Option(str, required=True),  # type: ignore
    ) -> None:
        asyncio.create_task(ctx.respond("Give me a second~"))

        try:
            zip_file = await get_stickerpack(url, ctx=ctx)
        except Exception as e:
            await ctx.edit(
                content="Oops! Something went wrong. Please check the URL or contact the developer."
                "\nURL example: "
                "https://store.line.me/stickershop/product/20347097/en\n"
                f"-# error: {e}"
            )
            return

        asyncio.create_task(
            ctx.edit(
                file=discord.File(zip_file),
                content="Here's the sticker pack you requested~",
            )
        )


def setup(bot):
    bot.add_cog(Stickers(bot))
