import asyncio
import logging
import discord

from typing import Optional
from bot.vocal.onsei import Onsei
from bot.vocal.server_session import ServerSession

onsei = Onsei()

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self) -> None:
        """
        Initialize the SessionManager.

        This constructor creates an empty dictionary to store server sessions.
        """
        self.server_sessions = {}

    def connect(
        self, ctx: discord.ApplicationContext, bot: discord.Bot
    ) -> Optional[ServerSession]:
        """
        Connect to a voice channel, create or retrieve a ServerSession and update the last context.

        This method attempts to connect to the user's voice channel and create
        a new ServerSession if one doesn't exist for the guild, or retrieve
        an existing one.

        Note:
            This method will create a new voice client connection if one doesn't exist.
        """
        user_voice = ctx.user.voice
        guild_id = ctx.guild.id
        if not user_voice:
            return

        channel = user_voice.channel

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            connect_task = asyncio.create_task(channel.connect())
            # Clean server session after a new connection
            old_session: ServerSession = self.server_sessions.pop(guild_id, None)
            if old_session:
                asyncio.create_task(old_session.clean_session())

        if guild_id not in self.server_sessions:
            session = ServerSession(
                guild_id, None, bot, ctx.channel_id, self, connect_task
            )
            self.server_sessions[guild_id] = session
            # Define the voice client when it's done
            asyncio.create_task(session.wait_for_connect_task())

        self.server_sessions[guild_id].last_context = ctx
        return self.server_sessions[guild_id]


session_manager = SessionManager()
