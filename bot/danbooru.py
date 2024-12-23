import httpx
from bs4 import BeautifulSoup

import discord


class Danbooru:
    def __init__(self):
        self.session = httpx.AsyncClient(follow_redirects=True)
        self.base_url = "https://danbooru.donmai.us/posts.json"

    @ staticmethod
    async def autocomplete(
        ctx: discord.AutocompleteContext
    ) -> list:
        search = ctx.options['tag'].replace(' ', '_')
        async with httpx.AsyncClient(follow_redirects=True) as session:
            params = {
                "search[query]": search,
                "search[type]": "tag_query",
                "limit": 10
            }
            response = await session.get(
                "https://danbooru.donmai.us/autocomplete",
                params=params
            )
            raw = BeautifulSoup(response.text, features="html.parser")
            suggestions = [
                li.get('data-autocomplete-value')
                for li in raw.find_all('li', class_='ui-menu-item')
            ]
            return suggestions

    async def get_posts(
        self,
        tag: str,
        limit: int = 10,
        random: bool = True
    ) -> list:
        """Get Danboru posts from a tag."""
        params = {
            'limit': limit,
            'tags': tag,
            'random': random
        }
        response = await self.session.get(self.base_url, params=params)
        response.raise_for_status()
        posts = response.json()

        return posts
