from typing import List

import discord
from discord.ui import View

from bot.vocal.custom import get_cover_data_from_hash
from bot.vocal.types import QueueItem
from config import DEFAULT_EMBED_COLOR


class QueueView(View):
    def __init__(
        self,
        queue: List[QueueItem],
        to_loop: List[QueueItem],
        bot: discord.Bot,
        page: int = 1
    ) -> None:
        super().__init__()
        self.queue = queue
        self.to_loop = to_loop
        self.bot = bot
        self.page = page
        self.max_per_page = 7
        self.update_buttons()

    def update_buttons(self) -> None:
        # Hide or show buttons based on the current page
        # and the number of queue items
        self.children[0].disabled = self.page <= 1
        self.children[1].disabled = len(
            self.queue) < self.page * self.max_per_page

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary
    )
    async def previous_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        """Handles the 'Previous' button click."""
        self.page -= 1
        await self.update_view(interaction)

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary
    )
    async def next_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        """Handles the 'Next' button click."""
        self.page += 1
        await self.update_view(interaction)

    async def on_button_click(
        self,
        interaction: discord.Interaction
    ) -> None:
        if interaction.custom_id == 'prev_page':
            self.page -= 1
        elif interaction.custom_id == 'next_page':
            self.page += 1

        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_embed(),
            view=self
        )

    async def create_embed(self) -> discord.Embed:
        if not self.queue:
            embed = discord.Embed(
                title='Queue Overview',
                color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
                description='No songs in queue!'
            )
            return embed

        # Get cover and colors of the NOW PLAYING song
        source: str = self.queue[0]['source']
        track_info: dict = self.queue[0]['track_info']
        if source == 'Spotify':
            # Cover data is not stored in the track info,
            # but only got when requested like here.
            # It allows the bot to bulk add songs (e.g from a playlist),
            # with way few API requests
            # TODO: cache the cover data
            cover_data = await self.bot.spotify.get_cover_data(track_info['id'])
        elif source == 'Custom':
            cover_data = await get_cover_data_from_hash(track_info['id'])

        # Create the embed
        embed = discord.Embed(
            title="Queue Overview",
            thumbnail=cover_data['url'],
            color=discord.Color.from_rgb(*cover_data['dominant_rgb'])
        )

        # "Now playing" track section
        now_playing = self.queue[0]['track_info']
        title = now_playing['display_name']
        url = now_playing['url']
        embed.add_field(
            name="Now Playing",
            value=f"[{title}]({url})",
            inline=False
        )

        # Queue section
        start_index = (self.page - 1) * self.max_per_page
        end_index = min(start_index + self.max_per_page, len(self.queue))

        if len(self.queue) > 1:
            if start_index < end_index:
                queue_details = "\n".join(
                    f"{i}. [{self.queue[i]['track_info']['display_name']}]"
                    f"({self.queue[i]['track_info']['url']})"
                    for i in range(start_index + 1, end_index)
                )
                embed.add_field(
                    name="Queue", value=queue_details, inline=False)

        # Songs in loop section
        end_index = min(start_index + self.max_per_page, len(self.to_loop))

        if self.to_loop:
            loop_details = "\n".join(
                f"{i + 1}. [{self.to_loop[i]['track_info']['display_name']}]"
                f"({self.to_loop[i]['track_info']['url']})"
                for i in range(start_index, end_index)
            )
            embed.add_field(
                name="Songs in Loop",
                value=loop_details,
                inline=False
            )

        return embed

    async def display(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        embed = await self.create_embed()
        await ctx.respond(embed=embed, view=self)

    async def update_view(
        self,
        interaction: discord.Interaction
    ) -> None:
        """Update the view when a button is pressed."""
        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_embed(),
            view=self
        )
