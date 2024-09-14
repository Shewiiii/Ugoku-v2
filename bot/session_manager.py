import logging

import discord

from typing import Dict
from bot.onsei import Onsei
from bot.server_session import ServerSession

onsei = Onsei()

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self) -> None:
        self.server_sessions = {}

    async def connect(
        self,
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
