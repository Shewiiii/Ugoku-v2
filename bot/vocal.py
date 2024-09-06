from config import CACHE_EXPIRY, CACHE_SIZE, TEMP_FOLDER, AUTO_LEAVE_DURATION
from datetime import datetime, timedelta
from urllib.parse import unquote
from datetime import datetime
from pathlib import Path
from time import time
from typing import Callable, Optional
import logging
import asyncio
import aiohttp
import hashlib
import re
import os

from discord.ui import Button, View
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

    async def display_queue(self, ctx: discord.ApplicationContext) -> None:
        view = QueueView(self.queue, self.to_loop, self.bot)
        await view.display(ctx)

    async def send_now_playing(self, ctx: discord.ApplicationContext) -> None:
        # Retrieve the current track_info from the queue
        track_info: dict = self.queue[0]['track_info']
        embed: Optional[discord.Embed] = track_info['embed']
        title: str = track_info['display_name']
        url: str = track_info['url']
        title_markdown = f'[{title}](<{url}>)'

        if embed:
            embed = await embed()
            if len(self.queue) > 1:
                next_track_info = self.queue[1]['track_info']
                next_track = (
                    f'[{next_track_info["display_name"]}](<{next_track_info["url"]}>)')
            else:
                next_track = 'End of queue!'

            # Update the embed with remaining tracks
            embed.add_field(
                name="Remaining Tracks",
                value=str(len(self.queue) - 1),
                inline=True
            )
            embed.add_field(
                name="Next",
                value=next_track, inline=True
            )

            message = ''  # No need for a text message if embed
        else:
            message = f'Now playing: {title_markdown}'

        # Send the message or edit the previous message based on the context
        await ctx.send(content=message, embed=embed)

    async def start_playing(self, ctx: discord.ApplicationContext) -> None:
        """Handles the playback of the next track in the queue."""
        if not self.queue:
            logging.info(f'Playback stopped in {self.guild_id}')
            await update_active_servers(self.bot)
            return  # No songs to play

        source = self.queue[0]['track_info']['source']
        # If source is a stream generator
        if isinstance(source, Callable):
            source = await source()  # Generate a fresh stream
            source.seek(167)  # Skip the non-audio content

        ffmpeg_source = discord.FFmpegOpusAudio(
            source,
            pipe=isinstance(source, AbsChunkedInputStream),
            bitrate=510
        )

        self.voice_client.play(
            ffmpeg_source,
            after=lambda e=None: self.after_playing(ctx, e)
        )

        await update_active_servers(self.bot, queue_item['element'])

        # Send "Now playing" at the end to slightly reduce audio latency
        if self.skipped or not self.loop_current:
            await self.send_now_playing(ctx)
            # Reset skip flag
            self.skipped = False

    async def add_to_queue(self, ctx: discord.ApplicationContext, tracks_info: list, source: str) -> None:
        for track_info in tracks_info:
            queue_item = {'track_info': track_info, 'source': source}
            self.queue.append(queue_item)

        # If only one song is added
        if len(tracks_info) == 1:
            title = tracks_info[0]['display_name']
            url = tracks_info[0]['url']
            await ctx.edit(content=f'Added to queue: [{title}](<{url}>) !')

        # If 2 or 3 songs are added
        elif len(tracks_info) in [2, 3]:
            titles_urls = ', '.join(
                f'[{track_info["display_name"]}](<{track_info["url"]}>)'
                for track_info in tracks_info
            )
            await ctx.edit(content=f'Added to queue: {titles_urls} !')

        # If more than 3 songs are added
        elif len(tracks_info) > 3:
            titles_urls = ', '.join(
                f'[{track_info["display_name"]}](<{track_info["url"]}>)'
                for track_info in tracks_info[:3]
            )
            additional_songs = len(tracks_info) - 3
            await ctx.edit(content=f'Added to queue: {titles_urls}, and {additional_songs} more song(s) !')

        if not self.voice_client.is_playing() and len(self.queue) >= 1:
            await self.start_playing(ctx)

    def after_playing(self, ctx: discord.ApplicationContext, error: Exception) -> None:
        self.last_played_time = datetime.now()
        if error:
            raise error

        if self.queue and self.voice_client.is_connected():
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
                await asyncio.sleep(1)
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


