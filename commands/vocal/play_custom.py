import asyncio
from typing import Tuple

import discord
from discord.ext import commands

from commands.vocal.play import Play


class PlayCustom(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending: dict[int, Tuple[int, discord.ApplicationContext]] = {}

    @commands.slash_command(
        name="play-custom", description="Upload a song to play it in vc !"
    )
    async def play_custom(self, ctx: discord.ApplicationContext) -> None:
        user_id = ctx.user.id
        channel_id = ctx.channel.id
        self.pending[user_id] = (ctx, channel_id)
        asyncio.create_task(ctx.respond("Send any song file to play !"))
        await asyncio.sleep(60)
        if user_id in self.pending:
            asyncio.create_task(
                ctx.respond(f"Play-custom canceled for {ctx.author.global_name}.")
            )
            del self.pending[user_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        user_id = message.author.id
        ctx, channel_id = self.pending.get(user_id, (None, None))
        if channel_id == message.channel.id == channel_id:
            # Play !
            play_cog: Play = self.bot.get_cog("Play")
            await play_cog.execute_play(
                ctx, query=message.jump_url, service="Custom", defer=False
            )
            del self.pending[user_id]


def setup(bot):
    bot.add_cog(PlayCustom(bot))
