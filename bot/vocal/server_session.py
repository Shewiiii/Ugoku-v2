import asyncio
from copy import deepcopy
from collections import deque
from datetime import datetime, timedelta
import gc
import itertools
import logging
from pathlib import Path
import random
from time import perf_counter
from typing import Optional, List, Union

import discord
from librespot.audio import AbsChunkedInputStream

from bot.utils import get_cache_path
from bot.vocal.queue_view import QueueView
from bot.vocal.now_playing_view import nowPlayingView
from bot.vocal.track_dataclass import Track
from config import (
    AUTO_LEAVE_DURATION,
    DEFAULT_AUDIO_VOLUME,
    DEFAULT_ONSEI_VOLUME,
    DEEZER_ENABLED,
    SPOTIFY_ENABLED,
    SPOTIFY_API_ENABLED,
    DEFAULT_AUDIO_BITRATE,
)
from deezer_decryption.chunked_input_stream import DeezerChunkedInputStream
from deezer_decryption.api import Deezer
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
        self.time_elapsed: int = 0
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

    async def display_queue(self, ctx: discord.ApplicationContext) -> None:
        """Displays the current queue."""
        view = QueueView(
            self.queue,
            self.to_loop,
            self.bot,
            self.last_played_time,
            self.time_elapsed,
            self.voice_client.is_playing(),
        )
        await view.display(ctx)

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
            if len(self.queue) > 1:
                next_track = f"{self.queue[1]:markdown}"

            sent_embed.add_field(
                name="Remaining",
                value=str(len(self.queue) - 1),
            ).add_field(name="Next", value=f"{next_track}")
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
        if not self.voice_client or not self.voice_client.is_playing():
            return

        self.is_seeking = True
        self.time_elapsed = position
        self.voice_client.pause()

        if not quiet and self.last_context:
            await self.last_context.send(f"Seeking to {position} seconds")

        await self.start_playing(self.last_context, start_position=position)

    async def load_deezer_stream(
        self, index: int = 0, load_chunks: bool = True, current_id: Optional[int] = None
    ) -> Optional[DeezerChunkedInputStream]:
        start = perf_counter()
        if (
            index >= len(self.queue)
            or not DEEZER_ENABLED
            or self.queue[index].service != "spotify/deezer"
            or isinstance(self.queue[0].stream_source, (str, Path))
            or current_id in self.deezer_blacklist
        ):
            return

        deezer: Deezer = self.bot.deezer
        track: Track = self.queue[index]

        # Already a Deezer stream: reset the position
        if isinstance(track.stream_source, DeezerChunkedInputStream):
            if load_chunks:
                await asyncio.to_thread(
                    track.stream_source.set_chunks, timer_start=start
                )
            # If seeking: current position will automatically be set by Ffmpeg's pipe
            track.stream_source.current_position = 0
            return track.stream_source

        # Try to get native track API (to grab the sostrng from irsc)
        native_track_api = await deezer.parse_spotify_track(
            track.source_url, self.bot.spotify.sessions.sp
        )
        if not native_track_api:
            return

        # Setup streaming
        deezer_id = native_track_api["id"]
        gw_track_api = await deezer.get_track(deezer_id)
        if not gw_track_api:
            return

        # Load the stream
        track_token = gw_track_api["TRACK_TOKEN"]
        stream_url = (await deezer.get_stream_urls([track_token]))[0]
        if not stream_url:
            # Track not found at desired bitrate and no alternative found
            return

        input_stream = DeezerChunkedInputStream(
            deezer_id, stream_url, track_token, self.bot, track
        )
        if load_chunks:
            await asyncio.to_thread(input_stream.set_chunks, timer_start=start)

        # Only update if the track hasn't changed
        if not current_id or current_id == track.id:
            track.stream_source = input_stream

        return input_stream

    async def load_spotify_stream(
        self, index: int = 0, current_id: Optional[str] = None
    ) -> Optional[AbsChunkedInputStream]:
        if index >= len(self.queue) or not SPOTIFY_ENABLED:
            return None
        track: Track = self.queue[index]

        # Handle Spotify stream generators
        if callable(track.stream_source):
            try:
                input_stream = await track.stream_source()
            except Exception as e:
                logging.error(repr(e))
                return None
            if not current_id or current_id == track.id:
                track.stream_source = input_stream
            logging.info(f"Loaded Spotify stream of {track}")

        else:
            # Already a Spotify stream
            input_stream = track.stream_source

        # Skip non-audio content in Spotify streams
        if isinstance(input_stream, AbsChunkedInputStream):
            await asyncio.to_thread(input_stream.seek, 167)
            return input_stream

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
            await self.load_deezer_stream(
                load_chunks=True
            ) or await self.load_spotify_stream(current_id=track.id)

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
        self.time_elapsed = start_position
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
        if len(self.queue) <= index:
            return
        track: Track = self.queue[index]
        current_id = track.id

        # Deezer task
        deezer_stream_task = asyncio.create_task(
            self.load_deezer_stream(index, current_id=current_id)
        )

        # Embed task
        if track.unloaded_embed:
            sp = self.bot.spotify.sessions.sp if SPOTIFY_API_ENABLED else None
            asyncio.create_task(track.generate_embed(sp))

        # Deezer/Spotify load
        if not await deezer_stream_task:
            self.deezer_blacklist.add(current_id)
            # Spotify task
            asyncio.create_task(self.load_spotify_stream(index, current_id))

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks: List[Track],
        interaction: Optional[discord.Interaction] = None,
        play_next: bool = False,
    ) -> None:
        """Adds tracks to the queue and starts playback if not already playing."""

        async def respond(content: str):
            edit_func = interaction.respond if interaction else ctx.respond
            try:
                await edit_func(content=content)
            except discord.errors.NotFound as e:
                logging.error(repr(e))

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
        asyncio.create_task(
            respond(
                content=f"Added to queue: {titles}{' !' if c <= 3 else f', and {c - 3} more songs !'}"
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
        # (prepare_next_track method has not been called before)
        if original_length == 1:
            await self.prepare_next_track()

    async def play_previous(self, ctx: discord.ApplicationContext) -> None:
        self.previous = True
        self.queue.insert(0, self.stack_previous.pop())
        if self.voice_client.is_playing():
            # Do not change ! Pause to not trigger the after_playing callback
            self.voice_client.pause()
        await self.start_playing(ctx)

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
        asyncio.create_task(self.update_now_playing(self.last_context))
        return True

    def after_playing(
        self, ctx: discord.ApplicationContext, error: Optional[Exception]
    ) -> None:
        """Callback function executed after a track finishes playing."""
        self.last_played_time = datetime.now()
        if error:
            raise error

        if self.is_seeking:
            return

        asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

    async def play_next(self, ctx: discord.ApplicationContext) -> None:
        """Plays the next track in the queue, handling looping and previous track logic."""
        played_track: Track = self.queue[0]
        self.previous_track_id = played_track.id

        if not self.queue and self.loop_queue:
            self.queue, self.to_loop = self.to_loop, []

        if not (self.loop_current or self.previous):
            self.stack_previous.append(played_track)

        if self.loop_queue and not self.loop_current:
            self.to_loop.append(played_track)

        if not self.loop_current:
            if not (self.previous or self.loop_current):
                source = played_track.stream_source
                if isinstance(source, DeezerChunkedInputStream):
                    # The user is unlikely to /previous the song, so we free the memory
                    logging.info(f"Deezer stream {played_track} has been closed")
                    asyncio.create_task(source.close())

            self.queue.pop(0)
        # After pop
        if not self.queue:
            # Can reset the skipped status if there is no more tracks
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
