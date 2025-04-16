from aiohttp_client_cache import CachedSession, SQLiteBackend
from config import CACHE_EXPIRY
import httpx
import os
from typing import Optional


YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


async def get_playlist_video_ids(playlist_id: str) -> list[str]:
    base_url = "https://www.googleapis.com/youtube/v3/playlistItems"
    video_ids = []
    next_page_token = ""

    if not YOUTUBE_API_KEY:
        raise ValueError("No Youtube API key provided")

    for _ in range(2):
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "pageToken": next_page_token,
            "key": YOUTUBE_API_KEY,
        }
        # Do no cache here: to refresh playlist on change
        async with httpx.AsyncClient(http2=True) as client:
            response = await client.get(base_url, params=params)
            data = response.json()
        video_ids.extend(
            item["contentDetails"]["videoId"] for item in data.get("items", [])
        )
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids


async def get_videos_info(video_ids: list[str]) -> list[Optional[dict]]:
    base_url = "https://www.googleapis.com/youtube/v3/videos"
    video_details = []

    if not YOUTUBE_API_KEY:
        raise ValueError("No Youtube API key provided")

    for i in range(0, len(video_ids), 50):
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids[i : i + 50]),
            "key": YOUTUBE_API_KEY,
        }
        async with CachedSession(
            follow_redirects=True,
            cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
        ) as session:
            response = await session.get(base_url, params=params)
            data = await response.json()
        video_details.extend(data.get("items", []))

    return video_details
