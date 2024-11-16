import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Literal

import discord
from librespot.audio import AbsChunkedInputStream

from api.update_active_servers import update_active_servers
from bot.vocal.queue_view import QueueView
from bot.vocal.control_view import controlView
from bot.vocal.types import QueueItem, TrackInfo, LoopMode, SimplifiedTrackInfo
from config import AUTO_LEAVE_DURATION, DEFAULT_AUDIO_VOLUME

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.vocal.session_manager import SessionManager


class ServerSession:
    """Represents an audio session for a Discord server.

    This class manages the audio playback, queue, and various controls for a specific server.

    Attributes:
        bot: The Discord bot instance.
        guild_id: The unique identifier of the Discord guild (server).
        voice_client: The voice client connected to the server's voice channel.
        queue: The current queue of tracks to be played.
        to_loop: Tracks that are set to be looped.
        last_played_time: Timestamp of when the last track was played.
        loop_current: Flag indicating if the current track should be looped.
        loop_queue: Flag indicating if the entire queue should be looped.
        skipped: Flag indicating if the current track was skipped.
        shuffle: Flag indicating if the queue is shuffled.
        original_queue: The original order of the queue before shuffling.
        shuffled_queue: The shuffled order of the queue.
        previous: Flag indicating if the previous track command was used.
        stack_previous: Stack of previously played tracks.
        is_seeking: Flag indicating if a seek operation is in progress.
        channel_id: The ID of the text channel associated with this session.
        session_manager: The session manager handling this server session.
        auto_leave_task: Task for automatically leaving the voice channel after inactivity.
        playback_start_time: Timestamp of when the current track started playing.
        last_context: The last context used for interaction.
        volume: The current volume level of the audio playback.
    """

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
        self.queue: List[QueueItem] = []
        self.to_loop: List[QueueItem] = []
        self.last_played_time = datetime.now()
        self.time_elapsed = 0
        self.loop_current = False
        self.loop_queue = False
        self.skipped = False
        self.shuffle = False
        self.original_queue: List[QueueItem] = []
        self.shuffled_queue: List[QueueItem] = []
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

    async def display_queue(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        """Displays the current queue.

        Args:
            ctx: The Discord application context.
        """
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
        """Sends an embed with information about the currently playing track.

        Args:
            ctx: The Discord application context.
        """
        # Retrieve the current track_info from the queue
        track_info: dict = self.queue[0]['track_info']
        embed: Optional[discord.Embed] = track_info['embed']
        title: str = track_info['display_name']
        url: str = track_info['url']
        title_markdown = f'[{title}](<{url}>)'

        if embed:
            # In case it requires additional api calls,
            # The embed is generated when needed only
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
            embed=embed,
            view=view,
            silent=True
        )

    async def seek(
        self,
        position: int,
        quiet: bool = False
    ) -> bool:
        """Seeks to a specific position in the current track.

        Args:
            position: The position to seek to in seconds.

        Returns:
            bool: True if seeking was successful, False otherwise.
        """
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

    async def start_playing(
        self,
        ctx: discord.ApplicationContext,
        start_position: int = 0
    ) -> None:
        """Handles the playback of the next track in the queue.

        Args:
            ctx: The Discord application context.
            start_position: The position to start playing from in seconds.
        """
        self.last_context = ctx
        if not self.queue:
            logging.info(f'Playback stopped in {self.guild_id}')
            await update_active_servers(self.bot, self.session_manager.server_sessions)
            return  # No songs to play

        source = self.queue[0]['track_info']['source']

        # If source is a stream generator
        if isinstance(source, Callable):
            source = await source()  # Generate a fresh stream
            source.seek(167)  # Skip the non-audio content

        # Set up FFmpeg options for seeking and volume
        ffmpeg_options = {
            'options': f'-ss {start_position} -filter:a "volume={self.volume / 100}"'
        }

        ffmpeg_source = discord.FFmpegOpusAudio(
            source,
            pipe=isinstance(source, AbsChunkedInputStream),
            bitrate=510,
            **ffmpeg_options
        )

        self.voice_client.play(
            ffmpeg_source,
            after=lambda e=None: self.after_playing(ctx, e)
        )

        self.time_elapsed = start_position
        now = datetime.now()
        self.playback_start_time = now.isoformat()
        self.last_played_time = now
        await update_active_servers(
            self.bot,
            self.session_manager.server_sessions
        )

        # Send "Now playing" at the end to slightly reduce audio latency
        if (
            not self.is_seeking
            and (self.skipped or not self.loop_current)
            and not (len(self.queue) == 1 and self.loop_queue)
        ):
            await self.send_now_playing(ctx)
            # Reset the skip flag
            self.skipped = False

        # Reset flags
        self.is_seeking = False
        self.previous = False

    async def add_to_queue(
        self,
        ctx: discord.ApplicationContext,
        tracks_info: List[TrackInfo],
        source: Literal['Spotify', 'Youtube', 'Custom', 'Onsei'],
        interaction: Optional[discord.Interaction] = None
    ) -> None:
        """Adds tracks to the queue and starts playback if not already playing.

        Args:
            ctx: The Discord application context.
            tracks_info: A list of track information dictionaries.
            source: The source of the tracks ('Spotify', 'Youtube', 'Custom', or 'Onsei').
            interaction: A discord interaction if that method has been triggered by one.
        """
        # Check if triggered by an interaction
        if interaction:
            edit = interaction.edit_original_response
        else:
            edit = ctx.edit

        for track_info in tracks_info:
            queue_item: QueueItem = {
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
        if len(tracks_info) == 1:
            title = tracks_info[0]['display_name']
            url = tracks_info[0]['url']
            await edit(content=f'Added to queue: [{title}](<{url}>) !')

        # If 2 or 3 songs are added
        elif len(tracks_info) in [2, 3]:
            titles_urls = ', '.join(
                f'[{track_info["display_name"]}](<{track_info["url"]}>)'
                for track_info in tracks_info
            )
            await edit(content=f'Added to queue: {titles_urls} !')

        # If more than 3 songs are added
        elif len(tracks_info) > 3:
            titles_urls = ', '.join(
                f'[{track_info["display_name"]}](<{track_info["url"]}>)'
                for track_info in tracks_info[:3]
            )
            additional_songs = len(tracks_info) - 3
            await edit(
                content=(
                    f'Added to queue: {titles_urls}, and '
                    f'{additional_songs} more song(s) !')
            )

        if not self.voice_client.is_playing() and len(self.queue) >= 1:
            await self.start_playing(ctx)

    async def play_previous(self, ctx: discord.ApplicationContext) -> None:
        """Plays the previous track in the queue.

        Args:
            ctx: The Discord application context.
        """
        self.previous = True
        self.queue.insert(0, self.stack_previous.pop())
        if self.voice_client.is_playing():
            self.voice_client.pause()
        await self.start_playing(ctx)

    async def skip_track(self, ctx: discord.ApplicationContext) -> bool:
        """Skips the current track and plays the next one in the queue.

        Args:
            ctx: The Discord application context.

        Returns:
            bool: True if a track was skipped, False otherwise.
        """
        if not self.voice_client or not self.voice_client.is_playing():
            return False

        self.voice_client.pause()
        await self.play_next(ctx)
        return True

    def get_queue(self) -> List[SimplifiedTrackInfo]:
        """Returns a simplified version of the current queue.

        Returns:
            List[SimplifiedTrackInfo]: A list of simplified track information dictionaries.
        """
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
        """Toggles shuffling of the queue.
        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        if len(self.queue) <= 1:
            self.shuffle = not self.shuffle
            # No need to shuffle if queue has 0 or 1 song
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
        """Callback function executed after a track finishes playing.

        Args:
            ctx: The Discord application context.
            error: Any error that occurred during playback, or None.
        """
        self.last_played_time = datetime.now()
        if error:
            raise error

        if self.is_seeking:
            # If we're seeking, don't do anything
            return

        if self.queue and self.voice_client.is_connected():
            asyncio.run_coroutine_threadsafe(
                self.play_next(ctx), self.bot.loop
            )

    async def play_next(
        self,
        ctx: discord.ApplicationContext
    ) -> None:
        """Plays the next track in the queue, handling looping and previous track logic.

        Args:
            ctx: The Discord application context.
        """
        if self.queue and not self.loop_current and not self.previous:
            self.stack_previous.append(self.queue[0])

        if self.loop_queue and not self.loop_current:
            self.to_loop.append(self.queue[0])

        if not self.loop_current:
            self.queue.pop(0)
        if not self.queue and self.loop_queue:
            self.queue, self.to_loop = self.to_loop, []

        await self.start_playing(ctx)

    def get_history(self) -> List[SimplifiedTrackInfo]:
        """Returns a simplified version of the play history.

        Returns:
            List[SimplifiedTrackInfo]: A list of simplified track information dictionaries.
        """
        return [
            {
                "title": track['track_info']['title'],
                "artist": track['track_info'].get('artist'),
                "album": track['track_info'].get('album'),
                "cover": track['track_info'].get('cover'),
                "duration": track['track_info'].get('duration'),
                "url": track['track_info']['url']
            }
            for track in self.stack_previous
        ]

    async def toggle_loop(self, mode: LoopMode) -> bool:
        """Toggles the loop mode for the current track or entire queue.

        Args:
            mode: The loop mode to set ('noLoop', 'loopAll', or 'loopOne').

        Returns:
            bool: True if the loop mode was successfully changed, False otherwise.
        """
        if mode == 'noLoop':
            self.loop_current = False
            self.loop_queue = False
            response = 'You are not looping anymore.'
        elif mode == 'loopAll':
            self.loop_current = False
            self.loop_queue = True
            response = 'You are now looping the queue!'
        elif mode == 'loopOne':
            self.loop_current = True
            self.loop_queue = False
            response = 'You are now looping the current song!'
        else:
            return False

        # Send message to the server
        channel = self.bot.get_channel(self.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await channel.send(response)
        return True

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
