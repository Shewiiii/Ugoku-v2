import discord
import requests

from urllib.parse import unquote
from requests.exceptions import ConnectionError, MissingSchema
from pathlib import Path
import asyncio
import re

from bot.spotify import Spotify_
from bot.utils import sanitize_filename
from config import TEMP_SONGS_PATH
from main import bot


spotify = Spotify_()

# Temp songs folder
TEMP_SONGS_PATH.mkdir(parents=True, exist_ok=True)


class ServerSession:
    def __init__(self, guild_id: int, voice_client: discord.voice_client):
        self.guild_id = guild_id
        self.voice_client = voice_client
        self.queue = []
        self.to_loop = []
        self.loop_current = False
        self.loop_queue = False
        self.skipped = False
        # When skipping while looping current, that variable will be
        # True, so it tells the start_playing method that the song has been
        # skipped, and that that it has to show the "Now playing" message

    def display_queue(self) -> str:
        if not self.queue:
            return 'No songs in queue!'

        def format_song(index, song):
            title = song['element']['display_name']
            url = song['element']['url']
            return f"{index}. [{title}](<{url}>) ({song['source']})\n"

        elements = [
            "Currently playing: " + format_song("", self.queue[0])
        ]

        elements.extend(
            format_song(i, s) for i, s in enumerate(self.queue[1:], start=1)
        )

        if self.to_loop:
            elements.append('Songs in loop: \n')
            elements.extend(
                format_song(i, s) for i, s in enumerate(self.to_loop, start=1)
            )

        return ''.join(elements)

    async def start_playing(
        self,
        ctx: discord.ApplicationContext,
        successor: bool = False
    ) -> None:
        queue_item = self.queue[0]
        title = queue_item['element']['display_name']
        url = queue_item['element']['url']
        message = f'Now playing: [{title}](<{url}>)'

        if successor:
            await ctx.edit(content=message)
        else:
            if not self.loop_current or self.skipped:
                await ctx.send(message)

        # Reset skipped status
        self.skipped = False

        # Play audio from a source file
        audio_source = discord.FFmpegOpusAudio(
            queue_item['element']['source'],
            bitrate=510,
        )
        self.voice_client.play(
            audio_source,
            after=lambda e=None: self.after_playing(ctx, e)
        )

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        element: dict | str,
        source: str
    ) -> None:  # does not auto start playing the playlist
        queue_item = {'element': element, 'source': source}
        self.queue.append(queue_item)

        if len(self.queue) > 1:
            title = element['display_name']
            url = element['url']
            await ctx.edit(
                content=f"Added to queue: [{title}](<{url}>) !"
            )

        # Trigger playback
        if not self.voice_client.is_playing() and len(self.queue) <= 1:
            await self.start_playing(ctx=ctx, successor=True)

    def after_playing(
        self,
        ctx: discord.ApplicationContext,
        error: Exception,
    ) -> None:
        if error:
            raise error

        if self.queue:
            asyncio.run_coroutine_threadsafe(self.play_next(ctx), bot.loop)

    # should be called only after making the
    # first element of the queue the song to play
    async def play_next(self, ctx: discord.ApplicationContext) -> None:
        if self.loop_queue and not self.loop_current:
            self.to_loop.append(self.queue[0])

        if not self.loop_current:
            self.queue.pop(0)

        if not self.queue and self.loop_queue:
            self.queue, self.to_loop = self.to_loop, []

        await self.start_playing(ctx)


server_sessions: dict[ServerSession] = {}


async def connect(ctx: discord.ApplicationContext) -> ServerSession | None:
    user_voice = ctx.user.voice
    guild_id = ctx.guild.id
    if not user_voice:
        return

    channel = user_voice.channel

    if not ctx.voice_client:
        await channel.connect()

    if ctx.voice_client.is_connected():
        if guild_id not in server_sessions:
            server_sessions[guild_id] = ServerSession(
                guild_id, ctx.voice_client)
        return server_sessions[guild_id]


async def play_spotify(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    track_ids = await spotify.get_track_ids(user_input=query)

    if not track_ids:
        await ctx.edit(content='Track not found!')
        return

    for track_id in track_ids:
        await ctx.edit(content='Getting the song...')
        track_info = await spotify.get_track(track_id)
        await session.add_to_queue(ctx, track_info, source='Spotify')


async def play_custom(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    file_extension = re.search(r'\.(\w+)(?:\?|$)', query).group(1)
    legal_query = sanitize_filename(query)
    filename = f"{legal_query}.{file_extension}"
    path: Path = TEMP_SONGS_PATH / filename

    if not path.is_file():
        try:
            response = requests.get(query)
        except (MissingSchema, ConnectionError):
            await ctx.respond('No audio found!')
            return

        with open(path, 'wb') as file:
            file.write(response.content)

    display_name = re.search(r'(?:.+/)([^#?]+)', query)
    display_name = unquote(display_name.group(
        1)) if display_name else 'Custom track'

    track_info = {
        'display_name': display_name,
        'source': path,
        'url': query
    }

    await session.add_to_queue(ctx, track_info, source='Custom')
