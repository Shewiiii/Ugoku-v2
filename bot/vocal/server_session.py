import requests
import aiofiles
from pathlib import Path
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Literal
from copy import deepcopy

import discord
from librespot.audio import AbsChunkedInputStream
from deezer.errors import DataException

from bot.vocal.queue_view import QueueView
from bot.vocal.control_view import controlView
from config import (
    AUTO_LEAVE_DURATION,
    DEFAULT_AUDIO_VOLUME,
    DEFAULT_ONSEI_VOLUME,
    DEEZER_ENABLED,
    SPOTIFY_ENABLED,
    CACHE_STREAMS,
    DEFAULT_AUDIO_BITRATE,
    DELAY_BEFORE_CACHING
)
from bot.vocal.deezer import DeezerChunkedInputStream
from bot.utils import cleanup_cache, get_cache_path
from deemix.utils.crypto import decryptChunk
from deemix.utils import USER_AGENT_HEADER

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
        self.current_stream = None
        self.bitrate = DEFAULT_AUDIO_BITRATE

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
        embed: Optional[discord.Embed] = track_info['embed']
        title: str = track_info['display_name']
        url: str = track_info['url']
        title_markdown = f'[{title}](<{url}>)'

        if embed:
            # In case it requires additional api calls,
            # The embed is generated when needed only
            if isinstance(embed, Callable):
                sent_embed = await embed()
            else:
                sent_embed = deepcopy(embed)

            if len(self.queue) > 1:
                next_track_info = self.queue[1]['track_info']
                next_track = (
                    f'[{next_track_info["display_name"]}](<{next_track_info["url"]}>)')
            else:
                next_track = 'End of queue!'
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
            # Audio quality indicator
            aq_dict = {'youtube': 'Low', 'spotify': 'High', 'deezer': 'Hifi'}
            audio_quality = aq_dict.get(self.queue[0]['source'].lower(), None)
            if audio_quality:
                sent_embed.add_field(
                    name="Audio quality",
                    value=audio_quality,
                    inline=True
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

    async def inject_lossless_stream(self, index: int = 0) -> bool:
        if not await self.check_deezer_availability(index=index):
            return False
        # Create stream directly from the track dict in track_info
        track_info = self.queue[index]['track_info']
        deezer = self.bot.deezer
        track = track_info.get('track')
        try:
            track_info['source'] = await asyncio.to_thread(deezer.stream, track)
            return True
        except DataException:
            return False

    async def check_deezer_availability(self, index: int = 0) -> bool:
        """Returns true if a track in queue is available on Deezer. 
        Change a "track" field to the track_info dict depending on the availability."""
        track_info = self.queue[index]['track_info']
        # Already a deezer stream
        if isinstance(track_info['source'], DeezerChunkedInputStream):
            logging.info(
                f"Stream already loaded: {track_info['display_name']}")
            return True

        # Already cached
        if isinstance(track_info['source'], (str, Path)):
            return True

        # Outside the queue
        if index >= len(self.queue):
            return False
        
        # Not a deezer track
        if not DEEZER_ENABLED or not self.queue[index]['source'] == 'Deezer':
            return False

        deezer = self.bot.deezer
        try:
            track = await deezer.get_track(url=track_info['url'])
            if not track:
                return False
            track_info['track'] = track
            return True
        except Exception as e:
            logging.error(e)
            self.queue[index]['source'] = 'Spotify'
            return False

    async def start_playing(
        self,
        ctx: discord.ApplicationContext,
        start_position: int = 0
    ) -> None:
        """Handles the playback of the next track in the queue."""
        self.last_context = ctx
        if not self.queue:
            logging.info(f'Playback stopped in {self.guild_id}')
            return  # No songs to play

        # Check for a cache file
        await cleanup_cache()
        current_element = self.queue[0]
        service = current_element['source'].lower()
        id: str = current_element['track_info']['id']
        file_path = get_cache_path(f"{service}{id}".encode('utf-8'))

        # Cached stream already
        if file_path.is_file():
            current_element['track_info']['source'] = file_path

        # New track info dict
        track_info = current_element['track_info']
        cached = isinstance(track_info['source'], (Path, str))

        # If Deezer enabled, inject lossless stream in a spotify track
        if service == 'deezer' and not cached and not await self.inject_lossless_stream():
            current_element['source'] = "spotify"

        if current_element['source'] == "spotify" and not SPOTIFY_ENABLED:
            await ctx.send(
                content=f"{track_info['display_name']}"
                " is not available !",
                silent=True
            )
            self.after_playing(ctx, error=None)
            return

        # Now playing embed info
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
                    "Now playing embed sent in a "
                    f"fobidden channel in {self.guild_id}"
                )
            # Reset the skip flag
            self.skipped = False

        # Audio source to play
        source = track_info['source']

        # If source is a stream generator, generate a fresh stream
        if isinstance(source, Callable) and SPOTIFY_ENABLED:
            try:
                source = await source()
            except RuntimeError as e:
                if str(e) == "Cannot get alternative track":
                    await ctx.send(f"{track_info['display_name']} is not available !")
                else:
                    logging.error(e)
                self.after_playing(ctx, error=None)
                return

        # Skip the non-audio content in spotify streams
        if isinstance(source, AbsChunkedInputStream):
            await asyncio.to_thread(source.seek, 167)

        # Set up FFmpeg options for seeking and volume
        volume = (
            self.volume if service != 'onsei' else self.onsei_volume) / 100

        # Check if there is an audio effect
        ae = self.audio_effect
        if self.audio_effect.effect:
            before_options = (
                f'-i "./audio_ir/{ae.left_ir_file}" '
                f'-i "./audio_ir/{ae.right_ir_file}"'
            )
            volume_adjust = volume * ae.volume_multiplier
            filter_complex = (
                f'"'
                # Split L&R channels
                f'[2:a]channelsplit=channel_layout=stereo[L_in][R_in]; '
                # Convolve both channels, then rejoin them
                f'[L_in][0:a]afir=dry={ae.dry}:wet={ae.wet}[L_fx]; '
                f'[R_in][1:a]afir=dry={ae.dry}:wet={ae.wet}[R_fx]; '
                f'[L_fx][R_fx]join=inputs=2:channel_layout=stereo[fx_stereo]; '
                # Combine the effect with the original signal
                f'{"[2:a][fx_stereo]amix=inputs=2:weights=1 1[mix]; " if not ae.effect_only else ""}'
                f'{"[mix]" if not ae.effect_only else "[fx_stereo]"}'
                # Apply the other settings
                f'volume={volume_adjust}[out]" '
                f'-map "[out]" -ss {start_position}'
            )

            ffmpeg_options = {
                "before_options": before_options,
                "options": f'-filter_complex {filter_complex}'
            }
        else:
            # Default output options
            ffmpeg_options = {
                'options': (
                    f'-ss {start_position} '
                    f'-filter:a "volume={volume}" '
                )
            }
        ffmpeg_source = discord.FFmpegOpusAudio(
            source,
            pipe=isinstance(source, (AbsChunkedInputStream,
                            DeezerChunkedInputStream)),
            bitrate=self.bitrate,
            **ffmpeg_options
        )

        # Add the currently playing source in class variable
        self.current_stream = source

        # Play the song !
        self.voice_client.play(
            ffmpeg_source,
            after=lambda e=None: self.after_playing(ctx, e)
        )

        # Update dates
        now = datetime.now()
        self.time_elapsed = start_position
        self.last_played_time = now
        self.playback_start_time = now.isoformat()

        # Reset flags
        self.is_seeking = False
        self.previous = False

        # Tasks to improve reactivity
        await self.prepare_next_track()
        # After a few seconds, cache tracks if they have not changed
        if CACHE_STREAMS:
            await asyncio.sleep(DELAY_BEFORE_CACHING)
            await self.cache_stream(index=0)
            if len(self.queue) >= 1:
                await self.cache_stream(index=1)

    async def prepare_next_track(self, index: int = 1) -> None:
        """Check the availability of the next track and load its embed in queue."""
        if len(self.queue) <= index:
            # No tracks to prepare
            return
        track_info = self.queue[index]['track_info']
        current_id = track_info['id']

        # Deezer
        if not await self.check_deezer_availability(index=index):
            logging.info(
                f"Track not available on Deezer: {track_info['display_name']}")
            self.queue[index]['source'] = 'spotify'

        # Generate the embed
        embed = track_info.get('embed', None)
        if embed and isinstance(embed, Callable):
            if track_info['id'] == current_id:
                track_info['embed'] = await embed()
            logging.info(
                f"Preloaded the embed of {track_info['display_name']}")

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks_info: List[dict],
        source: Literal['Spotify', 'Youtube', 'Custom', 'Onsei'],
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
                'source': source
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
            await asyncio.sleep(DELAY_BEFORE_CACHING)
            await self.cache_stream(index=1)

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

        # Close the current stream if it exists
        if self.current_stream and isinstance(self.current_stream, (DeezerChunkedInputStream, AbsChunkedInputStream)):
            self.current_stream.close()
            self.current_stream = None

        if self.is_seeking:
            # If we're seeking, don't do anything
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
                    del self.session_manager.server_sessions[self.guild_id]
                    channel = self.bot.get_channel(self.channel_id)
                    if channel:
                        await channel.send('Baibai~')
                    logging.info(
                        f'Deleted audio session in {self.guild_id} '
                        'due to inactivity.'
                    )
                    break

            await asyncio.sleep(17)

    async def cache_stream(self, index: int) -> None:
        """Cache audio streams from Deezer or Spotify"""
        cached = False
        await cleanup_cache()
        if len(self.queue) <= index:
            # Nothing to cache
            return

        # All the variables
        next_element = self.queue[index]
        track_info = next_element['track_info']
        source = track_info['source']
        service = next_element['source'].lower()
        id = track_info['id']
        cache_id: str = f"{service}{id}"
        file_path = get_cache_path(cache_id.encode('utf-8'))

        # Not a Deezer or Spotify stream / already cached
        if isinstance(source, (Path, str)):
            return

        # Cached stream already, nothing to do
        is_file = file_path.is_file()
        if is_file:
            track_info['source'] = file_path
        if is_file or id in self.cached_songs:
            logging.info(
                f"Already cached/Attempted to cache: {track_info['display_name']}")
            return

        # Add the stream to the cached songs set before processing
        # (avoid multiple caching for a single track)
        self.cached_songs.add(id)

        # Is a Spotify stream
        if isinstance(source, Callable) and SPOTIFY_ENABLED:
            source = await source()

            if isinstance(source, AbsChunkedInputStream):
                if not SPOTIFY_ENABLED:
                    return
                # Get track data
                data = await asyncio.to_thread(source.read)
                # Download
                with open(file_path, 'wb') as file:
                    file.write(data)
                cached = True

        # Deezer stream (means deezer features are enabled)
        elif service == 'deezer':
            await self.inject_lossless_stream(index)
            # Updated source
            source = next_element['track_info']['source']

            if isinstance(source, DeezerChunkedInputStream):
                # Generate a separate stream URL
                track = await self.bot.deezer.get_track(id_=str(source.id))
                response = await asyncio.to_thread(
                    requests.get,
                    track['stream_url'],
                    headers={'User-Agent': USER_AGENT_HEADER},
                    timeout=10
                )
                if response.status_code != 200:
                    logging.error(
                        f"Failed to fetch stream for track {track_info['id']}")
                    return
                encrypted_stream = await asyncio.to_thread(
                    response.iter_content,
                    source.chunk_size
                )

                async with aiofiles.open(file_path, 'wb') as file:
                    while True:
                        chunk = await asyncio.to_thread(
                            next,
                            encrypted_stream,
                            None
                        )
                        if chunk is None:
                            # No more chunks to process
                            break
                        if len(chunk) >= 2048:
                            # Offload decryption to a thread
                            decrypted = await asyncio.to_thread(
                                decryptChunk,
                                source.blowfish_key,
                                chunk[:2048]
                            )
                            chunk = decrypted + chunk[2048:]

                        # Write the chunk asynchronously
                        await file.write(chunk)
                cached = True

        # Check if it is still the same track
        if track_info['id'] == id and cached:
            logging.info(f"Cached successfully: {track_info['display_name']} ")
            track_info['source'] = file_path
