import discord
from datetime import datetime
import json
import logging

from bot.vocal.types import (
    TrackInfo,
    ActiveGuildInfo,
    CurrentSongInfo,
    Optional,
    List
)

async def notify_clients() -> None:
    """Notify all connected SSE clients of server updates."""
    from api.api import connected_clients
    logging.info(
        f"Notifying {len(connected_clients)} clients of server update")
    for queue in connected_clients:
        await queue.put(json.dumps({
            "message": "Success!" if active_servers else "No active voice connections",
            "server_time": datetime.now().isoformat(),
            "guilds": active_servers
        }))
    logging.info("All clients notified")


async def update_active_servers(
    bot: discord.Bot,
    server_sessions: dict
) -> None:
    """
    Update the list of active servers and their current playback information.

    Args:
        bot (discord.Bot): The Discord bot instance.
        server_sessions (Dict[int, 'ServerSession']): A dictionary of active server sessions.

    This function collects information about currently playing songs, queues, and playback history
    for each active voice client, and sends this information to an external API.
    """
    active_guilds: List[ActiveGuildInfo] = []
    for vc in bot.voice_clients:
        if not isinstance(vc, discord.VoiceClient):
            continue  # Skip if not a VoiceClient
        if vc.is_playing():
            guild = vc.guild
            session = server_sessions.get(guild.id)
            queue = session.get_queue() if session else []
            # Skip the first item as it's the currently playing song
            song_info = queue.pop(0)
            history: List[TrackInfo] = session.get_history() if session else []

            current_song: Optional[CurrentSongInfo] = {
                "title": song_info['title'],
                "artist": song_info.get('artist'),
                "album": song_info.get('album'),
                "cover": song_info.get('cover'),
                "duration": song_info.get('duration'),
                "playback_start_time": session.playback_start_time,
                "url": song_info['url']
            } if song_info else None

            guild_info: ActiveGuildInfo = {
                # Convert to string to avoid overflow in JavaScript
                "id": str(guild.id),
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "currentSong": current_song,
                "queue": queue,
                "history": history
            }
            active_guilds.append(guild_info)

    logging.info("Updating active servers.")
    global active_servers
    active_servers = active_guilds
    logging.info("Active servers updated.")
    await notify_clients()
