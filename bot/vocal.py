import discord

from config import CACHE_EXPIRY, CACHE_SIZE, TEMP_FOLDER
from urllib.parse import unquote
from pathlib import Path
from time import time
import asyncio
import aiohttp
import hashlib
import re
import os

from bot.spotify import Spotify_
from librespot.audio import AbsChunkedInputStream


spotify = Spotify_()


class ServerSession:
    def __init__(self, guild_id: int, voice_client: discord.voice_client, bot=discord.Bot):
        self.guild_id = guild_id
        self.voice_client = voice_client
        self.queue = []
        self.to_loop = []
        self.loop_current = False
        self.loop_queue = False
        self.skipped = False
        self.bot = bot
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
        elif not self.loop_current or self.skipped:
            await ctx.send(message)

        # Reset skipped status
        self.skipped = False

        source = queue_item['element']['source']
        pipe = isinstance(source, AbsChunkedInputStream)

        if queue_item['source'] == 'Custom':
            ffmpeg_source = discord.FFmpegOpusAudio(
                source,
                pipe=pipe
            )

        elif queue_item['source'] == 'Spotify':
            ffmpeg_source = discord.FFmpegOpusAudio(
                source,
                pipe=True
            )

        else:
            await ctx.send("Unsupported source type!")
            return

        self.voice_client.play(
            ffmpeg_source,
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
        error: Exception
    ) -> None:
        if error:
            raise error

        if self.queue:
            asyncio.run_coroutine_threadsafe(
                self.play_next(ctx), self.bot.loop)

    async def play_next(self, ctx: discord.ApplicationContext) -> None:
        if self.loop_queue and not self.loop_current:
            self.to_loop.append(self.queue[0])

        if not self.loop_current:
            self.queue.pop(0)

        if not self.queue and self.loop_queue:
            self.queue, self.to_loop = self.to_loop, []

        await self.start_playing(ctx)


server_sessions: dict[ServerSession] = {}


async def connect(ctx: discord.ApplicationContext, bot: discord.Bot) -> ServerSession | None:
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
                guild_id, ctx.voice_client, bot)
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
        track_info = await spotify.get_track(track_id)
        await session.add_to_queue(ctx, track_info, source='Spotify')


# Cache functions for custom sources

def get_cache_path(url: str) -> Path:
    # Hash the URL to create a unique filename
    hash_digest = hashlib.md5(url.encode('utf-8')).hexdigest()
    return TEMP_FOLDER / f"{hash_digest}.cache"


def cleanup_cache():
    files = sorted(TEMP_FOLDER.glob('*.cache'), key=os.path.getmtime)

    # Remove files that exceed the cache size limit
    while len(files) > CACHE_SIZE:
        oldest_file = files.pop(0)
        oldest_file.unlink()

    # Remove expired files
    current_time = time()
    for file in files:
        if current_time - file.stat().st_mtime > CACHE_EXPIRY:
            file.unlink()


async def fetch_audio_stream(url: str) -> Path:
    cache_path = get_cache_path(url)

    # If the file exists and is not expired, return it
    if cache_path.is_file():
        if time() - cache_path.stat().st_mtime < CACHE_EXPIRY:
            return cache_path
        else:
            cache_path.unlink()  # Remove expired file

    # Fetch the audio file from the URL asynchronously
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch audio: {response.status}")
            audio_data = await response.read()

    # Write the fetched audio to the cache file
    with cache_path.open('wb') as cache_file:
        cache_file.write(audio_data)

    cleanup_cache()

    return cache_path


async def play_custom(ctx: discord.ApplicationContext, query: str, session: ServerSession) -> None:
    try:
        audio_path = await fetch_audio_stream(query)
    except Exception as e:
        await ctx.respond(f'Error fetching audio: {str(e)}')
        return

    # Extract display name for the track
    display_name = re.search(r'(?:.+/)([^#?]+)', query)
    display_name = unquote(display_name.group(
        1)) if display_name else 'Custom track'

    track_info = {
        'display_name': display_name,
        'source': audio_path,
        'url': query
    }

    await session.add_to_queue(ctx, track_info, source='Custom')
