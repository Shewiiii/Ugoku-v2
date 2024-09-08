from config import AUTO_LEAVE_DURATION, DEFAULT_EMBED_COLOR
from datetime import datetime, timedelta
from typing import Callable, Optional
from urllib.parse import unquote
from requests import HTTPError
from datetime import datetime
import aiohttp
import logging
import asyncio
import re

from discord.ui import View
import discord

from bot.custom import fetch_audio_stream, generate_info_embed, get_cover_data_from_hash, upload_cover
from bot.utils import get_metadata, extract_cover_art, extract_number, get_accent_color_from_url
from librespot.audio import AbsChunkedInputStream
from bot.spotify import Spotify_
from bot.onsei import Onsei

spotify = Spotify_()
onsei = Onsei()


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
            self.check_auto_leave()
        )

    async def display_queue(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        view = QueueView(self.queue, self.to_loop, self.bot)
        await view.display(ctx)

    async def send_now_playing(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        # Retrieve the current track_info from the queue
        track_info: dict = self.queue[0]['track_info']
        embed: Optional[discord.Embed] = track_info['embed']
        title: str = track_info['display_name']
        url: str = track_info['url']
        title_markdown = f'[{title}](<{url}>)'

        if embed:
            # In case it requires additional api calls,
            # The embed is generated when needed only.
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

    async def start_playing(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        """Handles the playback of the next track in the queue."""
        if not self.queue:
            logging.info(f'Playback stopped in {self.guild_id}')
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

        # Send "Now playing" at the end to slightly reduce audio latency
        if self.skipped or not self.loop_current:
            await self.send_now_playing(ctx)
            # Reset skip flag
            self.skipped = False

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks_info: list,
        source: str
    ) -> None:
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
            await ctx.edit(
                content=(
                    f'Added to queue: {titles_urls}, and '
                    f'{additional_songs} more song(s) !')
            )

        if not self.voice_client.is_playing() and len(self.queue) >= 1:
            await self.start_playing(ctx)

    def after_playing(
        self,
        ctx: discord.ApplicationContext,
        error: Exception
    ) -> None:
        self.last_played_time = datetime.now()
        if error:
            raise error

        if self.queue and self.voice_client.is_connected():
            asyncio.run_coroutine_threadsafe(
                self.play_next(ctx), self.bot.loop
            )

    async def play_next(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
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
    def __init__(
        self,
        queue,
        to_loop,
        bot,
        page=1
    ) -> None:
        super().__init__()
        self.queue = queue
        self.to_loop = to_loop
        self.bot = bot
        self.page = page
        self.max_per_page = 7
        self.update_buttons()

    def update_buttons(self) -> None:
        # Hide or show buttons based on the current page
        # and the number of queue items
        self.children[0].disabled = self.page <= 1
        self.children[1].disabled = len(
            self.queue) < self.page * self.max_per_page

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
        await interaction.response.edit_message(
            embed=await self.create_embed(),
            view=self
        )

    async def create_embed(self) -> discord.Embed:
        if not self.queue:
            embed = discord.Embed(
                title='Queue Overview',
                color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
                description='No songs in queue!'
            )
            return embed

        # Get cover and colors of the NOW PLAYING song
        source: str = self.queue[0]['source']
        track_info: dict = self.queue[0]['track_info']
        if source == 'Spotify':
            # Cover data is not stored in the track info,
            # but only got when requested like here.
            # It allows the bot to bulk add songs (e.g from a playlist),
            # with way few API requests
            # TODO: cache the cover data
            cover_data = await spotify.get_cover_data(track_info['id'])
        elif source == 'Custom':
            cover_data = await get_cover_data_from_hash(track_info['id'])

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

    async def display(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        embed = await self.create_embed()
        await ctx.respond(embed=embed, view=self)

    async def update_view(
        self,
        interaction: discord.Interaction
    ) -> None:
        """Update the view when a button is pressed."""
        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_embed(),
            view=self
        )


async def connect(
    ctx: discord.ApplicationContext,
    bot: discord.Bot
) -> ServerSession | None:
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
    tracks_info = await spotify.get_tracks(user_input=query)

    if not tracks_info:
        await ctx.edit(content='Track not found!')
        return

    await session.add_to_queue(ctx, tracks_info, source='Spotify')


async def play_custom(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    # Request and cache
    try:
        audio_path = await fetch_audio_stream(query)
    except Exception as e:
        await ctx.edit(content=f'Error fetching audio: {str(e)}')
        return

    # Extract the metadata
    metadata = get_metadata(audio_path)
    # Idk why title and album are lists :elaina_huh:
    titles = metadata.get('title')
    albums = metadata.get('album')
    artists = metadata.get('artist', ['?'])

    display_name = (
        f'{artists[0]} - {titles[0]}' if titles
        else get_display_name_from_query(query)
    )

    # Extract the cover art
    cover_bytes: bytes | None = extract_cover_art(audio_path)
    if cover_bytes:
        cover_dict = await upload_cover(cover_bytes)
        cover_url = cover_dict.get('url')
        id = cover_dict.get('cover_hash')
        dominant_rgb = cover_dict.get('dominant_rgb')
    else:
        cover_url, id = None, None
        dominant_rgb = DEFAULT_EMBED_COLOR

    # Prepare the track
    def embed():
        return generate_info_embed(
            url=query,
            title=titles[0] if titles else display_name,
            album=albums[0] if albums else '?',
            artists=artists,
            cover_url=cover_url,
            dominant_rgb=dominant_rgb
        )

    track_info = {
        'display_name': display_name,
        'source': audio_path,
        'url': query,
        'embed': embed,
        'id': id
    }

    await session.add_to_queue(ctx, [track_info], source='Custom')


def get_display_name_from_query(query: str) -> str:
    """Extracts a display name from the query URL if no title is found."""
    match = re.search(r'(?:.+/)([^#?]+)', query)
    return unquote(match.group(1)) if match else 'Custom track'


async def play_onsei(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    work_id = extract_number(query)

    # API requests
    try:
        tracks_api: dict = await onsei.get_tracks_api(work_id)
        work_api: dict = await onsei.get_work_api(work_id)
        cover_url = onsei.get_cover(work_id)
        dominant_rgb = await get_accent_color_from_url(cover_url)
    except HTTPError:
        await ctx.edit(content='No onsei has been found!')
        return

    # Grab the data needed
    tracks = onsei.get_tracks(tracks_api, tracks={})
    work_title = work_api.get('title')
    artists = [i['name'] for i in work_api['vas']]

    # Prepare the tracks
    tracks_info = []
    for track_title, stream_url in tracks.items():
        def embed(track_title=track_title, stream_url=stream_url):
            return generate_info_embed(
                url=stream_url,
                title=track_title,
                album=work_title,
                artists=artists,
                cover_url=cover_url,
                dominant_rgb=dominant_rgb
            )

        track_info = {
            'display_name': track_title,
            'source': stream_url,
            'url': stream_url,
            'embed': embed,
            'id': None
        }

        tracks_info.append(track_info)
    await session.add_to_queue(ctx, tracks_info, source='Custom')
