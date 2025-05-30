import asyncio
from aiohttp_client_cache import CachedSession, SQLiteBackend
from typing import Dict, Optional, Tuple, List, Union, Callable, TYPE_CHECKING
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
from urllib.parse import urlparse, parse_qs, unquote, urlencode, urlunparse, parse_qsl

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

from config import TEMP_FOLDER, CACHE_EXPIRY, CACHE_SIZE, PREMIUM_CHANNEL_ID
from bot.search import link_grabber, is_url

if TYPE_CHECKING:
    from bot.vocal.spotify import Spotify
    from bot.vocal.server_session import ServerSession


def extract_number(string: str) -> str:
    """
    Extract a natural number from a string.

    Args:
        string (str): The input string to extract a number from.

    Returns:
        Optional[str]: The extracted number as a string, or None if no number is found.
    """
    search = re.search(r"\d+", string)
    if not search:
        return ""

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
    if string.lower().startswith(("rj", "vj")):
        return True

    if re.fullmatch(r"/d{6}|/d{8}", string):
        return True

    return False


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing illegal characters."""
    # For Windows, common illegal characters include: / / : * ? " < > |
    # The following pattern keeps only alphanumeric characters, hyphens, underscores, and periods.
    sanitized_filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
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


def get_accent_color(image_bytes: bytes, threshold: int = 50) -> Tuple[int, int, int]:
    """
    Extract an accent color from an image.

    Args:
        image_bytes (bytes): The image data as bytes.
        threshold (int, optional): The color distance threshold. Defaults to 50.

    Returns:
        Tuple[int, int, int]: The RGB values of the extracted accent color.
    """
    image = Image.open(BytesIO(image_bytes))
    image = image.convert("RGB")  # Ensure image RGB

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

    accent_color = dominant_color
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


async def get_dominant_rgb_from_url(image_url: str) -> Tuple[int, int, int]:
    """Fetch an image from a URL and extract its accent color."""
    async with CachedSession(
        follow_redirects=True,
        cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
    ) as session:
        response = await session.get(image_url)
        response.raise_for_status()
        cover_bytes = await response.read()
        dominant_rgb = get_accent_color(cover_bytes)

    return dominant_rgb


# Cache functions for custom sources
def get_cache_path(string: str) -> Path:
    """
    Generate a cache file path for a given byte string.

    Args:
        string (bytes): The byte string to generate a cache path for.

    Returns:
        Path: The generated cache file path.
    """
    utf_8 = string.encode("utf-8")
    # Hash the URL to create a unique filename
    hash_digest = hashlib.md5(utf_8).hexdigest()
    return TEMP_FOLDER / f"{hash_digest}.cache"


async def cleanup_cache() -> None:
    """
    Clean up the cache directory by removing old and excess files.

    This function removes files that exceed the cache size limit and deletes expired files.
    """
    files = sorted(
        list(TEMP_FOLDER.glob("*.cache")) + list(TEMP_FOLDER.glob("*.json")),
        key=lambda f: f.stat().st_mtime,
    )

    remove_tasks = []

    # Remove files that exceed the cache size limit
    while len(files) > CACHE_SIZE:
        oldest_file = files.pop(0)
        logging.info(f"Removed {oldest_file} from cache")
        remove_tasks.append(asyncio.to_thread(os.remove, oldest_file))

    # Remove expired files
    current_time = time()
    for file in files:
        file_stat = await asyncio.to_thread(os.stat, file)
        if current_time - file_stat.st_mtime > CACHE_EXPIRY:
            logging.info(f"Removed {file} from cache")
            remove_tasks.append(asyncio.to_thread(os.remove, file))

    if remove_tasks:
        await asyncio.gather(*remove_tasks, return_exceptions=True)


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
        covers_data = audio_file.get("metadata_block_picture")
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


def get_metadata(file_path: Path) -> Dict[str, List[str]]:
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

    if isinstance(audio_file, (MP3, ID3, WAVE)):
        return {
            "title": audio_file.get("TIT2", ["?"]),
            "album": audio_file.get("TALB", ["?"]),
            "artist": audio_file.get("TPE1", ["?"]),
        }

    return {key: value for key, value in audio_file.items()}


async def tag_ogg_file(
    file_path: Union[Path, str],
    title: str = "",
    artist: str = "",
    album_cover_url: str = "",
    album: str = "",
    date: str = "",
    track_number: Union[int, str] = "",
    disc_number: Union[int, str] = "",
    width: int = 640,
    height: int = 640,
) -> None:
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
    audio["date"] = date
    audio["tracknumber"] = str(track_number)
    audio["discnumber"] = str(disc_number)

    # Create a Picture object
    picture = Picture()
    picture.type = 3  # Front Cover
    picture.width = width
    picture.height = height
    picture.mime = "image/jpeg"
    picture.desc = "Cover"

    # Fetch the album cover
    if album_cover_url:
        async with CachedSession(
            follow_redirects=True,
            cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
        ) as session:
            async with session.get(album_cover_url) as response:
                response.raise_for_status()
                cover_bytes = await response.read()
        picture.data = cover_bytes
        # Encode the picture data in base64
        picture_encoded = base64.b64encode(picture.write()).decode("ascii")
        # Add the picture to the metadata
        audio["metadata_block_picture"] = [picture_encoded]

    # Save the tags
    audio.save(file_path)
    logging.info(f"Tagged '{file_path}' successfully.")


def split_into_chunks(text: str, max_length: int = 1024) -> list:
    """Convert a string into a list of chunks with an adjustable size.
    Written with Gemini."""
    token_pattern = r"(^[ \t]*>.*(?:\n|$)|\[[^\]]*\]\((?:<[^>]*>|[^)<>\s]+)\)|[ \t]*```[^\n]*\n?|\S+|\s+)"
    try:
        tokens = re.findall(token_pattern, text, flags=re.MULTILINE)
    except Exception as e:
        logging.error(f"Regex error during tokenization: {e}")
        tokens = text.split()
        if not tokens:
            return []

    if not tokens:
        return []

    chunks = []
    current_chunk_tokens = []
    current_chunk_len = 0
    inside_code_block = False
    code_block_indent = ""
    code_block_opening_fence = ""

    def build_and_add_chunk(tokens_to_add, add_closing_fence=False):
        nonlocal chunks, current_chunk_tokens, current_chunk_len
        if not tokens_to_add:
            return

        chunk_str = "".join(tokens_to_add)

        if add_closing_fence and code_block_indent is not None:
            if not chunk_str.endswith("\n"):
                chunk_str += "\n"
            chunk_str += f"{code_block_indent}```"

        if chunk_str:
            if len(chunk_str) > max_length and len(tokens_to_add) > 1:
                logging.warning("Fence addition exceeded max_length, adjusting chunk.")
                last_token = tokens_to_add.pop()
                build_and_add_chunk(tokens_to_add, add_closing_fence)
                current_chunk_tokens = [last_token]
                current_chunk_len = len(last_token)
                return

            chunks.append(chunk_str)

    for i, tok in enumerate(tokens):
        tok_len = len(tok)

        fence_match = re.fullmatch(r"([ \t]*)```([^\n]*\n?)", tok)
        is_fence = fence_match is not None
        is_opening_fence = False
        is_closing_fence = False
        current_indent = ""

        if is_fence:
            current_indent = fence_match.group(1)
            if not inside_code_block:
                is_opening_fence = True
            elif current_indent == code_block_indent:
                is_closing_fence = True

        if current_chunk_len > 0 and current_chunk_len + tok_len > max_length:
            build_and_add_chunk(
                current_chunk_tokens, add_closing_fence=inside_code_block
            )

            current_chunk_tokens = []
            current_chunk_len = 0

            if inside_code_block and code_block_opening_fence:
                if len(code_block_opening_fence) <= max_length:
                    current_chunk_tokens.append(code_block_opening_fence)
                    current_chunk_len += len(code_block_opening_fence)
                else:
                    logging.warning(
                        f"Code block fence '{code_block_opening_fence.strip()}' alone exceeds max_length={max_length}."
                    )
                    current_chunk_tokens.append(code_block_opening_fence)
                    current_chunk_len += len(code_block_opening_fence)

            if tok_len > max_length and current_chunk_len == 0:
                current_chunk_tokens.append(tok)
                current_chunk_len += tok_len
                if is_opening_fence:
                    inside_code_block = True
                    code_block_indent = current_indent
                    code_block_opening_fence = tok
                elif is_closing_fence:
                    inside_code_block = False
                    code_block_indent = ""
                    code_block_opening_fence = ""
                continue
            elif current_chunk_len + tok_len > max_length:
                pass

            current_chunk_tokens.append(tok)
            current_chunk_len += tok_len

            if is_opening_fence:
                inside_code_block = True
                code_block_indent = current_indent
                code_block_opening_fence = tok
            elif is_closing_fence:
                inside_code_block = False
                code_block_indent = ""
                code_block_opening_fence = ""

        else:
            current_chunk_tokens.append(tok)
            current_chunk_len += tok_len

            if is_opening_fence:
                inside_code_block = True
                code_block_indent = current_indent
                code_block_opening_fence = tok
            elif is_closing_fence:
                inside_code_block = False
                code_block_indent = ""
                code_block_opening_fence = ""

    build_and_add_chunk(current_chunk_tokens, add_closing_fence=inside_code_block)

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
    if "youtube" in parsed_url.hostname:
        # For URLs like https://www.youtube.com/watch?v=VIDEO_ID
        if parsed_url.path == "/watch":
            query_params = parse_qs(parsed_url.query)
            return query_params.get("v", [None])[0]
        # For URLs like https://www.youtube.com/embed/VIDEO_ID
        elif "/embed/" in parsed_url.path:
            return parsed_url.path.split("/embed/")[1]
    elif "youtu.be" in parsed_url.hostname:
        # For URLs like https://youtu.be/VIDEO_ID
        return parsed_url.path.lstrip("/")
    else:
        return None


def send_response(
    respond: Callable[[str], discord.Message],
    message: str,
    guild_id: int,
    silent: bool = False,
) -> None:
    if silent:
        return
    try:
        asyncio.create_task(respond(message))
    except discord.errors.HTTPException:
        logging.error(
            f"Failed to send response for guild {guild_id}. Invalid Webhook Token."
        )
    except discord.errors.Forbidden:
        logging.error(f"Message sent in forbidden channel in {guild_id}")


async def upload(
    bot: discord.Bot, ctx: discord.ApplicationContext, file_path: Path, filename: str
) -> None:
    size = os.path.getsize(file_path)
    size_limit = ctx.guild.filesize_limit if ctx.guild else 26214400
    try:
        if size < size_limit:
            await ctx.edit(
                content="Here you go !", file=discord.File(file_path, filename=filename)
            )
            return
    except discord.errors.HTTPException as e:
        if e.status == 413:
            logging.error(f"File not uploaded: {file_path} is too big: {size} bytes")

    # Not uploaded, attempthing to upload in the premium channel
    if not PREMIUM_CHANNEL_ID:
        await ctx.edit(content="Upload failed: file too big.")
        return

    try:
        channel = await bot.fetch_channel(PREMIUM_CHANNEL_ID)
        message = await channel.send(
            content="-# File requested by a user",
            file=discord.File(file_path, filename=filename),
        )
    except (discord.errors.Forbidden, discord.errors.HTTPException):
        await ctx.edit(
            content="Upload failed: file too big and invalid premium channel."
        )
        return
    await ctx.edit(content=f"Here you go ! [Direct URL]({message.attachments[0].url})")


def vocal_connect_check(ctx: discord.ApplicationContext, respond_function) -> bool:
    """Check if the bot has enough permissions for the bot to function. Send a message otherwise.
    Return a bool accordingly."""
    if not ctx.author.voice:
        asyncio.create_task(
            respond_function(content="You are not in an active voice channel !")
        )
        return False

    if not ctx.channel.permissions_for(ctx.guild.me).send_messages:
        asyncio.create_task(
            respond_function(
                content="I don't have permission to send messages in this channel!"
            )
        )
        return False

    voice_perms = ctx.author.voice.channel.permissions_for(ctx.guild.me)
    if not (voice_perms.connect and voice_perms.speak):
        asyncio.create_task(
            respond_function(
                content="I don't have permission to speak in your voice channel!"
            )
        )
        return False

    return True


def vocal_action_check(
    session: "ServerSession",
    ctx: discord.ApplicationContext,
    respond_function,
    check_queue: bool = True,
    silent: bool = False,
) -> bool:
    """Checks if a user is allowed to execute an operation in vc.
    Update the last context if it is the case."""
    if not session:
        if not silent:
            asyncio.create_task(respond_function(content="No active session !"))
        return False

    if not ctx.author.voice or (
        session.voice_client
        and ctx.author.voice.channel != session.voice_client.channel
    ):
        if not silent:
            asyncio.create_task(
                respond_function(content="You are not in an active voice channel !")
            )
        return False

    if check_queue and not session.queue:
        if not silent:
            asyncio.create_task(respond_function(content="No songs in the queue !"))
        return False

    session.last_context = ctx
    return True


async def respond(
    ctx: discord.ApplicationContext,
    content: str,
    interaction: Optional[discord.Interaction] = None,
    defer_task: Optional[asyncio.Task] = None,
    view: Optional[discord.ui.View] = None,
) -> None:
    if defer_task and not defer_task.done():
        await defer_task
    respond = interaction.respond if interaction else ctx.respond
    if view:
        await respond(content=content, view=view)
    else:
        await respond(content=content)


async def edit(
    ctx: discord.ApplicationContext,
    content: str,
    interaction: Optional[discord.Interaction] = None,
    defer_task: Optional[asyncio.Task] = None,
    view: Optional[discord.ui.View] = None,
) -> None:
    if defer_task and not defer_task.done():
        await defer_task
    edit = interaction.edit_original_message if interaction else ctx.edit
    if view:
        await edit(content=content, view=view)
    else:
        await edit(content=content)


async def parse_message_url(
    bot: discord.Bot, message_url: str
) -> Optional[discord.Message]:
    """Get the message class from a message URL."""
    parsed_url = urlparse(message_url)
    path_components = parsed_url.path.split("/")
    # Server id, Channel id, Message id.
    channel = await bot.fetch_channel(path_components[-2])
    message = await channel.fetch_message(path_components[-1])
    return message


async def get_url_from_message(
    bot: Optional[discord.ApplicationContext] = None,
    message_url: Optional[str] = None,
    message: Optional[discord.Message] = None,
) -> Optional[str]:
    """Get an audio url from a Discord message."""
    url = None
    if not message:
        if not (bot and message_url):
            raise ValueError("Bot or message url not provided")
        message = await parse_message_url(bot, message_url)
    match = link_grabber.findall(message.content)
    if match:
        url = match[0][0]

    for attachment in message.attachments:
        if "audio" in attachment.content_type:
            url = attachment.url

    return url


def get_display_name_from_query(query: str) -> str:
    """Extracts a display name from the query URL if no title is found."""
    match = re.search(r"(?:.+/)([^#?]+)", query)
    return unquote(match.group(1)) if match else "Custom track"


def clean_url(url: str) -> str:
    """Clean Youtube and Souncloud urls."""
    parsed_url = urlparse(url)
    query_params = dict(parse_qsl(parsed_url.query))
    params_blacklist = [
        "si",
        "t",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "rco",
        "in_system_playlist",
        "ref",
        "feature",
        "src",
        "fbclid",
        "gclid",
        "msclkid",
        "sc_ichannel",
        "partner",
        "p",
        "referrer",
        "tt_medium",
        "tt_content",
        "igshid",
        "ig_rid",
        "ig_mid",
        "from_messages",
        "s",
        "cxt",
        "_openstat",
        "yclid",
        "gbraid",
        "wbraid",
        "context",
        "spm_id_from",
        "from_source",
        "msource",
        "bsource",
        "seid",
        "from",
        "refer_page",
        "watch_refer",
        "ref_member",
        "ref_video",
        "nrc",
        "share_source",
        "share_medium",
        "share_campaign",
        "share_id",
        "action_type",
    ]

    for param in params_blacklist:
        query_params.pop(param, None)
    new_query = urlencode(query_params)
    new_url = re.sub(r"&.*", "", urlunparse(parsed_url._replace(query=new_query)))
    new_url = new_url.replace("youtu.be/", "www.youtube.com/watch?v=")
    return new_url


async def process_song_query(
    query: str,
    bot: discord.Bot,
    url: Optional[bool] = None,
    get_title: bool = False,
    spotify: Optional["Spotify"] = None,
) -> str:
    """Lower the query and grab the URL in a Discord message if a message link is provided."""
    message_link = is_url(query, "discord.com", parts=["channels"])
    if url is None:
        url = is_url(query)

    if not url:
        # Normal text
        query = query.lower()
    elif message_link:
        # Message link -> Get the audio url
        query = await get_url_from_message(bot, query)

    if get_title and is_url(query, ["open.spotify.com"]):
        tracks = await spotify.get_tracks(query)
        if tracks:
            query = str(tracks[0])

    return query
