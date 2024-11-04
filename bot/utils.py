import mutagen.ogg
import mutagen.oggvorbis
from typing import Dict, Optional, Tuple, List, Union, Callable
import discord
import base64
import hashlib
import logging
import os
import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from time import time
from urllib.parse import urlparse, parse_qs

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

from config import TEMP_FOLDER, CACHE_EXPIRY, CACHE_SIZE
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


async def get_dominant_rgb_from_url(
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
    files = sorted(TEMP_FOLDER.glob('*.cache'), key=os.path.getmtime)

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
    if isinstance(audio_file, (MP3, ID3, WAVE)) and audio_file.tags:
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


async def tag_ogg_file(
    file_path: Union[Path, str],
    title: Optional[str],
    artist: Optional[str],
    album_cover_url: Optional[str],
    album: Optional[str],
):
    """
    Tags an OGG Vorbis file with title, artist, and an album cover from a URL.

    Args:
        file_path: Path to the input OGG file.
        title: Title of the track.
        artist: Artist name.
        album_cover_url: URL of the album cover image (JPEG or PNG).
    """
    audio = OggVorbis(file_path)

    # Set title and artist tags
    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album

    # Fetch the album cover
    async with aiohttp.ClientSession() as session:
        async with session.get(album_cover_url) as response:
            response.raise_for_status()
            cover_bytes = await response.read()

    # Create a Picture object
    picture = Picture()
    picture.type = 3  # Front Cover
    picture.width = 640
    picture.height = 640
    picture.mime = "image/jpeg"
    picture.desc = "Cover"
    picture.data = cover_bytes

    # Encode the picture data in base64
    picture_encoded = base64.b64encode(picture.write()).decode("ascii")

    # Add the picture to the metadata
    audio["metadata_block_picture"] = [picture_encoded]

    # Save the tags
    audio.save(file_path)
    logging.info(f"Tagged '{file_path}' successfully.")


def split_into_chunks(string: str, max_length=1024) -> list:
    """Convert a string into a list of chunks with an adjustable size."""
    paragraphs = string.split('\n')  # Split the text into paragraphs
    chunks = []
    current_chunk = ''

    for paragraph in paragraphs:
        # +1 accounts for the '\n' that was removed by split
        additional_length = len(paragraph) + 1

        if len(current_chunk) + additional_length > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ''

            # If the single paragraph itself is longer than max_length, split it
            if additional_length > max_length:
                # Split the long paragraph into smaller parts
                start = 0
                while start < len(paragraph):
                    end = start + max_length - 1  # -1 to account for '\n'
                    chunk_part = paragraph[start:end]
                    chunks.append(chunk_part)
                    start = end
                continue

        # Add the paragraph and a newline to the current chunk
        if current_chunk:
            current_chunk += '\n' + paragraph
        else:
            current_chunk = paragraph

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def extract_video_id(url):
    """
    Extracts the YouTube video ID from a given URL.

    Args:
        url (str): The YouTube URL.

    Returns:
        str or None: The extracted video ID if found; otherwise, None.
    """
    parsed_url = urlparse(url)
    if 'youtube' in parsed_url.hostname:
        # For URLs like https://www.youtube.com/watch?v=VIDEO_ID
        if parsed_url.path == '/watch':
            query_params = parse_qs(parsed_url.query)
            return query_params.get('v', [None])[0]
        # For URLs like https://www.youtube.com/embed/VIDEO_ID
        elif '/embed/' in parsed_url.path:
            return parsed_url.path.split('/embed/')[1]
    elif 'youtu.be' in parsed_url.hostname:
        # For URLs like https://youtu.be/VIDEO_ID
        return parsed_url.path.lstrip('/')
    else:
        return None


async def send_response(
    respond: Callable[[str], discord.Message],
    message: str,
    guild_id: int
) -> None:
    try:
        await respond(message)
    except discord.errors.HTTPException:
        logging.error(
            f"Failed to send response for guild {guild_id}. "
            "Invalid Webhook Token."
        )
