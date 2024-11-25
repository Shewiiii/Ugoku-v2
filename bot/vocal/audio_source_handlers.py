import re
from urllib.parse import unquote
from typing import Optional


import discord
from aiohttp.client_exceptions import ClientResponseError
from yt_dlp.utils import DownloadError

from bot.vocal.custom import fetch_audio_stream, upload_cover, generate_info_embed
from bot.vocal.server_session import ServerSession
from bot.utils import get_metadata, extract_cover_art, extract_number, get_dominant_rgb_from_url
from bot.vocal.session_manager import onsei
from config import DEFAULT_EMBED_COLOR


async def play_spotify(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession,
    interaction: Optional[discord.Interaction] = None,
    requested_source: str = 'Spotify',
    offset: int = 0
) -> None:
    """
    Handles playback of Spotify tracks.

    This function searches for Spotify tracks based on the given query,
    adds them to the session's queue, and starts playback if not already playing.

    Args:
        ctx (discord.ApplicationContext): The Discord application context.
        query (str): The Spotify track or playlist URL, or search query.
        session (ServerSession): The current server's audio session.
        interaction: A discord interaction if that method has been triggered by one.
        requested_source: The streaming service that should be used (Spotify or Deezer).
    """
    tracks_info = await ctx.bot.spotify.get_tracks(query, offset=offset)

    if not tracks_info:
        if interaction:
            interaction.edit_original_message(content='Track not found!')
        else:
            await ctx.edit(content='Track not found!')
        return

    await session.add_to_queue(
        ctx,
        tracks_info,
        requested_source,
        interaction
    )


def get_display_name_from_query(query: str) -> str:
    """
    Extracts a display name from the query URL if no title is found.

    Args:
        query (str): The URL query string.

    Returns:
        str: The extracted display name or 'Custom track' if extraction fails.
    """

    match = re.search(r'(?:.+/)([^#?]+)', query)
    return unquote(match.group(1)) if match else 'Custom track'


async def play_custom(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    """
    Handles playback of custom audio sources.

    This function fetches audio from a custom URL, extracts metadata,
    processes cover art, and adds the track to the session's queue.

    Args:
        ctx (discord.ApplicationContext): The Discord application context.
        query (str): The URL of the custom audio source.
        session (ServerSession): The current server's audio session.
    """
    # Request and cache
    try:
        audio_path = await fetch_audio_stream(query)
    except Exception as e:
        await ctx.edit(content=f'Error fetching audio: {str(e)}')
        return

    # Extract the metadata
    metadata = get_metadata(audio_path)
    # Idk why title and album are lists :elaina_huh:
    titles = metadata.get('title')
    artists = metadata.get('artist', ['?'])
    display_name = (
        f'{artists[0]} - {titles[0]}' if titles
        else get_display_name_from_query(query)
    )
    title = titles[0] if titles else display_name
    albums = metadata.get('album')
    album = albums[0] if albums else '?'

    # Extract the cover art
    cover_bytes = extract_cover_art(audio_path)
    if cover_bytes and (cover_dict := await upload_cover(cover_bytes)):
        cover_url = cover_dict.get('url')
        id = cover_dict.get('cover_hash')
        dominant_rgb = cover_dict.get('dominant_rgb')
    else:
        cover_url = id = None
        dominant_rgb = DEFAULT_EMBED_COLOR

    # Prepare the track

    def embed():
        return generate_info_embed(
            url=query,
            title=title,
            album=album,
            artists=artists,
            cover_url=cover_url,
            dominant_rgb=dominant_rgb
        )

    track_info = {
        'display_name': display_name,
        'title': title,
        'artist': artists,
        'album': album,
        'cover': cover_url,
        # 'duration': ???
        'source': audio_path,
        'url': query,
        'embed': embed,
        'id': id
    }

    await session.add_to_queue(ctx, [track_info], source='Custom')


async def play_onsei(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    """
    Handles playback of Onsei audio tracks.

    This function fetches track information from Onsei API, processes the data,
    and adds the tracks to the session's queue.

    Args:
        ctx (discord.ApplicationContext): The Discord application context.
        query (str): The Onsei work ID or URL.
        session (ServerSession): The current server's audio session.
    """
    work_id = extract_number(query)

    # API requests
    try:
        tracks_api: dict = await onsei.get_tracks_api(work_id)
        work_api: dict = await onsei.get_work_api(work_id)
        cover_url = onsei.get_cover(work_id)
        dominant_rgb = await get_dominant_rgb_from_url(cover_url)
    except ClientResponseError as e:
        if e.status == 404:
            await ctx.edit(content='No onsei has been found!')
            return
        else:
            await ctx.edit(content=f'An error occurred: {e.message}')
            return

    # Grab the data needed
    tracks = onsei.get_all_tracks(tracks_api)
    work_title = work_api.get('title')
    artists = [i['name'] for i in work_api['vas']]

    # Prepare the tracks
    tracks_info = []
    for track_title, stream_url in tracks.items():
        def embed(track_title=track_title, stream_url=stream_url):
            return generate_info_embed(
                url=stream_url,
                title=track_title,
                album=work_title,
                artists=artists,
                cover_url=cover_url,
                dominant_rgb=dominant_rgb
            )

        track_info = {
            'display_name': track_title,
            'title': track_title,
            'artist': artists,
            'source': stream_url,
            'album': work_title,
            'cover': cover_url,
            # 'duration': duration (can get it using aone api)
            'url': stream_url,
            'embed': embed,
            'id': work_id
        }

        tracks_info.append(track_info)
    await session.add_to_queue(ctx, tracks_info, source='Custom')


async def play_youtube(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession,
    interaction: Optional[discord.Interaction] = None
) -> None:
    if interaction:
        edit = interaction.edit_original_message
    else:
        edit = ctx.edit

    try:
        tracks_info = await ctx.bot.youtube.get_track_info(query)
    except DownloadError as e:
        await edit(content='Download failed: Ugoku has been detected as a bot.')
        return

    if not tracks_info:
        await edit(content='No video has been found!')
        return

    await session.add_to_queue(ctx, [tracks_info], 'Youtube', interaction)
