import asyncio
from bs4 import BeautifulSoup
from typing import TYPE_CHECKING

import discord
from bot import http_client


if TYPE_CHECKING:
    from commands.other.danbooru import Danbooru_


class DanbooruView(discord.ui.View):
    def __init__(self, ctx: discord.ApplicationContext, tag: str):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.tag = tag

    @discord.ui.button(label="More !")
    async def more_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        danbooru_cog: "Danbooru_" = self.ctx.bot.get_cog("Danbooru_")
        await danbooru_cog.execute_danbooru_(self.ctx, self.tag)


class Danbooru:
    def __init__(self):
        self.base_url = "https://danbooru.donmai.us/posts.json"

    async def autocomplete(self, ctx: discord.AutocompleteContext) -> list:
        search = ctx.options["tag"].replace(" ", "_")
        params = {"search[query]": search, "search[type]": "tag_query", "limit": 10}

        async with http_client.session.get(
            "https://danbooru.donmai.us/autocomplete", params=params
        ) as response:
            response.raise_for_status()
            raw = BeautifulSoup(await response.text(), features="html.parser")

        suggestions = [
            li.get("data-autocomplete-value")
            for li in raw.find_all("li", class_="ui-menu-item")
        ]
        return suggestions

    async def get_posts(
        self, tag: str, limit: int = 10, random: bool = True
    ) -> list[dict]:
        """Get Danboru posts from a tag."""
        params = {"limit": limit, "tags": tag, "random": str(random)}
        
        async with http_client.session.get(self.base_url, params=params) as response:
            response.raise_for_status()
            posts = await response.json()

        return posts
