import logging
from typing import Optional

import discord
from discord.ext import commands

from bot.vocal.server_session import ServerSession
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
        if not session:
            await ctx.respond("No active session!")
            return

        if not session.queue:
            await ctx.respond("No song in queue !")
            return

        removed_tracks = []
        queue = session.queue
        tracks_info = [element['track_info'] for element in queue]
        # If a song is specified, find its index in the queue
        if song:
            for i, track_info in enumerate(tracks_info):
                if track_info['display_name'] == song:
                    index = i
                    break

        if not index:
            # If index is 0 or None
            pass
        elif mode == 'Single' and len(queue) >= index >= -1:
            removed_tracks: list[Optional[dict]] = [session.queue.pop(index)]
        elif mode == 'After (included)':
            removed_tracks = queue[index:]
            session.queue = queue[:index]
        elif mode == 'Before (included)':
            removed_tracks = queue[:index]
            session.queue = queue[index:]

        # Send message
        # If no song removed
        count = len(removed_tracks)
        r_tracks_info = [track['track_info'] for track in removed_tracks]
        if count == 0:
            await ctx.respond("No song has been removed !")

        # If only one song is removed
        elif count == 1:
            title = r_tracks_info[0]['display_name']
            url = r_tracks_info[0]['url']
            await ctx.respond(content=f'Removed: [{title}](<{url}>) !')

        # If 2 or 3 songs are removed
        elif count in [2, 3]:
            titles_urls = ', '.join(
                f'[{track["display_name"]}](<{track["url"]}>)'
                for track in r_tracks_info
            )
            await ctx.respond(content=f'Removed: {titles_urls} !')

        # If more than 3 songs are removed
        elif count > 3:
            titles_urls = ', '.join(
                f'[{track["display_name"]}](<{track["url"]}>)'
                for track in r_tracks_info[:3]
            )
            additional_songs = count - 3
            await ctx.respond(
                content=(
                    f'Removed: {titles_urls}, and '
                    f'{additional_songs} more song(s) !')
            )


def setup(bot):
    bot.add_cog(PopSong(bot))
