import asyncio
import re
from typing import Tuple

import discord
from discord.ext import commands


class Emotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending: dict[int, Tuple[int, asyncio.Event]] = {}

    @commands.slash_command(
        name="get-emotes", description="Get the direct URL of emotes or stickers."
    )
    async def get_emote(self, ctx: discord.ApplicationContext) -> None:
        # Wait for a user message
        user_id = ctx.user.id
        channel_id = ctx.channel.id
        pending_event = asyncio.Event()
        self.pending[user_id] = (channel_id, pending_event)
        asyncio.create_task(
            ctx.respond(
                "Send any emotes or stickers, or reply to a message !"
            )
        )
        try:
            await asyncio.wait_for(pending_event.wait(), 180.0)
        except TimeoutError:
            if user_id in self.pending:
                asyncio.create_task(
                    ctx.respond(f"Get emotes canceled for {ctx.author.global_name}.")
                )
                del self.pending[user_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        user_id = message.author.id
        channel_id, pending_event = self.pending.get(user_id, (None, None))
        if channel_id == message.channel.id == channel_id:
            pending_event.set()

            # data is containing tuples: ('name', 'snowflake')
            data = []
            stickers = message.stickers

            # Reference message (if any)
            rmessage_content = ""
            if message.reference and message.reference.message_id:
                rid = message.reference.message_id
                rmessage = await message.channel.fetch_message(rid)
                rmessage_content = rmessage.content
                stickers.extend(rmessage.stickers)

            # Process stickers
            for sticker in stickers:
                data.append((sticker.name, sticker.url))

            # Process custom emojis
            search = re.findall(
                r"<(?P<animated>a?):(?P<name>[^:]+):(?P<snowflake>\d+)>",
                message.content + rmessage_content,
            )
            for animated, emote_name, snowflake in search:
                base_url = f"https://cdn.discordapp.com/emojis/{snowflake}"
                url = f"{base_url}.gif" if animated else f"{base_url}.png"
                # If not a duplicate
                if (emote_name, url) not in data:
                    data.append((emote_name, url))

            # No emote or sticker found
            if not data:
                await message.channel.send("oi (Canceled)")
                del self.pending[user_id]
                return

            string = "Here you go !\n" + "\n".join(
                [f"{name}: <{url}>" for name, url in data]
            )
            del self.pending[user_id]
            await message.channel.send(string)


def setup(bot):
    bot.add_cog(Emotes(bot))
