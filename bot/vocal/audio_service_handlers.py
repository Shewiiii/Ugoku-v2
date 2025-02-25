import re
from urllib.parse import unquote
from typing import Optional
import asyncio


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
    offset: int = 0,
    artist_mode: bool = False,
    album: bool = False
) -> None:
    """
    Handles playback of Spotify tracks.
    This function searches for Spotify tracks based on the given query,
    adds them to the session's queue, and starts playback if not already playing.
    """
    if len(query) >= 250:
        await ctx.respond('Query too long!')
        return

    if artist_mode:
        response = await asyncio.to_thread(
            ctx.bot.spotify.sessions.sp.search, query, type='artist', limit=1
        )
        # Get the artist URL and get the tracks from it
        tracks_info = await ctx.bot.spotify.get_tracks(
            response['artists']['items'][0]['external_urls']['spotify'],
            offset=offset,
            album=album
        ) if response else None
    else:
        tracks_info = await ctx.bot.spotify.get_tracks(query, offset=offset, album=album)

    if not tracks_info:
        content = 'Track not found!'
        await (interaction.edit_original_message(content=content) if interaction else ctx.edit(content=content))
        return

    await session.add_to_queue(ctx, tracks_info, 'spotify/deezer', interaction)


def get_display_name_from_query(query: str) -> str:
    """Extracts a display name from the query URL if no title is found."""
    match = re.search(r'(?:.+/)([^#?]+)', query)
    return unquote(match.group(1)) if match else 'Custom track'


async def play_custom(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    """Handles playback of other URLs."""
    # Request and cache
    try:
        audio_path = await fetch_audio_stream(query)
    except Exception as e:
        await ctx.edit(content=f'Error fetching audio: {str(e)}')
        return

    # Extract the metadata
    def first_item(items, default='?'):
        return items[0] if items else default

    # Convert to list to sync with ID3 tags
    metadata = get_metadata(audio_path)
    titles = list(metadata.get('title', []))
    artists = list(metadata.get('artist', []))
    albums = list(metadata.get('album', []))
    print(titles, artists, albums)

    artist = first_item(artists, default='?')
    album = first_item(albums, default='?')
    has_title = len(titles) > 0

    if has_title:
        title = titles[0]
        display_name = f'{artist} - {title}'
    else:
        display_name = get_display_name_from_query(query)
        title = display_name

    # Extract the cover art
    cover_bytes = extract_cover_art(audio_path)
    if cover_bytes and (cover_dict := await upload_cover(cover_bytes)):
        cover_url = cover_dict.get('url')
        id = cover_dict.get('cover_hash')
        dominant_rgb = cover_dict.get('dominant_rgb')
    else:
        cover_url = id = None
        dominant_rgb = DEFAULT_EMBED_COLOR

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

    await session.add_to_queue(ctx, [track_info], 'custom')


async def play_onsei(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    """
    Handles playback of Onsei audio tracks.
    This function fetches track information from Onsei API, processes the data,
    and adds the tracks to the session's queue.
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
    for track_title, track_api in tracks.items():
        stream_url = track_api['media_stream_url']

        # Explicit parameters are necessary to not give the same embed to all tracks
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
            'duration': round(track_api['duration']),
            'url': stream_url,
            'embed': embed,
            'id': work_id
        }

        tracks_info.append(track_info)
    await session.add_to_queue(ctx, tracks_info, 'onsei')


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

    await session.add_to_queue(ctx, [tracks_info], 'youtube', interaction)
