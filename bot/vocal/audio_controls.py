from bot.vocal.server_session import ServerSession
from bot.utils import update_active_servers
from bot.vocal.session_manager import session_manager as sm


async def seek_playback(guild_id: str, position: int):
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.seek(position)


async def toggle_loop(guild_id: str, mode: str):
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.toggle_loop(mode)


async def skip_track(guild_id: str):
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.skip_track(session.last_context)


async def previous_track(guild_id: str):
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.previous_track(session.last_context)


async def shuffle_queue(guild_id: str, is_active: bool):
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    success = await session.shuffle_queue(is_active)
    # Update the queue for all connected clients
    await update_active_servers(session.bot, sm.server_sessions)
    return success


async def set_volume(guild_id: str, volume: int):
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    session.voice_client.source.volume = volume / 100
    session.volume = volume
    return True
