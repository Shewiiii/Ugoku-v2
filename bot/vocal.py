from config import CACHE_EXPIRY, CACHE_SIZE, TEMP_FOLDER, AUTO_LEAVE_DURATION
from datetime import datetime, timedelta
from urllib.parse import unquote
from datetime import datetime
from pathlib import Path
from time import time
from typing import Callable
import logging
import asyncio
import aiohttp
import hashlib
import re
import os

import discord

from bot.spotify import Spotify_
from librespot.audio import AbsChunkedInputStream

from bot.utils import update_active_servers

spotify = Spotify_()


class ServerSession:
    def __init__(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient,
        bot: discord.Bot,
        channel_id: int
    ):
        self.guild_id = guild_id
        self.voice_client = voice_client
        self.queue = []
        self.to_loop = []
        self.last_played_time = datetime.now()
        self.loop_current = False
        self.loop_queue = False
        self.skipped = False
        self.bot = bot
        self.channel_id = channel_id
        self.auto_leave_task = asyncio.create_task(
            self.check_auto_leave())

    def display_queue(self) -> str:
        if not self.queue:
            return 'No songs in queue!'

        def format_song(index: int, song: dict) -> str:
            title = song['element']['display_name']
            url = song['element']['url']
            return f"{index}. [{title}](<{url}>) ({song['source']})\n"

        elements = [
            'Currently playing: ' + format_song('', self.queue[0])
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

    async def start_playing(self, ctx: discord.ApplicationContext, successor: bool = False) -> None:
        if not self.queue:
            self.last_played_time = datetime.now()
            logging.info(f'Playback stopped in {self.guild_id}')
            await update_active_servers(self.bot)
            return  # No songs to play

        queue_item = self.queue[0]
        title = queue_item['element']['display_name']
        artist = queue_item['element']['artist']
        album = queue_item['element']['album']
        cover = queue_item['element']['cover']
        duration = queue_item['element']['duration']
        url = queue_item['element']['url']
        message = f'Now playing: [{title}](<{url}>)'

        if successor:
            await ctx.edit(content=message)
        elif not self.loop_current or self.skipped:
            await ctx.send(message)

        self.skipped = False

        source = queue_item['element']['source']
        pipe = isinstance(source, Callable)

        if pipe:
            # Generate a fresh stream to prevent any issues, like bandwidth heavy availability checks
            source = await source()
            # Don't change this
            source.seek(167)

        ffmpeg_source = discord.FFmpegOpusAudio(
            source,
            pipe=pipe,
            bitrate=510
        )

        self.voice_client.play(
            ffmpeg_source,
            after=lambda e=None: self.after_playing(ctx, e)
        )

        await update_active_servers(self.bot, queue_item['element'])

    async def add_to_queue(self, ctx: discord.ApplicationContext, element: dict, source: str) -> None:
        queue_item = {'element': element, 'source': source}
        self.queue.append(queue_item)

        if len(self.queue) > 1:
            title = element['display_name']
            url = element['url']
            await ctx.edit(
                content=f'Added to queue: [{title}](<{url}>) !'
            )

        if not self.voice_client.is_playing() and len(self.queue) == 1:
            await self.start_playing(ctx, successor=True)

    def after_playing(self, ctx: discord.ApplicationContext, error: Exception) -> None:
        if error:
            raise error

        if self.queue:
            asyncio.run_coroutine_threadsafe(
                self.play_next(ctx), self.bot.loop
            )

    async def play_next(self, ctx: discord.ApplicationContext) -> None:
        if self.loop_queue and not self.loop_current:
            self.to_loop.append(self.queue[0])

        if not self.loop_current:
            self.queue.pop(0)

        if not self.queue and self.loop_queue:
            self.queue, self.to_loop = self.to_loop, []

        await self.start_playing(ctx)

    async def check_auto_leave(self) -> None:
        while self.voice_client.is_connected():
            if not self.voice_client.is_playing():
                time_since_last_played = datetime.now() - self.last_played_time
                time_until_disconnect = timedelta(
                    seconds=AUTO_LEAVE_DURATION) - time_since_last_played

                logging.info(
                    'Time until disconnect due to '
                    f'inactivity in {self.guild_id}: '
                    f'{time_until_disconnect}'
                )

                if time_until_disconnect <= timedelta(seconds=0):
                    await self.voice_client.disconnect()
                    del server_sessions[self.guild_id]
                    channel = self.bot.get_channel(self.channel_id)
                    if channel:
                        await channel.send('Baibai~')
                    logging.info(
                        f'Deleted audio session in {self.guild_id} '
                        'due to inactivity.'
                    )
                    break

            await asyncio.sleep(17)


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
                guild_id,
                ctx.voice_client,
                bot,
                ctx.channel_id
            )
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
    return TEMP_FOLDER / f'{hash_digest}.cache'


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
                raise Exception(f'Failed to fetch audio: {response.status}')
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
        'url': query,
        'id': None
    }

    await session.add_to_queue(ctx, track_info, source='Custom')
