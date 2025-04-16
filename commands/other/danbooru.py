import asyncio
import logging
from httpx._exceptions import HTTPStatusError

import discord
from discord.ext import commands

from bot.misc.danbooru import Danbooru, DanbooruView
from bot.utils import get_dominant_rgb_from_url
from bot.search import is_url


class Danbooru_(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.danbooru = Danbooru()
        self.cached_posts: dict[str, set] = {}
        # So key: tag, value: post url set [post1, post2 ...]

    async def execute_danbooru_(
        self,
        ctx: discord.ApplicationContext,
        tag: str,
    ) -> None:
        try:
            posts = await self.danbooru.get_posts(tag=tag)
        except HTTPStatusError as e:
            logging.error(f"Failed to get posts from {tag}: {e}")
            await ctx.respond(f"Can't get posts from {tag}.")
            return
        if not posts:
            await ctx.respond("No post found !")
            return

        if not self.cached_posts.get(tag):
            # Grab the results
            results = []
            for post in posts:
                # Variables
                url: str = post.get("file_url", "")
                rating: str = post.get("rating", "")
                # e: explicit, q: questionable
                if not url or rating in {"e", "q", ""}:
                    continue
                results.append(post)

            if not results:
                await ctx.respond("Failed to find a post !")
                return

            # Cache all the results
            self.cached_posts[tag] = results

        # Variables of the chosen post
        post: dict = self.cached_posts[tag].pop()
        id: int = post.get("id", 0)
        url: str = post.get("file_url", "")
        rating: str = post.get("rating", "")
        source = post.get("source", "")
        danbooru_source = f"https://danbooru.donmai.us/posts/{id}"

        if is_url(source):
            desc = f"[source]({source}), [danbooru source]({danbooru_source})"
        else:
            desc = f"[danbooru source]({danbooru_source})"
        # Prepare the embed
        dominant_rgb = await get_dominant_rgb_from_url(post["preview_file_url"])
        color = discord.Colour.from_rgb(*dominant_rgb)
        embed = (
            discord.Embed(description=desc, color=color)
            .set_author(
                name=tag.replace("_", " "),
                icon_url="https://danbooru.donmai.us/packs/static/danbooru-logo-128x128-ea111b6658173e847734.png",
            )
            .set_image(url=url)
            .set_footer(text=post.get("tag_string_artist", "").replace("_", " "))
        )
        view = DanbooruView(ctx, tag)
        await ctx.respond(embed=embed, view=view)

    @commands.slash_command(
        name="danbooru",
        description="Get a random image from a danbooru tag ! (SFW only)",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def danbooru_(
        self,
        ctx: discord.ApplicationContext,
        tag: discord.Option(str, autocomplete=Danbooru.autocomplete),  # type: ignore
    ) -> None:
        asyncio.create_task(ctx.defer())
        await self.execute_danbooru_(ctx, tag)


def setup(bot):
    bot.add_cog(Danbooru_(bot))
