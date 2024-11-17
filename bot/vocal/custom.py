from typing import Optional

from bot.vocal.types import CoverData
from config import CACHE_EXPIRY, TEMP_FOLDER, DEFAULT_EMBED_COLOR
import discord

from dotenv import load_dotenv
from pathlib import Path
from time import time
import hashlib
import logging
import aiohttp
import json
import os

from bot.utils import cleanup_cache, get_cache_path, get_accent_color


logger = logging.getLogger(__name__)
load_dotenv()
IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')


async def upload_cover(cover_bytes: bytes) -> Optional[CoverData]:
    """
    Upload a song art cover to imgur and return the URL and cover hash.

    This function uses cache to avoid re-uploading the same cover.

    Keys: 'url', 'cover_hash'

    Args:
        cover_bytes (bytes): The cover art image data.

    Returns:
        Optional[CoverData]: A dictionary containing the cover URL, hash, and dominant RGB color.
                             Returns None if upload fails or IMGUR_CLIENT_ID is not set.
    """
    # Step 0: Cleanup expired files in the cache
    cleanup_cache()

    # Step 1: Hash the cover bytes
    cover_hash = hashlib.md5(cover_bytes).hexdigest()

    # Step 2: Check if the hash already exists in the cache
    cache_file_path: Path = TEMP_FOLDER / f"{cover_hash}.json"
    if cache_file_path.is_file():
        # Step 3: If cached, read and return the stored dict
        with open(cache_file_path, 'r') as cache_file:
            cached_data: dict = json.load(cache_file)
            return {
                'url': cached_data.get('url'),
                'cover_hash': cover_hash,
                'dominant_rgb': cached_data.get('dominant_rgb')
            }

    # Step 4: If not cached, upload to Imgur (If IMGUR_CLIENT_ID id valid)
    if not IMGUR_CLIENT_ID:
        return

    url = "https://api.imgur.com/3/upload"
    headers = {
        "Authorization": f"Client-ID {IMGUR_CLIENT_ID}"
    }

    async with aiohttp.ClientSession() as session:
        data = {
            'image': cover_bytes,
            'type': 'file'  # Imgur expects the file type
        }
        async with session.post(
            url,
            headers=headers, data=data
        ) as response:
            if response.status != 200:
                logging.error(
                    f"Upload failed with status {response.status}"
                )
                return

            json_response = await response.json()
            image_url = json_response['data']['link']

            # Step 5: Cache the uploaded image URL and
            # the dominant RGB. Prevent additional future requests
            dominant_rgb = get_accent_color(cover_bytes)
            with open(cache_file_path, 'w') as cache_file:
                json.dump({
                    'url': image_url,
                    'dominant_rgb': dominant_rgb
                },
                    cache_file)

            return {
                'url': image_url,
                'cover_hash': cover_hash,
                'dominant_rgb': dominant_rgb
            }


async def get_cover_data_from_hash(cover_hash: str) -> CoverData:
    """
    Retrieve cover art data for a given cover hash.

    Args:
        cover_hash (str): The hash of the cover art.

    Returns:
        CoverData: A dictionary containing the cover URL and its dominant RGB color.
                   If no data is found, returns a dict with None for URL and DEFAULT_EMBED_COLOR for RGB.

    Note:
        The cover_hash in the track_info of songs from a custom source, is
        stored as a value of 'id'.
    """
    cache_file_path = os.path.join(TEMP_FOLDER, f"{cover_hash}.json")

    # Returns the default embed color
    if not os.path.exists(cache_file_path):
        return {'url': None, 'dominant_rgb': DEFAULT_EMBED_COLOR}

    with open(cache_file_path, 'r') as cache_file:
        cached_data: dict = json.load(cache_file)
        cover_url = cached_data.get('url')
        dominant_rgb = cached_data.get('dominant_rgb')

        return {'url': cover_url, 'dominant_rgb': dominant_rgb}


async def generate_info_embed(
    url: str,
    title: str,
    album: str,
    artists: list,
    cover_url: Optional[str],
    dominant_rgb: tuple[int, int, int],
) -> discord.Embed:
    """
    Generate a Discord Embed with track information.

    Args:
        url (str): The URL of the track.
        title (str): The title of the track.
        album (str): The album name.
        artists (list): List of artist names.
        cover_url Optional[str]: The URL of the cover image, or None if not available.
        dominant_rgb (tuple[int, int, int]): The dominant RGB color of the cover.

    Returns:
        discord.Embed: A Discord Embed object containing formatted track information.
    """
    artist_string = ', '.join(artists)

    embed = discord.Embed(
        title=title,
        url=url,
        description=f"By {artist_string}",
        color=discord.Colour.from_rgb(*dominant_rgb)
    ).add_field(
        name="Part of the album",
        value=album,
        inline=True
    ).set_author(
        name="Now playing"
    ).set_thumbnail(
        url=cover_url
    )

    return embed


async def fetch_audio_stream(url: str) -> Path:
    """
    Fetch an audio file from a URL and cache it locally.

    This function checks for a cached version of the file before fetching.
    If the cached file exists and is not expired, it returns the cached file path.
    Otherwise, it downloads the file, caches it, and returns the path.

    Args:
        url (str): The URL of the audio file to fetch.

    Returns:
        Path: The path to the cached audio file.

    Raises:
        Exception: If the audio fetch fails.
    """
    cache_path = get_cache_path(url.encode('utf-8'))

    # If the file exists and is not expired, return it
    if cache_path.is_file():
        if time() - cache_path.stat().st_mtime < CACHE_EXPIRY:
            return cache_path
        else:
            cache_path.unlink()  # Remove expired file

    # Fetch the audio file from the URL asynchronously
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f'Failed to fetch audio: {response.status}')
            audio_data = await response.read()

    # Write the fetched audio to the cache file
    with cache_path.open('wb') as cache_file:
        cache_file.write(audio_data)

    cleanup_cache()

    return cache_path
