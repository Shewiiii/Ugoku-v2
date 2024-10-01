import discord
import api
from typing import Dict, Optional, Tuple, List
import base64
import hashlib
import logging
import os
import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from time import time

import aiohttp
import mutagen
from PIL import Image
from mutagen.flac import FLAC
from mutagen.flac import Picture
from mutagen.id3 import ID3, APIC
from mutagen.m4a import M4A
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from bot.vocal.types import TrackInfo, ActiveGuildInfo, CurrentSongInfo
from config import TEMP_FOLDER, CACHE_EXPIRY, CACHE_SIZE

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.vocal.server_session import ServerSession

logger = logging.getLogger(__name__)


def extract_number(string: str) -> Optional[str]:
    """
    Extract a natural number from a string.

    Args:
        string (str): The input string to extract a number from.

    Returns:
        Optional[str]: The extracted number as a string, or None if no number is found.
    """
    search = re.search(r'\d+', string)
    if not search:
        return

    return search.group()


def is_onsei(string: str) -> bool:
    """
    Determines if a string refers to an audio work/onsei.
    Checks if it is starting by'RJ' or 'VJ', 
    or contains exactly 6 or 8 digits.

    Args:
        string (str): The string to evaluate.

    Returns:
        bool: True if the string meets any of the conditions, False otherwise.
    """
    if string.startswith(('RJ', 'VJ')):
        return True

    if re.fullmatch(r'\d{6}|\d{8}', string):
        return True

    return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing or replacing illegal characters.

    Args:
        filename (str): The filename to sanitize.

    Returns:
        str: The sanitized filename.

    Note:
        This function keeps only alphanumeric characters, hyphens, underscores, and periods.
    """
    # For Windows, common illegal characters include: / / : * ? " < > |
    # The following pattern keeps only alphanumeric characters, hyphens, underscores, and periods.
    sanitized_filename = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
    return sanitized_filename


def rgb_to_hsv(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """
    Convert RGB color values to HSV color space.

    Args:
        r (float): Red component (0-255).
        g (float): Green component (0-255).
        b (float): Blue component (0-255).

    Returns:
        Tuple[float, float, float]: A tuple containing the HSV values.
    """
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    delta = max_val - min_val

    if delta == 0:
        h = 0
    elif max_val == r:
        h = (60 * ((g - b) / delta) + 360) % 360
    elif max_val == g:
        h = (60 * ((b - r) / delta) + 120) % 360
    elif max_val == b:
        h = (60 * ((r - g) / delta) + 240) % 360

    s = 0 if max_val == 0 else (delta / max_val)
    v = max_val

    return h, s, v


def get_accent_color(
    image_bytes: bytes,
    threshold: int = 50
) -> Tuple[int, int, int]:
    """
    Extract an accent color from an image.

    Args:
        image_bytes (bytes): The image data as bytes.
        threshold (int, optional): The color distance threshold. Defaults to 50.

    Returns:
        Tuple[int, int, int]: The RGB values of the extracted accent color.
    """
    image = Image.open(BytesIO(image_bytes))
    image = image.convert('RGB')  # Ensure image RGB

    # Resize image to reduce computation time
    image = image.resize((50, 50))

    # Get pixels as a list of tuples
    pixels = list(image.getdata())

    # Count the frequency of each color
    color_counts = Counter(pixels)

    # Find the dominant color
    dominant_color = color_counts.most_common(1)[0][0]

    # Filter out colors too close to the dominant color
    def color_distance(c1, c2):
        return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

    accent_color = None
    max_priority = -1

    for color, count in color_counts.items():
        if color_distance(dominant_color, color) > threshold:
            # Convert color to HSV
            _, saturation, brightness = rgb_to_hsv(*color)

            # Calculate priority based on saturation and brightness
            priority = saturation * brightness * count

            if priority > max_priority:
                max_priority = priority
                accent_color = color

    return accent_color


async def get_accent_color_from_url(
    image_url: str
) -> Tuple[int, int, int]:
    """
    Fetch an image from a URL and extract its accent color.

    Args:
        image_url (str): The URL of the image.

    Returns:
        Tuple[int, int, int]: The RGB values of the extracted accent color.

    Raises:
        aiohttp.ClientResponseError: If the image fetch fails.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            response.raise_for_status()
            cover_bytes = await response.read()
            dominant_rgb = get_accent_color(cover_bytes)

    return dominant_rgb


# Cache functions for custom sources
def get_cache_path(string: bytes) -> Path:
    """
    Generate a cache file path for a given byte string.

    Args:
        string (bytes): The byte string to generate a cache path for.

    Returns:
        Path: The generated cache file path.
    """
    # Hash the URL to create a unique filename
    hash_digest = hashlib.md5(string).hexdigest()
    return TEMP_FOLDER / f'{hash_digest}.cache'


def cleanup_cache() -> None:
    """
    Clean up the cache directory by removing old and excess files.

    This function removes files that exceed the cache size limit and deletes expired files.
    """
    files = sorted(TEMP_FOLDER.glob('*'), key=os.path.getmtime)

    # Remove files that exceed the cache size limit
    while len(files) > CACHE_SIZE:
        oldest_file = files.pop(0)
        oldest_file.unlink()

    # Remove expired files
    current_time = time()
    for file in files:
        if current_time - file.stat().st_mtime > CACHE_EXPIRY:
            file.unlink()


def extract_cover_art(file_path) -> Optional[bytes]:
    """
    Extract cover art from an audio file.

    Args:
        file_path: The path to the audio file.

    Returns:
        Optional[bytes]: The cover art image data, or None if no cover art is found.
    """
    audio_file = mutagen.File(file_path)

    # For files using ID3 tags (mp3, sometimes WAV)
    if isinstance(audio_file, (MP3, ID3, WAVE)):
        for tag in audio_file.tags.values():
            if isinstance(tag, APIC):
                cover_data = tag.data
                img = cover_data
                return img

    # For files using PICTURE block (OGG, Opus)
    elif isinstance(audio_file, (OggVorbis, OggOpus)):
        covers_data = audio_file.get('metadata_block_picture')
        if covers_data:
            b64_data: str = covers_data[0]
            data = base64.b64decode(b64_data)
            picture = Picture(data)
            return picture.data

    # For files using PICTURE block but FLAC x)
    elif isinstance(audio_file, FLAC):
        if audio_file.pictures:
            img = audio_file.pictures[0].data
            return img

    # MP4/M4A containers (mp4, ALAC, AAC and idk)
    elif isinstance(audio_file, (MP4, M4A)):
        tags = audio_file.tags
        if tags:
            cover_data = tags.get("covr")
            if cover_data:
                img = cover_data[0]
                return img


def get_metadata(file_path) -> Dict[str, List[str]]:
    """
    Extract metadata from an audio file.

    Args:
        file_path: The path to the audio file.

    Returns:
        Dict[str, List[str]]: A dictionary containing the extracted metadata.
    """
    audio_file = mutagen.File(file_path)

    if not audio_file:
        return {}

    # For files using ID3 tags (e.g. MP3, sometimes WAV)
    if isinstance(audio_file, (MP3, ID3, WAVE)):
        return {
            'title': audio_file.get('TIT2', ['?']),
            'album': audio_file.get('TALB', ['?']),
            'artist': audio_file.get('TPE1', ['?'])
        }

    return {key: value for key, value in audio_file.items()}


async def update_active_servers(
    bot: discord.Bot,
    server_sessions: Dict[int, 'ServerSession']
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
    await api.update_active_servers(active_guilds)
