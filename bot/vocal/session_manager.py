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

    async def connect(
        self,
        ctx: discord.ApplicationContext,
        bot: discord.Bot
    ) -> Optional[ServerSession]:
        """
        Connect to a voice channel and create or retrieve a ServerSession.

        This method attempts to connect to the user's voice channel and create
        a new ServerSession if one doesn't exist for the guild, or retrieve
        an existing one.

        Args:
            ctx (discord.ApplicationContext): The context of the command invocation.
            bot (discord.Bot): The Discord bot instance.

        Returns:
            Optional[ServerSession]: A ServerSession instance if connection is successful,
                                     None if the user is not in a voice channel.

        Note:
            This method will create a new voice client connection if one doesn't exist.
        """
        user_voice = ctx.user.voice
        guild_id = ctx.guild.id
        if not user_voice:
            return

        channel = user_voice.channel

        if not ctx.voice_client:
            await channel.connect()
            # Clean server session after a new connection
            self.server_sessions.pop(guild_id, None)

        if ctx.voice_client.is_connected():
            if guild_id not in self.server_sessions:
                self.server_sessions[guild_id] = ServerSession(
                    guild_id,
                    ctx.voice_client,
                    bot,
                    ctx.channel_id,
                    self
                )
            return self.server_sessions[guild_id]

session_manager = SessionManager()
