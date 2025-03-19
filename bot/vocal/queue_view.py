import asyncio
from typing import List

import discord
from discord.ui import View

from bot.vocal.custom import get_cover_data_from_file
from bot.utils import split_into_chunks
from bot.vocal.track_dataclass import Track
from config import DEFAULT_EMBED_COLOR


class QueueView(View):
    def __init__(
        self,
        queue: List[dict],
        to_loop: List[dict],
        bot: discord.Bot,
        is_playing: bool,
        page: int = 1,
    ) -> None:
        super().__init__()
        self.queue = queue
        self.to_loop = to_loop
        self.bot = bot
        self.is_playing = is_playing
        self.page = page
        self.max_per_page = 7
        self.update_buttons()

    def update_buttons(self) -> None:
        """Disable or enable 'next' and 'previous' buttons based on the current page."""
        self.children[0].disabled = self.page <= 1
        self.children[1].disabled = len(self.queue) <= self.page * self.max_per_page

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Update the page on 'previous' click."""
        self.page -= 1
        await self.update_view(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Update the page on 'Next' click."""
        self.page += 1
        await self.update_view(interaction)

    async def on_button_click(self, interaction: discord.Interaction) -> None:
        """Change the page of the embed."""
        if interaction.custom_id == "prev_page":
            self.page -= 1
        elif interaction.custom_id == "next_page":
            self.page += 1

        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_embed(), view=self
        )

    async def create_embed(self) -> discord.Embed:
        default_color = discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR)
        if not self.queue:
            embed = discord.Embed(
                title="Queue Overview",
                color=default_color,
                description="No songs in queue!",
            )
            return embed

        # Get cover and colors of the NOW PLAYING song
        track: Track = self.queue[0]
        if track.service == "custom":
            cover_data = await get_cover_data_from_file(track.id)
        else:
            if track.unloaded_embed:
                await track.generate_embed()
            embed = track.embed
            cover_data = {
                "cover_url": track.cover_url,
                "dominant_rgb": embed.color if embed and embed.color else default_color,
            }

        # Create the embed
        embed = discord.Embed(
            title="Queue Overview",
            thumbnail=cover_data.get("cover_url"),
            color=cover_data["dominant_rgb"],
        )

        # Time indication
        time_string = f"{track.timer.get()}s / {track.duration}s"

        # "Now playing" track section
        embed.add_field(
            # Now playing + time indication
            name=f"Now Playing - {time_string}",
            value=f"{track:markdown}",
            inline=False,
        )

        # Queue section
        start_index = (self.page - 1) * self.max_per_page
        end_index = min(start_index + self.max_per_page, len(self.queue))

        if len(self.queue) > 1:
            if start_index < end_index:
                queue_details = "\n".join(
                    f"{i}. {self.queue[i]:markdown}"
                    for i in range(start_index + 1, end_index)
                )
                # Split the queue (if too long)
                splitted: list = split_into_chunks(queue_details)
                embed.add_field(name="Queue", value=splitted[0], inline=False)
                for part in splitted[1:]:
                    embed.add_field(name="", value=part, inline=False)

        # Songs in loop section
        end_index = min(start_index + self.max_per_page, len(self.to_loop))

        if self.to_loop:
            loop_details = "\n".join(
                f"{i + 1}. {self.to_loop[i]:markdown}"
                for i in range(start_index, end_index)
            )
            embed.add_field(name="Songs in Loop", value=loop_details, inline=False)

        return embed

    async def display(
        self, ctx: discord.ApplicationContext, defer_task: asyncio.Task
    ) -> None:
        """Display the queue view in response to a command."""
        embed = await self.create_embed()
        await defer_task
        await ctx.respond(embed=embed, view=self)

    async def update_view(self, interaction: discord.Interaction) -> None:
        """Update the queue view in response to a button interaction."""
        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_embed(), view=self
        )
