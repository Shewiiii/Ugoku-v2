import asyncio
from collections import deque
from datetime import datetime, timedelta
import gc
import itertools
import logging
import random
from time import perf_counter, time
from typing import Optional, List, Union

import discord
from librespot.audio import AbsChunkedInputStream

from bot.utils import get_cache_path, respond
from bot.vocal.queue_view import QueueView
from bot.vocal.now_playing_view import nowPlayingView
from bot.vocal.wrong_track_view import WrongTrackView
from bot.vocal.track_dataclass import Track
from config import (
    AUTO_LEAVE_DURATION,
    DEFAULT_AUDIO_VOLUME,
    DEFAULT_ONSEI_VOLUME,
    DEEZER_ENABLED,
    SPOTIFY_API_ENABLED,
    DEFAULT_AUDIO_BITRATE,
    MAX_DUMMY_LOAD_INDEX,
)
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from deezer_decryption.download import Download
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.vocal.session_manager import SessionManager


class AudioEffect:
    def __init__(self):
        self.left_ir_file = ""
        self.right_ir_file = ""
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
        voice_client: Optional[discord.VoiceClient],
        bot: discord.Bot,
        channel_id: int,
        session_manager: "SessionManager",
        connect_task: Optional[asyncio.Task] = None,
    ) -> None:
        self.connect_task: Optional[asyncio.Task] = connect_task
        self.bot: discord.Bot = bot
        self.guild_id: int = guild_id
        self.voice_client: Optional[discord.VoiceClient] = voice_client
        self.queue: List[Track] = []
        self.to_loop: List[Optional[dict]] = []
        self.last_played_time: datetime = datetime.now()
        self.loop_current: bool = False
        self.loop_queue: bool = False
        self.skipped: bool = False
        self.shuffle: bool = False
        self.original_queue: List[Track] = []
        self.deezer_blacklist: set[Union[str, int]] = set()
        self.previous: bool = False
        self.stack_previous: deque = deque([])
        self.is_seeking: bool = False
        self.channel_id: int = channel_id
        self.now_playing_view: Optional[nowPlayingView] = None
        self.now_playing_message: Optional[discord.Message] = None
        self.old_message: Optional[discord.Message] = None
        self.session_manager: SessionManager = session_manager
        self.auto_leave_task: asyncio.Task = asyncio.create_task(
            self.check_auto_leave()
        )
        self.playback_start_time = None
        self.last_context = None
        self.volume = DEFAULT_AUDIO_VOLUME
        self.onsei_volume = DEFAULT_ONSEI_VOLUME
        self.audio_effect = AudioEffect()
        self.bitrate = DEFAULT_AUDIO_BITRATE
        self.deezer_download = Download(bot.deezer) if DEEZER_ENABLED else None
        self.stop_event: Optional[asyncio.Event] = None
        self.wrong_track_views: list[WrongTrackView] = []
        self.ffmpeg_source: Optional[discord.FFmpegOpusAudio] = None

    async def wait_for_connect_task(self) -> None:
        if self.connect_task:
            self.voice_client = await self.connect_task

    async def display_queue(
        self, ctx: discord.ApplicationContext, defer_task: asyncio.Task
    ) -> None:
        """Displays the current queue."""
        view = QueueView(
            self.queue,
            self.to_loop,
            self.bot,
            self.voice_client.is_playing(),
        )
        await view.display(ctx, defer_task)

    async def update_now_playing(
        self,
        ctx: discord.ApplicationContext,
        send: bool = True,
        edit_only: bool = False,
    ) -> None:
        """Sends an embed with information about the currently playing track."""
        track: Track = self.queue[0]

        # Embed
        if track.unloaded_embed:
            message = ""
            params = []
            if SPOTIFY_API_ENABLED:
                params.append(self.bot.spotify.sessions.sp)
            embed = await track.generate_embed(*params)

        if track.embed:
            # No need for a text message if embed
            message = ""
            embed = track.embed

            # Update the embed with remaining tracks
            next_name = "Next"
            next_value = "End of queue!"
            if len(self.queue) > 1:
                next_value = f"{self.queue[1]:markdown}"
            elif self.loop_queue and self.to_loop:
                next_value = f"{self.to_loop[0]:markdown}"
                next_name = "Next (Loop)"

            embed.fields[1].value = str(len(self.queue) - 1)  # Remaining
            embed.fields[2].name = next_name  # Next
            embed.fields[2].value = next_value  # Next

        else:
            message = f"Now playing: {track:markdown}"
            embed = None

        # View (buttons)
        if not self.now_playing_view:
            self.now_playing_view = nowPlayingView(
                self.bot, ctx, self.voice_client, self
            )
        else:
            await self.now_playing_view.update_buttons(edit=False)
        view = self.now_playing_view

        # Send the message or edit the previous message based on the context
        try:
            if not self.now_playing_message and send:
                if self.old_message:
                    # /skip or /previous executed
                    asyncio.create_task(self.old_message.delete())
                    self.old_message = None
                self.now_playing_message = await ctx.send(
                    content=message, embed=embed, view=view
                )
            elif send:
                # If skipping, just edit the embed, resend a new one otherwise (if the track ended naturally)
                if not (self.skipped or self.previous or edit_only):
                    old_message = self.now_playing_message
                    asyncio.create_task(old_message.delete())
                    self.now_playing_message = await ctx.send(
                        content=message, embed=embed, view=view
                    )
                else:
                    self.now_playing_message = await self.now_playing_message.edit(
                        content=message, embed=embed, view=view
                    )
        except discord.errors.Forbidden:
            logging.error(
                f"Now playing embed sent in forbidden channel in {self.guild_id}"
            )

    async def seek(self, position: int, quiet: bool = False) -> None:
        """Seeks to a specific position in the current track.
        Returns True if successful."""
        # No audio is playing
        if not (self.voice_client and self.queue):
            return

        if not quiet and self.last_context:
            asyncio.create_task(
                self.last_context.send(f"Seeking to {position} seconds")
            )

        self.is_seeking = True
        await self.stop_playback()

        track = self.queue[0]
        stream_source = self.queue[0].stream_source
        if isinstance(stream_source, DeezerChunkedInputStream):
            nearest_anchor = await asyncio.to_thread(stream_source.seek, position)
            track.timer._elapsed_time_accumulator = nearest_anchor
            position = 0
        else:
            # Timer
            track.timer._elapsed_time_accumulator = position
        track.timer._start_time = time()

        await self.start_playing(self.last_context, start_position=position)

    async def start_playing(
        self,
        ctx: discord.ApplicationContext,
        start_position: int = 0,
    ) -> None:
        """Handles the playback of the next track in the queue."""
        start = perf_counter()
        self.last_context = ctx

        if not self.queue:
            asyncio.create_task(self.now_playing_view.update_buttons())
            logging.info(f"Playback stopped in {self.guild_id}")
            return

        # Cache
        track: Track = self.queue[0]
        file_path = get_cache_path(f"{track.service}{track.id}")
        if file_path.is_file():
            track.stream_source = file_path

        # Load stream
        await track.load_stream(self)
        if track.stream_source is None:
            asyncio.create_task(ctx.send(f"{str(track)} is not available !"))
            # Wait for the voice_client to be set before continuing
            await self.wait_for_connect_task()
            self.after_playing(ctx, error=None)
            return

        logging.info(f"Stream source: {track.stream_source}")

        # Wait until the bot is fully connected to the vc
        await self.wait_for_connect_task()

        # Last checks
        if not self.voice_client:
            logging.error(f"No voice client in {self.guild_id} session")
            return
        if self.voice_client.is_playing():
            logging.error(f"Audio is already playing in {self.channel_id}")
            return

        # Play !
        ffmpeg_source = discord.FFmpegOpusAudio(
            track.stream_source,
            pipe=isinstance(
                track.stream_source, (AbsChunkedInputStream, DeezerChunkedInputStream)
            ),
            bitrate=self.bitrate,
            **self.get_ffmpeg_options(track.service, start_position),
        )
        self.voice_client.play(
            ffmpeg_source,
            after=lambda e=None: self.after_playing(ctx, e),
        )
        self.ffmpeg_source = ffmpeg_source

        # Log
        logging.info(
            f"Loading time before playing {track}: {(perf_counter() - start):.3f}s"
        )

        # Process the next track
        self.dummy_load = asyncio.create_task(self.load_next_tracks())

        # Send now playing
        if self.queue:
            should_update_now_playing = (
                not self.is_seeking
                and (self.skipped or not self.loop_current)
                and not (
                    len(self.queue) == 1 and len(self.to_loop) == 0 and self.loop_queue
                )
            )
            if should_update_now_playing:
                # Await to be sync with flags
                await self.update_now_playing(ctx)

        else:
            logging.error(f"Queue should not be empty after playing in {self.guild_id}")

        # Playback State Management
        now = datetime.now()
        track.timer.start()
        self.last_played_time = now
        self.playback_start_time = now.isoformat()

        # Reset control flags
        self.skipped = False
        self.is_seeking = False
        self.previous = False
        self.edit_now_playing_embed = True

    def get_ffmpeg_options(self, service: str, start_position: int) -> dict[str, str]:
        # Volume
        volume = (self.volume if service != "onsei" else self.onsei_volume) / 100

        # Stream options
        stream_options = "-fflags +discardcorrupt "
        if service == "ytdlp":
            stream_options += (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
            )

        # Audio effects
        ae = self.audio_effect
        if ae.effect:
            # Audio convolution
            before_options = (
                f'-i "./audio_ir/{ae.left_ir_file}" -i "./audio_ir/{ae.right_ir_file}" '
                + stream_options
            )
            volume_adjust = volume * ae.volume_multiplier
            mix_condition = (
                ""
                if ae.effect_only
                else "[2:a][fx_stereo]amix=inputs=2:weights=1 1[mix]; "
            )
            output_source = "[mix]" if not ae.effect_only else "[fx_stereo]"
            filter_complex = (
                f'"[2:a]channelsplit=channel_layout=stereo[L_in][R_in]; '
                f"[L_in][0:a]afir=dry={ae.dry}:wet={ae.wet}[L_fx]; "
                f"[R_in][1:a]afir=dry={ae.dry}:wet={ae.wet}[R_fx]; "
                f"[L_fx][R_fx]join=inputs=2:channel_layout=stereo[fx_stereo]; "
                f"{mix_condition}"
                f'{output_source}volume={volume_adjust}[out]"'
            )
            ffmpeg_options = {
                "before_options": before_options,
                "options": f'-filter_complex {filter_complex} -map "[out]" -ss {start_position}',
            }
        else:
            # Basic volume adjustment
            ffmpeg_options = {
                "before_options": stream_options,
                "options": f'-ss {start_position} -filter:a "volume={volume}"',
            }
        return ffmpeg_options

    async def load_next_tracks(self, max_index: int = MAX_DUMMY_LOAD_INDEX) -> None:
        """Load next the next Tracks and embeds.
        Preload the next stream if from Spotify/Deezer, check until the max index if from Ytdlp."""
        sp = self.bot.spotify.sessions.sp if SPOTIFY_API_ENABLED else None
        tasks = []

        # In the loop queue
        if self.loop_queue and len(self.queue) == 1 and self.to_loop:
            track: Track = self.to_loop[0]

        # In queue
        for i, track in enumerate(self.queue[1:max_index], start=1):
            if i == 1 or track.service == "ytdlp":
                tasks.append(track.load_stream(self))
            if track.unloaded_embed:  # Spotify/Deezer
                tasks.append(track.generate_embed(sp))

        if not tasks:
            return

        await asyncio.gather(*tasks)

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks: List[Track],
        play_next: bool = False,
        show_wrong_track_embed: bool = False,
        user_query: Optional[str] = None,
        load_dummies: bool = True,
    ) -> None:
        """Adds tracks to the queue and starts playback if not already playing."""

        # Add elements to the queue
        original_length = len(self.queue)
        self.queue[(i := 1 if play_next else len(self.queue)) : i] = tracks

        # Shuffle if enabled
        if self.shuffle:
            self.original_queue[
                (i := 1 if play_next else len(self.original_queue)) : i
            ] = tracks
            random.shuffle(self.queue[1:])

        # Tell the user what has been added
        c = len(tracks)
        titles = ", ".join(f"{t:markdown}" for t in tracks[:3])
        content = f"Added to queue: {titles}{' !' if c <= 3 else f', and {c - 3} more songs !'}"

        if c == 1 and show_wrong_track_embed:
            view = WrongTrackView(
                ctx, str(tracks[0]), self, content, user_query=user_query
            )
            self.wrong_track_views.append(view)
        else:
            view = None

        asyncio.create_task(
            respond(
                ctx,
                content=content,
                view=view,
            )
        )

        # Play !
        should_start_playing = len(self.queue) >= 1 and (
            not self.voice_client
            or (
                not self.voice_client.is_playing() and not self.voice_client.is_paused()
            )
        )

        if should_start_playing:
            await self.start_playing(ctx)
        else:
            asyncio.create_task(self.update_now_playing(ctx, edit_only=True))

        # Preload next tracks if the queue has only one track
        # Or is played next
        # (prepare_next_track method has not been called before)
        if load_dummies and (original_length == 1 or play_next):
            await self.load_next_tracks()

    async def play_previous(self, ctx: discord.ApplicationContext) -> None:
        self.previous = True
        await self.stop_playback()
        if self.queue:
            await self.post_process()
        self.queue.insert(0, self.stack_previous.pop())
        await self.start_playing(ctx)

    async def stop_playback(self) -> None:
        """Stop the playback and cancel the after_playing callback."""
        if not self.voice_client.is_playing():
            return
        self.stop_event = asyncio.Event()
        self.voice_client.stop()
        await self.stop_event.wait()  # ... Until its completely stopped
        self.last_played_time = datetime.now()
        self.stop_event = None

    async def post_process(
        self, track: Optional[Track] = None, close_stream: bool = True
    ) -> None:
        """Postprocess a track in the queue. Defaults to the first one"""
        tasks = []
        if not track:
            track = self.queue[0]
        track.timer.reset()
        self.last_played_time = datetime.now()

        if close_stream:
            tasks.append(track.close_stream())

        # Limit the previous stack length
        if len(self.stack_previous) >= 5:
            old_track: Track = self.stack_previous.popleft()
            # The removed track should not be in the queue
            # I check nonetheless to avoid weird issues
            if track not in self.to_loop + self.queue:
                tasks.append(old_track.close())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def shuffle_queue(self) -> bool:
        """Toggles shuffling of the queue. Returns True if successful."""
        if len(self.queue) <= 1:
            self.shuffle = not self.shuffle
            # No need to shuffle if the queue has 0 or 1 song
            return True

        current_song = self.queue[0]

        if self.shuffle:
            # Restore the original order
            current_index = self.original_queue.index(current_song)
            self.queue = [current_song] + self.original_queue[current_index + 1 :]

            # Reset the previous stack
            await self.close_streams(
                tracks=list(self.stack_previous), clear_queues=False
            )
            self.stack_previous.clear()
            self.original_queue.clear()
        else:
            # Grab all the incoming tracks
            self.original_queue = self.queue
            shuffled_queue = self.queue[1:]
            random.shuffle(shuffled_queue)
            self.queue = [current_song] + shuffled_queue

        self.shuffle = not self.shuffle
        asyncio.create_task(self.update_now_playing(self.last_context, edit_only=True))
        return True

    def after_playing(
        self,
        ctx: discord.ApplicationContext,
        error: Optional[Exception] = None,
    ) -> None:
        """Callback function executed after a track finishes playing."""
        self.last_played_time = datetime.now()

        if self.ffmpeg_source:
            self.ffmpeg_source.cleanup()
            self.ffmpeg_source = None

        if error:
            logging.error(repr(error))

        # POST PROCESSING
        played_track: Track = self.queue[0]
        played_track.timer.reset()
        close_stream = not (self.loop_current or self.previous or self.is_seeking)
        # Will take more time to regenerate the stream,
        # But the user is more likely to not play this track again
        asyncio.run_coroutine_threadsafe(
            self.post_process(played_track, close_stream=close_stream), self.bot.loop
        )

        # Stop the play_next call
        if self.is_seeking or self.stop_event:
            self.stop_event.set()
            return

        asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

    async def play_next(self, ctx: discord.ApplicationContext) -> None:
        """Plays the next track in the queue, handling looping and previous track logic.
        Do not call this method explicitely."""
        played_track: Track = self.queue[0]

        if not (self.loop_current or self.previous):
            self.stack_previous.append(played_track)

        if self.loop_queue and not self.loop_current:
            self.to_loop.append(played_track)

        if not self.loop_current:
            self.queue.pop(0)

        # After pop
        if not self.queue:
            if self.loop_queue:
                self.queue, self.to_loop = self.to_loop, []
            else:
                # Can reset the skipped status if there are no more tracks
                self.skipped = False

        await self.start_playing(ctx)

    async def check_auto_leave(self) -> None:
        """Checks for inactivity and automatically disconnects from the voice channel if inactive for too long."""
        await asyncio.sleep(1)
        await self.wait_for_connect_task()

        while self.voice_client.is_connected():
            if not self.voice_client.is_playing():
                time_since_last_played = datetime.now() - self.last_played_time
                time_until_disconnect = (
                    timedelta(seconds=AUTO_LEAVE_DURATION) - time_since_last_played
                )

                logging.debug(
                    "Time until disconnect due to "
                    f"inactivity in {self.guild_id}: "
                    f"{time_until_disconnect}"
                )

                if time_until_disconnect <= timedelta(seconds=0):
                    await self.voice_client.disconnect()
                    channel = self.bot.get_channel(self.channel_id)
                    if channel:
                        await channel.send("Baibai~")
                    await self.clean_session()
                    await asyncio.to_thread(gc.collect)
                    break

            await asyncio.sleep(17)

    async def close_streams(
        self,
        gc_collect: bool = True,
        clear_queues: bool = True,
        tracks: Optional[list[Track]] = None,
    ) -> None:
        close_tasks = []
        # Close & delete tracks
        if tracks is None:
            tracks = itertools.chain(self.queue, self.stack_previous, self.to_loop)

        for track in tracks:
            if not clear_queues and track in self.queue:
                continue
            close_tasks.append(track.close())

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        if clear_queues:
            self.queue.clear()
            self.original_queue.clear()
            self.to_loop.clear()
            self.stack_previous.clear()

        if gc_collect:
            await asyncio.to_thread(gc.collect)

    async def clean_session(self) -> None:
        await self.stop_playback()

        if self.now_playing_message:
            await self.now_playing_message.delete()

        if self.now_playing_view:
            self.now_playing_view.close()
            self.now_playing_view = None

        for view in self.wrong_track_views:
            view.close()

        if self.voice_client:
            if self.voice_client.is_playing():
                await self.stop_playback()
            await self.voice_client.disconnect()
            self.voice_client.cleanup()

        if self.auto_leave_task and not self.auto_leave_task.done():
            self.auto_leave_task.cancel()
        if self.connect_task and not self.connect_task.done():
            self.connect_task.cancel()

        self.session_manager.server_sessions.pop(self.guild_id)

        await self.close_streams(gc_collect=False)
        self.bot = None
        self.voice_client = None
        self.deezer_download = None
