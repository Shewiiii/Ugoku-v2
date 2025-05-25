import asyncio
import discord
from discord.ext import commands

from bot.utils import vocal_action_check
from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from bot.vocal.track_dataclass import Track


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
        asyncio.create_task(ctx.defer())
        guild_id = ctx.guild.id
        session: ServerSession = sm.server_sessions.get(guild_id)
        if not vocal_action_check(session, ctx, ctx.respond):
            return

        removed_tracks = []
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

        if mode == "Single" and not index == 0:
            removed_tracks: list[Track] = [session.queue.pop(index)]

        elif mode == "Before (included)":
            if not index <= 0:  # -1 is not appropriate here
                removed_tracks.extend(queue[1 : index + 1])
            session.queue = [queue[0]] + queue[index + 1 :]

        elif mode == "After (included)":
            index = max(min(index, len(queue)), 1)  # Don't kill the playing song
            removed_tracks.extend(queue[index:])
            session.queue = queue[:index]

        # Clear old tracks and preload the following ones
        tasks = []
        for track in removed_tracks:
            tasks.append(track.close())
        # Important to be before the skip
        tasks.append(session.load_next_tracks())
        await asyncio.gather(*tasks, return_exceptions=True)

        # Skip if the track is currently playing
        if index == 0:
            removed_tracks.append(queue[0])
            skip_cog = session.bot.get_cog("Skip")
            asyncio.create_task(skip_cog.execute_skip(ctx, silent=True))
        else:
            asyncio.create_task(session.update_now_playing(ctx))

        # Send message
        c = len(removed_tracks)
        titles = ", ".join(f"{track:markdown}" for track in removed_tracks[:3])
        message = (
            f"Removed: {titles}{' !' if c <= 3 else f', and {c - 3} more songs !'}"
        )
        asyncio.create_task(ctx.respond(message))


def setup(bot):
    bot.add_cog(RemoveSong(bot))
