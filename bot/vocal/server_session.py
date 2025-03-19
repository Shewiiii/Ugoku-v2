import asyncio
from copy import deepcopy
from collections import deque
from datetime import datetime, timedelta
import gc
import itertools
import logging
from pathlib import Path
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
        self.shuffled_queue: List[Track] = []
        self.deezer_blacklist: set[Union[str, int]] = set()
        self.previous_track_id: Optional[Union[int, str]] = None
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
            sent_embed = deepcopy(embed)

        if track.embed:
            # No need for a text message if embed
            message = ""
            sent_embed = deepcopy(track.embed)

            # Update the embed with remaining tracks
            next_track = "End of queue!"
            name = "Next"
            if len(self.queue) > 1:
                next_track = f"{self.queue[1]:markdown}"
            elif self.loop_queue and self.to_loop:
                next_track = f"{self.to_loop[0]:markdown}"
                name = "Next (Loop)"

            sent_embed.add_field(
                name="Remaining",
                value=str(len(self.queue) - 1),
            ).add_field(name=name, value=f"{next_track}")
        else:
            message = f"Now playing: {track:markdown}"
            sent_embed = None

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
                    content=message, embed=sent_embed, view=view
                )
            elif send:
                # If skipping, just edit the embed, resend a new one otherwise (if the track ended naturally)
                if not (self.skipped or self.previous or edit_only):
                    old_message = self.now_playing_message
                    asyncio.create_task(old_message.delete())
                    self.now_playing_message = await ctx.send(
                        content=message, embed=sent_embed, view=view
                    )
                else:
                    self.now_playing_message = await self.now_playing_message.edit(
                        content=message, embed=sent_embed, view=view
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

        self.is_seeking = True
        self.voice_client.pause()

        if not quiet and self.last_context:
            await self.last_context.send(f"Seeking to {position} seconds")

        track = self.queue[0]
        stream_source = self.queue[0].stream_source
        if isinstance(stream_source, DeezerChunkedInputStream):
            await asyncio.to_thread(stream_source.seek, position)
            # Position changed within the stream class
            position = 0
        else:
            # Timer
            track.timer._start_time = time()
            track.timer._elapsed_time_accumulator = position

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
        file_path = get_cache_path(f"{track.service}{track.id}".encode("utf-8"))
        if file_path.is_file():
            track.stream_source = file_path

        # Audio source setup
        if track.service == "spotify/deezer" and not isinstance(
            track.stream_source, (Path, str)
        ):
            await track.load_stream(self)
            if track.stream_source is None:
                asyncio.create_task(ctx.send(f"{str(track)} is not available!"))
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
            ffmpeg_source, after=lambda e=None: self.after_playing(ctx, e)
        )

        # Log
        logging.info(
            f"Loading time before playing {track}: {(perf_counter() - start):.3f}s"
        )

        # Process the next track
        asyncio.create_task(self.prepare_next_track())

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
        volume = (self.volume if service != "onsei" else self.onsei_volume) / 100
        ae = self.audio_effect
        if ae.effect:
            # Audio convolution
            before_options = (
                f'-i "./audio_ir/{ae.left_ir_file}" -i "./audio_ir/{ae.right_ir_file}"'
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
                "before_options": f"{before_options} -fflags +discardcorrupt",
                "options": f'-filter_complex {filter_complex} -map "[out]" -ss {start_position}',
            }
        else:
            # Basic volume adjustment
            ffmpeg_options = {
                "before_options": "-fflags +discardcorrupt",
                "options": f'-ss {start_position} -filter:a "volume={volume}"',
            }
        return ffmpeg_options

    async def prepare_next_track(self, index: int = 1) -> None:
        """Check the availability of the next track and load its embed in queue."""
        # Kind of an artificial implementation: ignore the index value
        # when preparing the track in loop
        if self.loop_queue and len(self.queue) == 1 and self.to_loop:
            track: Track = self.to_loop[0]
        elif len(self.queue) <= index:
            return
        else:
            track: Track = self.queue[index]

        # Stream task
        asyncio.create_task(track.load_stream(self))

        # Embed task
        if track.unloaded_embed:
            sp = self.bot.spotify.sessions.sp if SPOTIFY_API_ENABLED else None
            asyncio.create_task(track.generate_embed(sp))

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks: List[Track],
        play_next: bool = False,
    ) -> None:
        """Adds tracks to the queue and starts playback if not already playing."""

        # Add elements to the queue
        original_length = len(self.queue)
        for queue in self.queue, self.original_queue:
            queue[(i := 1 if play_next else len(queue)) : i] = tracks

        # Shuffle if enabled
        if self.shuffle:
            random.shuffle(self.queue[1:])

        # Tell the user what has been added
        c = len(tracks)
        titles = ", ".join(f"{t:markdown}" for t in tracks[:3])
        content = f"Added to queue: {titles}{' !' if c <= 3 else f', and {c - 3} more songs !'}"
        view = WrongTrackView(ctx, tracks[0], self, content) if c == 1 else None
        asyncio.create_task(
            respond(
                ctx,
                content=content,
                view=view,
            )
        )

        # Play !
        if len(self.queue) >= 1 and (
            not self.voice_client or not self.voice_client.is_playing()
        ):
            await self.start_playing(ctx)
        else:
            asyncio.create_task(self.update_now_playing(ctx, edit_only=True))

        # Preload next tracks if the queue has only one track
        # Or is played next
        # (prepare_next_track method has not been called before)
        if original_length == 1 or play_next:
            await self.prepare_next_track()

    async def play_previous(self, ctx: discord.ApplicationContext) -> None:
        self.previous = True
        self.voice_client.pause()
        if self.queue:
            track = self.queue[0]
            asyncio.create_task(self.post_process(track))
        self.queue.insert(0, self.stack_previous.pop())
        await self.start_playing(self.last_context)

    async def post_process(self, track: Optional[Track] = None) -> None:
        """Postprocess a track in the queue. Defaults to the first one"""
        if not track:
            track = self.queue[0]
        track.timer.reset()
        self.last_played_time = datetime.now()
        if isinstance(track.stream_source, DeezerChunkedInputStream):
            await track.stream_source.close()

    def get_queue(self) -> List[dict]:
        """Returns a simplified version of the current queue."""
        return [
            {
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "cover": track.cover_url,
                "duration": track.duration,
                "url": track.source_url,
            }
            for track in self.queue
        ]

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

        else:
            self.shuffled_queue = self.queue[1:]
            random.shuffle(self.shuffled_queue)
            self.queue = [current_song] + self.shuffled_queue

        self.shuffle = not self.shuffle
        asyncio.create_task(self.update_now_playing(self.last_context, edit_only=True))
        return True

    def after_playing(
        self, ctx: discord.ApplicationContext, error: Optional[Exception]
    ) -> None:
        """Callback function executed after a track finishes playing."""
        self.last_played_time = datetime.now()

        if error:
            logging.error(repr(error))

        if self.is_seeking:
            return

        asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

    async def play_next(self, ctx: discord.ApplicationContext) -> None:
        """Plays the next track in the queue, handling looping and previous track logic."""
        played_track: Track = self.queue[0]
        played_track.timer.reset()
        self.previous_track_id = played_track.id

        if not (self.loop_current or self.previous):
            self.stack_previous.append(played_track)

        if self.loop_queue and not self.loop_current:
            self.to_loop.append(played_track)

        asyncio.create_task(self.post_process(played_track))

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
                    await self.voice_client.cleanup()
                    await self.close_streams()
                    del self.session_manager.server_sessions[self.guild_id]
                    logging.info(
                        f"Deleted audio session in {self.guild_id} due to inactivity."
                    )
                    break

            await asyncio.sleep(17)

    async def close_streams(self) -> None:
        close_tasks = []
        chain = itertools.chain(self.queue, self.stack_previous, self.to_loop)

        # Close streams
        for stream in chain:
            source = stream.stream_source
            if isinstance(source, (DeezerChunkedInputStream)):
                close_tasks.append(source.close())
            elif isinstance(source, AbsChunkedInputStream):
                close_tasks.append(asyncio.to_thread(source.close))
        if close_tasks:
            await asyncio.gather(*close_tasks)

        # Free the memory
        for source in chain:
            del source
        gc.collect()
