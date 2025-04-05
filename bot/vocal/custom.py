import aiofiles
from aiohttp_client_cache import CachedSession, SQLiteBackend
import cgi
import discord
from dotenv import load_dotenv
import json
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from bot.utils import get_accent_color, get_display_name_from_query
from config import CACHE_EXPIRY, TEMP_FOLDER, DEFAULT_EMBED_COLOR


logger = logging.getLogger(__name__)
load_dotenv()
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")


async def upload_cover(cover_bytes: bytes) -> dict:
    """Upload a song art cover to imgur and return the URL and cover hash."""
    # Step 1: Hash the cover bytes
    cover_hash = hashlib.md5(cover_bytes).hexdigest()

    # Step 2: Check if the hash already exists in the cache
    cache_file_path: Path = TEMP_FOLDER / f"{cover_hash}.json"
    if cache_file_path.is_file():
        # Step 3: If cached, read and return the stored dict
        with open(cache_file_path, "r") as cache_file:
            cached_data: dict = json.load(cache_file)
            return {
                "url": cached_data.get("url"),
                "cover_hash": cover_hash,
                "dominant_rgb": cached_data.get("dominant_rgb"),
            }

    # Step 4: If not cached, upload to Imgur (If IMGUR_CLIENT_ID id valid)
    if not IMGUR_CLIENT_ID:
        return {}

    url = "https://api.imgur.com/3/upload"
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}

    async with CachedSession(
        follow_redirects=True,
        cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
    ) as session:
        data = {
            "image": cover_bytes,
            "type": "file",  # Imgur expects the file type
        }
        async with session.post(url, headers=headers, data=data) as response:
            if response.status != 200:
                logging.error(f"Upload failed with status {response.status}")
                return

            json_response = await response.json()
            image_url = json_response["data"]["link"]

            # Step 5: Cache the uploaded image URL and
            # the dominant RGB. Prevent additional future requests
            dominant_rgb = get_accent_color(cover_bytes)
            with open(cache_file_path, "w") as cache_file:
                json.dump({"url": image_url, "dominant_rgb": dominant_rgb}, cache_file)

            return {
                "url": image_url,
                "cover_hash": cover_hash,
                "dominant_rgb": dominant_rgb,
            }


async def get_cover_data_from_file(filename: str) -> dict[str, discord.Colour]:
    """Retrieve cover art data for a given JSON file.
    Returns a dict with the 'url' and 'dominant_rgb' of the latter."""
    cache_file_path = Path(TEMP_FOLDER) / f"{filename}.json"

    # Returns the default embed color
    if not cache_file_path.exists():
        return {
            "url": "",
            "dominant_rgb": discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
        }

    with open(cache_file_path, "r") as cache_file:
        cached_data: dict = json.load(cache_file)
        cover_url = cached_data.get("url")
        dominant_rgb = cached_data.get("dominant_rgb")

        return {
            "url": cover_url,
            "dominant_rgb": discord.Colour.from_rgb(*dominant_rgb),
        }


async def generate_info_embed(
    url: str,
    title: str,
    album: str,
    artists: list,
    cover_url: Optional[str],
    dominant_rgb: tuple[int, int, int],
) -> discord.Embed:
    """
    Generate a Discord Embed with track information."""
    artist_string = ", ".join(artists)

    embed = discord.Embed(
        title=title,
        url=url,
        description=f"By {artist_string}",
        color=discord.Colour.from_rgb(*dominant_rgb),
    )
    embed.add_field(name="Part of the album", value=album, inline=True)
    embed.set_author(name="Now playing")
    embed.set_thumbnail(url=cover_url)

    return embed


async def fetch_audio_stream(
    bot: discord.Bot, url: Optional[str] = None
) -> Optional[Path]:
    """Fetch an audio file from a URL and cache it locally."""
    async with CachedSession(
        follow_redirects=True,
        cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
    ) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch audio: {response.status}")
            audio_data = await response.read()
            cd_header = response.headers.get("Content-Disposition", "")
            _, params = cgi.parse_header(cd_header)

            # Get the file name from headers
            if f := (params.get("filename*") or params.get("filename")):
                filename = unquote(f).replace("UTF-8''", "")
            else:
                filename = get_display_name_from_query(url)

    # Write the fetched audio to the cache file
    cache_path = Path(f"{TEMP_FOLDER}/{filename}")
    if not cache_path.is_file():
        async with aiofiles.open(cache_path, "wb") as cache_file:
            await cache_file.write(audio_data)

    return cache_path
