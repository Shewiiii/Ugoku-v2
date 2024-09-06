import re
import api, discord, logging
from typing import Dict
logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    # Define a regular expression pattern that matches any character not allowed in filenames
    # For Windows, common illegal characters include: \ / : * ? " < > |
    # The following pattern keeps only alphanumeric characters, hyphens, underscores, and periods.
    sanitized_filename = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
    return sanitized_filename

async def update_active_servers(bot: discord.Bot, song_info: Dict[str, str] | None = None):
    active_guilds = []
    for vc in bot.voice_clients:
        if vc.is_playing():
            guild = vc.guild
            guild_info = {
                "id": guild.id,
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "currentSong": {
                    "title": song_info["display_name"] if song_info else None,
                    "artist": song_info["artist"] if song_info else None,
                    "album": song_info["album"] if song_info else None,
                    "cover": song_info["cover"] if song_info else None,
                    "duration": song_info["duration"] if song_info else None,
                }
            }
            active_guilds.append(guild_info)

    logger.info(f"Updating active servers. Current voice clients: {active_guilds}")
    await api.update_active_servers(active_guilds)
