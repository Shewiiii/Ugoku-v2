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

    song = ctx.options['song'].lower()
    songs = [element['track_info']['display_name']
             for element in session.queue]
    if song:
        search = []
        for s in songs:
            if song in s.lower():
                search.append(s)
        return search
    else:
        return songs


class PopSong(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name='pop',
        description='Pop a song in the queue.'
    )
    async def pop(
        self,
        ctx: discord.ApplicationContext,
        mode: discord.Option(
            str,
            description="Select what song to remove.",
            choices=['Single', 'After (included)', 'Before (included)']
        ),  # type: ignore
        index: discord.Option(
            int,
            description="The index of the song to point. -1 to point to the last song.",
            default=None
        ),  # type: ignore
        song: discord.Option(
            str,
            autocomplete=autocomplete,
            default=None
        )  # type: ignore
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond):
            return

        removed_tracks = []
        queue = session.queue
        # If a song is specified, find its index in the queue
        if song:
            for i, track_info in enumerate([e['track_info'] for e in queue]):
                if track_info['display_name'] == song:
                    index = i
                    break

        # Remove tracks
        if not index or not -1 <= index < len(queue):
            await ctx.respond("No song has been removed !")
            return
        elif mode == 'Single':
            removed_tracks: list[Optional[dict]] = [session.queue.pop(index)]
        elif mode == 'Before (included)':
            removed_tracks, session.queue = queue[:index], queue[index:]
        elif mode == 'After (included)':
            index = min(index, len(queue))
            removed_tracks, session.queue = queue[index:], queue[:index]

        # Send message
        c = len(removed_tracks)
        r_tracks_info = [track['track_info'] for track in removed_tracks]
        titles = ', '.join(
            f'[{t["display_name"]}](<{t["url"]}>)' for t in r_tracks_info[:3]
        )
        message = f'Removed: {titles}{" !" if c <= 3 else f", and {c-3} more songs !"}'
        asyncio.create_task(ctx.respond(message))
        asyncio.create_task(session.update_now_playing(ctx))


def setup(bot):
    bot.add_cog(PopSong(bot))
