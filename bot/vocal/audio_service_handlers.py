import asyncio
import logging
from typing import Optional


from aiohttp.client_exceptions import ClientResponseError, InvalidUrlClientError
import discord
from spotipy.exceptions import SpotifyException
from yt_dlp.utils import DownloadError

from bot.vocal.custom import fetch_audio_stream, upload_cover
from bot.vocal.server_session import ServerSession
from bot.utils import get_metadata, extract_cover_art, extract_number, respond, edit
from bot.search import is_url
from bot.vocal.session_manager import onsei
from bot.vocal.track_dataclass import Track
from config import DEFAULT_EMBED_COLOR


async def play_spotify(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession,
    interaction: Optional[discord.Interaction] = None,
    offset: int = 0,
    artist_mode: bool = False,
    album: bool = False,
    play_next: bool = False,
    defer_task: Optional[asyncio.Task] = None,
) -> None:
    """
    Handles playback of Spotify tracks.
    This function searches for Spotify tracks based on the given query,
    adds them to the session's queue, and starts playback if not already playing.
    """
    response_params = [ctx, "", interaction, defer_task]
    if len(query) >= 250:
        response_params[1] = "Query too long!"
        await respond(*response_params)
        return

    try:
        if artist_mode:
            response = await ctx.bot.spotify.search(query, type="artist", limit=1)
            # Get the artist URL and get the tracks from it
            tracks_info = (
                await ctx.bot.spotify.get_tracks(
                    offset=offset, album=album, id_=response[0]["id"], type="artist"
                )
                if response
                else None
            )
        else:
            tracks_info = await ctx.bot.spotify.get_tracks(
                query, offset=offset, album=album
            )

        if not tracks_info:
            response_params[1] = "Track not found!"
            await edit(*response_params)
            return

    except SpotifyException as e:
        if e.http_status == 404:
            response_params[1] = (
                "Content not found! Perhaps you are trying to play a private playlist?"
            )
            await edit(*response_params)
        else:
            logging.error(e)
        return

    await session.add_to_queue(
        ctx,
        tracks_info,
        play_next=play_next,
        show_wrong_track_embed=not is_url(query, ["open.spotify.com"]),
        user_query=query,  # For the prompt in the "wrong track" embed
    )


async def play_custom(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession,
    play_next: bool = False,
    defer_task: Optional[asyncio.Task] = None,
) -> None:
    """Handles playback of other URLs."""
    response_params = [ctx, "", None, defer_task]
    # Request and cache
    try:
        audio_path = await fetch_audio_stream(query)
    except (InvalidUrlClientError, ValueError):
        response_params[1] = "Invalid URL !"
        await respond(*response_params)
        return
    except Exception as e:
        await defer_task
        await ctx.respond(f"Oops! Something went wrong.\n-# {repr(e)}")
        raise e

    if not audio_path:
        if defer_task:
            await defer_task
        await ctx.respond("oi (Canceled)")
        return

    # Convert to list to sync with ID3 tags
    metadata = get_metadata(audio_path)
    titles = list(metadata.get("title", "?"))
    artists = list(metadata.get("artist", "?"))
    albums = list(metadata.get("album", "?"))

    # Remove blank fields
    for field in titles, artists, albums:
        if not field[0].strip():
            field[0] = "?"

    # Extract the cover art
    cover_bytes = extract_cover_art(audio_path)
    cover_url = None
    dominant_rgb = DEFAULT_EMBED_COLOR
    if cover_bytes and (cover_dict := await upload_cover(cover_bytes)):
        cover_url = cover_dict.get("url")
        dominant_rgb = cover_dict.get("dominant_rgb")

    track = Track(
        service="custom",
        title=titles[0] if titles[0] != "?" else audio_path.name,
        album=albums[0],
        source_url=query,
        stream_source=audio_path,
        cover_url=cover_url or "",
        dominant_rgb=dominant_rgb,
    )
    track.set_artists(artists)
    track.create_embed()

    await session.add_to_queue(ctx, [track], play_next=play_next)


async def play_onsei(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession,
    play_next: bool = False,
    defer_task: Optional[asyncio.Task] = None,
) -> None:
    """
    Handles playback of Onsei audio tracks.
    This function fetches track information from Onsei API, processes the data,
    and adds the tracks to the session's queue.
    """
    response_params = [ctx, "", None, defer_task]
    work_id = extract_number(query)

    try:
        tracks: list[Track] = await onsei.get_all_tracks(work_id)
    except ClientResponseError as e:
        if e.status == 404:
            response_params[1] = "No onsei has been found !"
            await respond(*response_params)
            return
        else:
            response_params[1] = f"An error occurred.\n-# {repr(e)}"
            await respond(*response_params)
            return

    await session.add_to_queue(ctx, tracks, play_next=play_next)


async def play_ytdlp(
    ctx: discord.ApplicationContext,
    query: str,
    session: ServerSession,
    interaction: Optional[discord.Interaction] = None,
    play_next: bool = False,
    defer_task: Optional[asyncio.Task] = None,
) -> None:
    response_params = [ctx, "", interaction, defer_task]
    try:
        track: Track = await ctx.bot.ytdlp.get_track(query)
    except DownloadError:
        response_params[1] = "Download failed: Ugoku has been detected as a bot."
        await respond(*response_params)
        return

    if not track:
        response_params[1] = "No video has been found!"
        await respond(*response_params)
        return

    await session.add_to_queue(ctx, [track], play_next=play_next)
