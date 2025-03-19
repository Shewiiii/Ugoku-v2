from aiohttp_client_cache import CachedSession, SQLiteBackend
from bs4 import BeautifulSoup

import discord
from config import CACHE_EXPIRY


class Danbooru:
    def __init__(self):
        self.base_url = "https://danbooru.donmai.us/posts.json"

    async def autocomplete(self, ctx: discord.AutocompleteContext) -> list:
        search = ctx.options["tag"].replace(" ", "_")
        params = {"search[query]": search, "search[type]": "tag_query", "limit": 10}
        async with CachedSession(
            follow_redirects=True, cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
        ) as session:
            response = await session.get(
                "https://danbooru.donmai.us/autocomplete", params=params
            )
            response.raise_for_status()
        raw = BeautifulSoup(response.text(), features="html.parser")
        suggestions = [
            li.get("data-autocomplete-value")
            for li in raw.find_all("li", class_="ui-menu-item")
        ]
        return suggestions

    async def get_posts(self, tag: str, limit: int = 10, random: bool = True) -> list:
        """Get Danboru posts from a tag."""
        params = {"limit": limit, "tags": tag, "random": random}
        async with CachedSession(
            follow_redirects=True, cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
        ) as session:
            response = await session.get(self.base_url, params=params)
            response.raise_for_status()
        posts = response.json()

        return posts
