import asyncio
from copy import deepcopy
from pathlib import Path
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Literal

import discord
from librespot.audio import AbsChunkedInputStream

from bot.vocal.queue_view import QueueView
from bot.vocal.control_view import controlView
from config import (
    AUTO_LEAVE_DURATION,
    DEFAULT_AUDIO_VOLUME,
    DEFAULT_ONSEI_VOLUME,
    DEEZER_ENABLED,
    SPOTIFY_ENABLED,
    DEFAULT_AUDIO_BITRATE,
)
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from deezer_decryption.api import Deezer
from deezer_decryption.download import Download
from bot.utils import cleanup_cache, get_cache_path

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.vocal.session_manager import SessionManager


class AudioEffect:
    def __init__(self):
        self.left_ir_file = ''
        self.right_ir_file = ''
        self.effect: Optional[str] = None
        self.effect_only = False
        self.dry = 0
        self.wet = 0
        self.volume_multiplier = 1


class ServerSession:
    """Represents an audio session for a Discord server.
    This class manages the audio playback for a specific server."""

    def __init__(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient,
        bot: discord.Bot,
        channel_id: int,
        session_manager: 'SessionManager'
    ) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.voice_client = voice_client
        self.queue: List[Optional[dict]] = []
        self.to_loop: List[Optional[dict]] = []
        self.last_played_time = datetime.now()
        self.time_elapsed = 0
        self.loop_current = False
        self.loop_queue = False
        self.skipped = False
        self.shuffle = False
        self.original_queue: List[Optional[dict]] = []
        self.shuffled_queue: List[Optional[dict]] = []
        self.cached_songs: set[str] = set()
        self.previous = False
        self.stack_previous = []
        self.is_seeking = False
        self.channel_id = channel_id
        self.session_manager = session_manager
        self.auto_leave_task = asyncio.create_task(
            self.check_auto_leave()
        )
        self.playback_start_time = None
        self.last_context = None
        self.volume = DEFAULT_AUDIO_VOLUME
        self.onsei_volume = DEFAULT_ONSEI_VOLUME
        self.audio_effect = AudioEffect()
        self.bitrate = DEFAULT_AUDIO_BITRATE
        self.deezer_download = Download(bot.deezer)

    async def display_queue(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        """Displays the current queue."""
        view = QueueView(
            self.queue,
            self.to_loop,
            self.bot,
            self.last_played_time,
            self.time_elapsed,
            self.voice_client.is_playing()
        )
        await view.display(ctx)

    async def send_now_playing(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        """Sends an embed with information about the currently playing track."""
        # Retrieve the current track_info from the queue
        track_info: dict = self.queue[0]['track_info']
        unloaded_embed: Optional[discord.Embed] = track_info['embed']
        title: str = track_info['display_name']
        url: str = track_info['url']
        title_markdown = f'[{title}](<{url}>)'

        if unloaded_embed:
            # In case it requires additional api calls,
            # The embed is generated when needed only
            if isinstance(unloaded_embed, Callable):
                track_info['embed'] = await track_info['embed']()
                sent_embed = deepcopy(track_info['embed'])
            else:
                sent_embed = deepcopy(unloaded_embed)

            next_track = 'End of queue!'
            if len(self.queue) > 1:
                next_track_info = self.queue[1]['track_info']
                next_track = f'[{next_track_info["display_name"]}](<{next_track_info["url"]}>)'
            # Update the embed with remaining tracks
            sent_embed.add_field(
                name="Remaining",
                value=str(len(self.queue) - 1),
                inline=True
            )
            sent_embed.add_field(
                name="Next",
                value=next_track, inline=True
            )

            # No need for a text message if embed
            message = ''

            # VIEW (buttons)
            view = controlView(self.bot, ctx, self.voice_client)

        else:
            message = f'Now playing: {title_markdown}'
            view = None

        # Send the message or edit the previous message based on the context
        await ctx.send(
            content=message,
            embed=sent_embed,
            view=view,
            silent=True
        )

    async def seek(
        self,
        position: int,
        quiet: bool = False
    ) -> bool:
        """Seeks to a specific position in the current track.
        Returns True if successful."""
        # No audio is playing
        if not self.voice_client or not self.voice_client.is_playing():
            return False

        self.is_seeking = True
        self.time_elapsed = position
        self.voice_client.stop()

        # Wait a short time to ensure the stop has been processed
        await asyncio.sleep(0.1)

        if not quiet and self.last_context:
            await self.last_context.send(f"Seeking to {position} seconds")

        await self.start_playing(self.last_context, start_position=position)
        return True

    async def load_deezer_stream(self, index: int = 0) -> Optional[DeezerChunkedInputStream]:
        if (index >= len(self.queue)
            or not DEEZER_ENABLED or self.queue[index]['service'] != 'spotify/deezer'
                or isinstance(self.queue[0]['track_info']['source'], (str, Path))):
            return

        deezer: Deezer = self.bot.deezer
        track_info = self.queue[index]['track_info']
        source = track_info['source']

        # Already a Deezer stream: reset the position
        if isinstance(source, DeezerChunkedInputStream):
            source.current_position = 0
            return source

        # Try to get native track API (to grab the song from irsc)
        native_track_api = await deezer.parse_spotify_track(track_info['url'], self.bot.spotify.sessions.sp)
        if not native_track_api:
            return

        # Setup streaming
        track_id = native_track_api['id']
        gw_track_api = await deezer.get_track(track_id)
        if not gw_track_api:
            return

        # Load the stream
        track_token = gw_track_api['TRACK_TOKEN']
        stream_url = (await deezer.get_track_urls([track_token]))[0]
        if not stream_url:
            # Track not found at desired bitrate and no alternative found
            return

        input_stream = DeezerChunkedInputStream(track_id, stream_url)
        await input_stream.set_chunks()
        track_info.update({
            'source': input_stream,
            'id': track_id
        })

        return input_stream

    async def load_spotify_stream(self, index: int = 0) -> Optional[AbsChunkedInputStream]:
        if index >= len(self.queue) or not SPOTIFY_ENABLED:
            return
        source = self.queue[index]['track_info']['source']

        # Handle Spotify stream generators
        if isinstance(source, Callable):
            try:
                input_stream = await source()
            except Exception as e:
                logging.error(e)
                return

        # Skip non-audio content in Spotify streams
        if isinstance(input_stream, AbsChunkedInputStream):
            await asyncio.to_thread(input_stream.seek, 167)
            return input_stream

    async def start_playing(
        self,
        ctx: discord.ApplicationContext,
        start_position: int = 0
    ) -> None:
        """Handles the playback of the next track in the queue."""
        start = datetime.now()
        self.last_context = ctx

        if not self.queue:
            logging.info(f'Playback stopped in {self.guild_id}')
            return

        # Cache
        await cleanup_cache()
        current_element = self.queue[0]
        service = current_element['service']
        track_id: str = current_element['track_info']['id']
        file_path = get_cache_path(f"{service}{track_id}".encode('utf-8'))
        if file_path.is_file():
            current_element['track_info']['source'] = file_path

        # Send now playing
        should_send_now_playing = (
            not self.is_seeking
            and (self.skipped or not self.loop_current)
            and not (len(self.queue) == 1 and len(self.to_loop) == 0 and self.loop_queue)
        )
        if should_send_now_playing:
            try:
                await self.send_now_playing(ctx)
            except discord.errors.Forbidden:
                logging.error(
                    f"Now playing embed sent in forbidden channel in {self.guild_id}")
            self.skipped = False

        # Audio source setup
        track_info = current_element['track_info']
        unloaded_source = track_info['source']
        if service == 'spotify/deezer' and not isinstance(unloaded_source, (Path, str)):
            source = await self.load_deezer_stream() or await self.load_spotify_stream()
            if source is None:
                await ctx.send(f"{track_info['display_name']} is not available!")
                self.after_playing(ctx, error=None)
                return
        else:
            source = unloaded_source
        logging.info(f"Stream source: {source}")

        # FFmpeg config
        volume = (self.volume if service !=
                  'onsei' else self.onsei_volume) / 100
        ae = self.audio_effect
        ffmpeg_options = {}

        if ae.effect:
            # Audio convolution
            before_options = (
                f'-i "./audio_ir/{ae.left_ir_file}" '
                f'-i "./audio_ir/{ae.right_ir_file}"'
            )
            volume_adjust = volume * ae.volume_multiplier
            mix_condition = "" if ae.effect_only else "[2:a][fx_stereo]amix=inputs=2:weights=1 1[mix]; "
            output_source = "[mix]" if not ae.effect_only else "[fx_stereo]"
            filter_complex = (
                f'"[2:a]channelsplit=channel_layout=stereo[L_in][R_in]; '
                f'[L_in][0:a]afir=dry={ae.dry}:wet={ae.wet}[L_fx]; '
                f'[R_in][1:a]afir=dry={ae.dry}:wet={ae.wet}[R_fx]; '
                f'[L_fx][R_fx]join=inputs=2:channel_layout=stereo[fx_stereo]; '
                f'{mix_condition}'
                f'{output_source}volume={volume_adjust}[out]"'
            )
            ffmpeg_options = {
                "before_options": f'{before_options} -fflags +discardcorrupt',
                "options": f'-filter_complex {filter_complex} -map "[out]" -ss {start_position}'
            }
        else:
            # Basic volume adjustment
            ffmpeg_options = {
                'before_options': '-fflags +discardcorrupt',
                'options': f'-ss {start_position} -filter:a "volume={volume}"'
            }

        # Play !
        ffmpeg_source = discord.FFmpegOpusAudio(
            source,
            pipe=isinstance(source, (AbsChunkedInputStream,
                            DeezerChunkedInputStream)),
            bitrate=self.bitrate,
            **ffmpeg_options
        )
        self.voice_client.play(
            ffmpeg_source,
            after=lambda e=None: self.after_playing(ctx, e)
        )

        # Playback State Management
        now = datetime.now()
        self.time_elapsed = start_position
        self.last_played_time = now
        self.playback_start_time = now.isoformat()

        # Reset control flags
        self.is_seeking = False
        self.previous = False

        # Process the next track
        await self.prepare_next_track()

        # Log total processing time
        logging.info(
            f"Start playing processing time: {(datetime.now() - start).total_seconds()}s")

    async def prepare_next_track(self, index: int = 1) -> None:
        """Check the availability of the next track and load its embed in queue."""
        if len(self.queue) <= index:
            # No tracks to prepare
            return
        track_info = self.queue[index]['track_info']
        current_id = track_info['id']

        # Generate the embed
        embed = track_info.get('embed', None)
        if embed and isinstance(embed, Callable):
            if track_info['id'] == current_id:
                track_info['embed'] = await embed()
            logging.info(f"Loaded embed of {track_info['display_name']}")

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks_info: List[dict],
        service: Literal['spotify', 'youtube', 'custom', 'onsei'],
        interaction: Optional[discord.Interaction] = None
    ) -> None:
        """Adds tracks to the queue and starts playback if not already playing."""
        def edit_method(edit_function):
            async def edit(content: str, edit_function=edit_function) -> None:
                try:
                    await edit_function(content=content)
                except discord.errors.NotFound as e:
                    logging.error(e)
                    pass
            return edit

        # Check if triggered by an interaction
        if interaction:
            edit = edit_method(interaction.edit_original_response)
        else:
            edit = edit_method(ctx.edit)

        original_length = len(self.queue)

        for track_info in tracks_info:
            queue_item: dict = {
                'track_info': track_info,
                'service': service
            }
            self.queue.append(queue_item)
            # Add to original queue for shuffle
            self.original_queue.append(queue_item)

        if self.shuffle:
            current_song = [self.queue[0]] if self.queue else []
            remaining_songs = self.queue[1:]
            random.shuffle(remaining_songs)
            self.queue = current_song + remaining_songs

        # If only one song is added
        count = len(tracks_info)
        if count == 1:
            title = tracks_info[0]['display_name']
            url = tracks_info[0]['url']
            await edit(content=f'Added to queue: [{title}](<{url}>) !')

        # If 2 or 3 songs are added
        elif count in [2, 3]:
            titles_urls = ', '.join(
                f'[{track_info["display_name"]}](<{track_info["url"]}>)'
                for track_info in tracks_info
            )
            await edit(content=f'Added to queue: {titles_urls} !')

        # If more than 3 songs are added
        elif count > 3:
            titles_urls = ', '.join(
                f'[{track_info["display_name"]}](<{track_info["url"]}>)'
                for track_info in tracks_info[:3]
            )
            additional_songs = count - 3
            await edit(
                content=(
                    f'Added to queue: {titles_urls}, and '
                    f'{additional_songs} more song(s) !')
            )

        if not self.voice_client.is_playing() and len(self.queue) >= 1:
            await self.start_playing(ctx)

        # Preload next tracks if the queue has only one track
        # (prepare_next_track method has not been called before)
        if original_length == 1:
            await self.prepare_next_track()

    async def play_previous(self, ctx: discord.ApplicationContext) -> None:
        self.previous = True
        self.queue.insert(0, self.stack_previous.pop())
        if self.voice_client.is_playing():
            self.voice_client.pause()
        await self.start_playing(ctx)

    def get_queue(self) -> List[dict]:
        """Returns a simplified version of the current queue."""
        return [
            {
                "title": track['track_info']['title'],
                "artist": track['track_info'].get('artist'),
                "album": track['track_info'].get('album'),
                "cover": track['track_info'].get('cover'),
                "duration": track['track_info'].get('duration'),
                "url": track['track_info']['url']
            }
            for track in self.queue
        ]

    def shuffle_queue(self) -> bool:
        """Toggles shuffling of the queue. Returns True if successful."""
        if len(self.queue) <= 1:
            self.shuffle = not self.shuffle
            # No need to shuffle if the queue has 0 or 1 song
            return True

        current_song = self.queue[0]

        if self.shuffle:
            # Restore the original order
            current_index = self.original_queue.index(current_song)
            self.queue = [current_song] + \
                self.original_queue[current_index + 1:]

        else:
            self.shuffled_queue = self.queue[1:]
            random.shuffle(self.shuffled_queue)
            self.queue = [current_song] + self.shuffled_queue

        self.shuffle = not self.shuffle
        return True

    def after_playing(
        self,
        ctx: discord.ApplicationContext,
        error: Optional[Exception]
    ) -> None:
        """Callback function executed after a track finishes playing."""
        self.last_played_time = datetime.now()

        if error:
            raise error

        if self.is_seeking:
            return

        if self.queue and self.voice_client.is_connected():
            asyncio.run_coroutine_threadsafe(
                self.play_next(ctx),
                self.bot.loop
            )

    async def play_next(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        """Plays the next track in the queue, handling looping and previous track logic."""
        if self.queue and not self.loop_current and not self.previous:
            self.stack_previous.append(self.queue[0])

        if self.loop_queue and not self.loop_current:
            self.to_loop.append(self.queue[0])

        if not self.loop_current:
            self.queue.pop(0)

        if not self.queue and self.loop_queue:
            self.queue, self.to_loop = self.to_loop, []

        await self.start_playing(ctx)

    async def check_auto_leave(self) -> None:
        """Checks for inactivity and automatically disconnects from the voice channel if inactive for too long."""
        while self.voice_client.is_connected():
            if not self.voice_client.is_playing():
                await asyncio.sleep(1)
                time_since_last_played = datetime.now() - self.last_played_time
                time_until_disconnect = timedelta(
                    seconds=AUTO_LEAVE_DURATION) - time_since_last_played

                logging.debug(
                    'Time until disconnect due to '
                    f'inactivity in {self.guild_id}: '
                    f'{time_until_disconnect}'
                )

                if time_until_disconnect <= timedelta(seconds=0):
                    await self.voice_client.disconnect()
                    if channel:
                        await channel.send('Baibai~')
                    await self.voice_client.cleanup()
                    await self.close_streams()
                    del self.session_manager.server_sessions[self.guild_id]
                    channel = self.bot.get_channel(self.channel_id)
                    logging.info(
                        f'Deleted audio session in {self.guild_id} '
                        'due to inactivity.'
                    )
                    break

            await asyncio.sleep(17)

    async def close_streams(self) -> None:
        for stream in self.queue+self.stack_previous+self.to_loop:
            if isinstance(stream, DeezerChunkedInputStream):
                await self.current_stream.close(),
            elif isinstance(stream, AbsChunkedInputStream):
                await asyncio.to_thread(self.current_stream.close)
            self.stream = None
