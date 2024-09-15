import re
from urllib.parse import unquote

import discord
from aiohttp.client_exceptions import ClientResponseError

from bot.vocal.custom import fetch_audio_stream, upload_cover, generate_info_embed
from bot.vocal.server_session import ServerSession
from bot.utils import get_metadata, extract_cover_art, extract_number, get_accent_color_from_url
from bot.vocal.session_manager import onsei
from config import DEFAULT_EMBED_COLOR


async def play_spotify(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
    tracks_info = await ctx.bot.spotify.get_tracks(user_input=query)

    if not tracks_info:
        await ctx.edit(content='Track not found!')
        return

    await session.add_to_queue(ctx, tracks_info, source='Spotify')


async def play_custom(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession
) -> None:
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
    albums = metadata.get('album')
    artists = metadata.get('artist', ['?'])

    display_name = (
        f'{artists[0]} - {titles[0]}' if titles
        else get_display_name_from_query(query)
    )

    # Extract the cover art
    cover_bytes: bytes | None = extract_cover_art(audio_path)
    if cover_bytes:
        cover_dict = await upload_cover(cover_bytes)
        cover_url = cover_dict.get('url')
        id = cover_dict.get('cover_hash')
        dominant_rgb = cover_dict.get('dominant_rgb')
    else:
        cover_url, id = None, None
        dominant_rgb = DEFAULT_EMBED_COLOR

    # Prepare the track
    def embed():
        return generate_info_embed(
            url=query,
            title=titles[0] if titles else display_name,
            album=albums[0] if albums else '?',
            artists=artists,
            cover_url=cover_url,
            dominant_rgb=dominant_rgb
        )

    track_info = {
        'display_name': display_name,
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
    work_id = extract_number(query)

    # API requests
    try:
        tracks_api: dict = await onsei.get_tracks_api(work_id)
        work_api: dict = await onsei.get_work_api(work_id)
        cover_url = onsei.get_cover(work_id)
        dominant_rgb = await get_accent_color_from_url(cover_url)
    except ClientResponseError as e:
        if e.status == 404:
            await ctx.edit(content='No onsei has been found!')
        else:
            await ctx.edit(content=f'An error occurred: {e.message}')

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
            # 'duration': duration
            'url': stream_url,
            'embed': embed,
            'id': work_id
        }

        tracks_info.append(track_info)
    await session.add_to_queue(ctx, tracks_info, source='Custom')


def get_display_name_from_query(query: str) -> str:
    """Extracts a display name from the query URL if no title is found."""
    match = re.search(r'(?:.+/)([^#?]+)', query)
    return unquote(match.group(1)) if match else 'Custom track'