class QueueView(View):
    def __init__(self, queue, to_loop, bot, page=1) -> None:
        super().__init__()
        self.queue = queue
        self.to_loop = to_loop
        self.bot = bot
        self.page = page
        self.max_per_page = 7
        self.update_buttons()

    def update_buttons(self) -> None:
        # Hide or show buttons based on the current page and the number of queue items
        self.children[0].disabled = self.page <= 1
        self.children[1].disabled = len(
            self.queue) <= self.page * self.max_per_page

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary
    )
    async def previous_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        """Handles the 'Previous' button click."""
        self.page -= 1
        await self.update_view(interaction)

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary
    )
    async def next_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        """Handles the 'Next' button click."""
        self.page += 1
        await self.update_view(interaction)

    async def on_button_click(
        self,
        interaction: discord.Interaction
    ) -> None:
        if interaction.custom_id == 'prev_page':
            self.page -= 1
        elif interaction.custom_id == 'next_page':
            self.page += 1

        self.update_buttons()
        await interaction.response.edit_message(embed=await self.create_embed(), view=self)

    async def create_embed(self) -> discord.Embed:

        if not self.queue:
            embed = discord.Embed(
                title='Queue Overview',
                thumbnail=cover_data['url'],
                color=discord.Color.blurple()
            )
            embed.add_field(
                name='No songs in queue!',
                value=f"[{title}]({url})",
                inline=False
            )

            return embed

        # Get cover and color
        if self.queue[0]['source'] == 'Spotify':
            cover_data = await spotify.get_cover_data(self.queue[0]['track_info']['id'])
        else:
            cover_data = {'url': None, 'dominant_rgb': (145, 153, 252)}

        # Create the embed
        embed = discord.Embed(
            title="Queue Overview",
            thumbnail=cover_data['url'],
            color=discord.Color.from_rgb(*cover_data['dominant_rgb'])
        )

        # "Now playing" track section
        now_playing = self.queue[0]['track_info']
        title = now_playing['display_name']
        url = now_playing['url']
        embed.add_field(
            name="Now Playing",
            value=f"[{title}]({url})",
            inline=False
        )

        # Queue section
        start_index = (self.page - 1) * self.max_per_page
        end_index = min(start_index + self.max_per_page, len(self.queue))

        if len(self.queue) > 1:
            if start_index < end_index:
                queue_details = "\n".join(
                    f"{i}. [{self.queue[i]['track_info']['display_name']}]"
                    f"({self.queue[i]['track_info']['url']})"
                    for i in range(start_index + 1, end_index)
                )
                embed.add_field(
                    name="Queue", value=queue_details, inline=False)

        # Songs in loop section
        end_index = min(start_index + self.max_per_page, len(self.to_loop))

        if self.to_loop:
            loop_details = "\n".join(
                f"{i + 1}. [{self.to_loop[i]['track_info']['display_name']}]"
                f"({self.to_loop[i]['track_info']['url']})"
                for i in range(start_index, end_index)
            )
            embed.add_field(
                name="Songs in Loop",
                value=loop_details,
                inline=False
            )

        return embed

    async def display(self, ctx: discord.ApplicationContext) -> None:
        embed = await self.create_embed()
        await ctx.respond(embed=embed, view=self)

    async def update_view(self, interaction: discord.Interaction) -> None:
        """Update the view when a button is pressed."""
        self.update_buttons()
        await interaction.response.edit_message(embed=await self.create_embed(), view=self)


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


async def play_spotify(ctx: discord.ApplicationContext, query: str, session: ServerSession) -> None:
    tracks_info = await spotify.get_tracks(user_input=query)

    if not tracks_info:
        await ctx.edit(content='Track not found!')
        return

    await session.add_to_queue(ctx, tracks_info, source='Spotify')


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
        await ctx.edit(content=f'Error fetching audio: {str(e)}')
        return

    # Extract display name for the track
    display_name = re.search(r'(?:.+/)([^#?]+)', query)
    display_name = unquote(display_name.group(
        1)) if display_name else 'Custom track'

    track_info = {
        'display_name': display_name,
        'source': audio_path,
        'url': query,
        'embed': None,
        'id': None
    }

    await session.add_to_queue(ctx, [track_info], source='Custom')
