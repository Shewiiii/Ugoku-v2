import asyncio
import discord
from discord.ext import commands
from typing import Optional

from bot.chatbot.vector_recall import memory
from bot.chatbot.gemini import Gembot
from bot.utils import split_into_chunks
from config import DEFAULT_EMBED_COLOR


class ForgetView(discord.ui.View):
    def __init__(
        self,
        id_: int,
        embed: discord.Embed,
        vectors: list,
        channel: discord.TextChannel,
    ):
        super().__init__(timeout=None)
        self.id_ = id_
        self.page = 1
        self.max_per_page = 10
        self.embed: discord.Embed = embed
        self.vectors: list = vectors
        self.update()
        self.channel: discord.TextChannel = channel
        self.webhook_msg: Optional[discord.WebhookMessage] = None

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Update the page on 'previous' click."""
        await interaction.response.defer()
        self.page -= 1
        self.update()
        await self.webhook_msg.edit(embed=self.embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Update the page on 'Next' click."""
        await interaction.response.defer()
        self.page += 1
        self.update()
        await self.webhook_msg.edit(embed=self.embed, view=self)

    @discord.ui.select(
        placeholder="Choose a vector",
        min_values=1,
        max_values=1,
        options=[discord.SelectOption(label="1. You should not see this")],
    )
    async def select_callback(self, select, interaction: discord.Interaction) -> None:
        asyncio.create_task(interaction.response.defer())
        removed_vector_ids: list = select.values
        self.vectors = [
            vector for vector in self.vectors if vector["id"] not in removed_vector_ids
        ]

        await asyncio.to_thread(memory.index.delete, removed_vector_ids)
        await self.channel.send(
            f"Removed {len(removed_vector_ids)} vector{'s' if len(removed_vector_ids) > 1 else ''} !"
        )
        self.update()
        await self.webhook_msg.edit(embed=self.embed, view=self)

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.secondary,
    )
    async def close_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await interaction.message.delete()
        self.clear_items()
        self.ctx = self.bot = None

    def update(self) -> None:
        # Vector list
        start_index = (self.page - 1) * self.max_per_page
        end_index = min(start_index + self.max_per_page, len(self.vectors))
        # If a vector is deleted on page 2 or more, and no vector is remaining,
        # come back to the previous page
        if self.page > 1 and end_index - start_index == 0:
            self.page -= 1
            return self.update()
        vector_text_list = "\n".join(
            [
                f"{i + 1}. {self.vectors[i]['metadata']['text']}"
                for i in range(start_index, end_index)
            ]
        )
        splitted = split_into_chunks(vector_text_list)
        self.embed.fields = []
        self.embed.add_field(name="Results", value=splitted[0] if splitted else "")
        for part in splitted[1:]:
            self.embed.add_field(name="", value=part)

        # Buttons
        self.children[0].disabled = self.page <= 1
        self.children[1].disabled = len(self.vectors) <= self.page * self.max_per_page

        # Select menu
        self.children[2].disabled = end_index - start_index == 0
        if end_index - start_index != 0:
            self.children[2].max_values = end_index - start_index
            self.children[2].options = [
                discord.SelectOption(
                    label=f"{i + 1}. {self.vectors[i]['metadata']['text'][:95]}",
                    value=self.vectors[i]["id"],
                )
                for i in range(start_index, end_index)
            ]


class Forget(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="forget",
        description="Forget a specific Pinecone entry in your server or channel.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def forget(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, "Search the entry you want to delete.", default=""),  # type: ignore
    ) -> None:
        # I await afterward to gain a few ms
        defer_task = asyncio.create_task(ctx.defer())
        id_ = Gembot.get_chat_id(ctx, gemini_command=True)
        if not id_:
            await defer_task
            await ctx.respond(
                "Invalid location ! Try again in another channel or server."
            )
            return
        vectors = await memory.get_vectors(query, id_)
        if not vectors:
            await defer_task
            await ctx.respond("No Pinecone entry has been found !")
            return

        embed = discord.Embed(
            color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
        ).set_author(name="Forget a vector:")

        view = ForgetView(id_=id_, embed=embed, vectors=vectors, channel=ctx.channel)
        await defer_task
        webhook_msg = await ctx.respond(view=view, embed=embed)
        view.webhook_msg = webhook_msg


def setup(bot):
    bot.add_cog(Forget(bot))
