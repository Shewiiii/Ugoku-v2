import asyncio
from typing import Optional

import discord
from discord.ext import commands

from bot.vocal.server_session import ServerSession
from bot.utils import vocal_action_check
from bot.vocal.session_manager import session_manager as sm


async def autocomplete(ctx: discord.AutocompleteContext) -> list:
    """Return the name of all the songs in the queue."""
    guild_id = ctx.interaction.guild.id
    session: ServerSession = sm.server_sessions.get(guild_id)
    if not session:
        return []

    song = ctx.options["song"].lower()
    songs = [str(element) for element in session.queue]
    if song:
        search = []
        for s in songs:
            if song in s.lower():
                search.append(s)
        return search
    else:
        return songs


class RemoveSong(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="remove", description="Remove songs in the queue.")
    async def remove(
        self,
        ctx: discord.ApplicationContext,
        mode: discord.Option(
            str,
            description="Select what song to remove.",
            choices=["Single", "After (included)", "Before (included)"],
        ),  # type: ignore
        song: discord.Option(str, autocomplete=autocomplete, default=None),  # type: ignore
        index: discord.Option(
            int,
            description="The index of the song to point. -1 to point to the last song.",
            default=None,
        ),  # type: ignore
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond):
            return

        removed_tracks = []
        embed_updated = False
        queue = session.queue
        # If a song is specified, find its index in the queue
        if song:
            for i, track in enumerate(queue):
                if str(track) == song:
                    index = i
                    break

        # Remove tracks
        if index is None or not -1 <= index < len(queue):
            await ctx.respond("No song has been removed !")
            return
        elif mode == "Single":
            removed_tracks: list[Optional[dict]] = [session.queue.pop(index)]
            if index == 0:
                # Track currently playing
                skip_cog = session.bot.get_cog("Skip")
                asyncio.create_task(skip_cog.execute_skip(ctx, silent=True))
                embed_updated = True
        elif mode == "Before (included)":
            removed_tracks, session.queue = queue[:index], queue[index:]
        elif mode == "After (included)":
            index = min(index, len(queue))
            removed_tracks, session.queue = queue[index:], queue[:index]

        # Send message
        c = len(removed_tracks)
        titles = ", ".join(f"{track:markdown}" for track in removed_tracks[:3])
        message = (
            f"Removed: {titles}{' !' if c <= 3 else f', and {c - 3} more songs !'}"
        )
        asyncio.create_task(ctx.respond(message))
        if not embed_updated:
            asyncio.create_task(session.update_now_playing(ctx))


def setup(bot):
    bot.add_cog(RemoveSong(bot))
