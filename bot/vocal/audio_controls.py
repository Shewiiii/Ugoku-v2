from bot.vocal.server_session import ServerSession
from api.update_active_servers import update_active_servers
from bot.vocal.session_manager import session_manager as sm
from bot.vocal.types import LoopMode


async def seek_playback(guild_id: str, position: int) -> bool:
    """
    Seek to a specific position in the currently playing track.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.
        position (int): The position to seek to, in seconds.

    Returns:
        bool: True if seeking was successful, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.seek(position)


async def toggle_loop(guild_id: str, mode: LoopMode) -> bool:
    """
    Toggle the loop mode for the current playback session.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.
        mode (LoopMode): The loop mode to set. Can be 'noLoop', 'loopAll', or 'loopOne'.

    Returns:
        bool: True if the loop mode was successfully changed, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.toggle_loop(mode)


async def skip_track(guild_id: str) -> bool:
    """
    Skip the currently playing track.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.

    Returns:
        bool: True if the track was successfully skipped, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    return await session.skip_track(session.last_context)


async def previous_track(guild_id: str) -> bool:
    """
    Play the previous track in the queue.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.

    Returns:
        bool: True if the previous track was successfully played, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    await session.play_previous(session.last_context)
    return True


async def shuffle_queue(guild_id: str, is_active: bool) -> bool:
    """
    Shuffle or unshuffle the current queue.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.
        is_active (bool): True to activate shuffling, False to deactivate.

    Returns:
        bool: True if the queue was successfully shuffled or unshuffled, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
        It also updates the queue for all connected clients after shuffling.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    success = await session.shuffle_queue(is_active)
    # Update the queue for all connected clients
    await update_active_servers(session.bot, sm.server_sessions)
    return success


async def set_volume(guild_id: str, volume: int) -> bool:
    """
    Set the volume for the current playback session.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.
        volume (int): The volume level to set, expected to be between 0 and 100.

    Returns:
        bool: True if the volume was successfully set, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
        The volume is set as a fraction of 1 (e.g., 50 becomes 0.5) for the voice client.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    session.voice_client.source.volume = volume / 100
    session.volume = volume
    return True

async def toggle_playback(guild_id: str) -> bool:
    """
    Toggle the playback state for the current session.

    Args:
        guild_id (str): The ID of the guild (server) where the playback is occurring.

    Returns:
        bool: True if the playback state was successfully toggled, False if the guild is not in an active session.

    Note:
        This function converts the string guild_id to an integer before processing.
    """
    guild_id = int(guild_id)
    if guild_id not in sm.server_sessions:
        return False
    session: ServerSession = sm.server_sessions[guild_id]
    if session.voice_client.is_playing():
        session.voice_client.pause()
    else:
        session.voice_client.resume()
    return True

