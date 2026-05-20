from typing import Optional
from aiohttp_client_cache import CachedSession, SQLiteBackend
from config import CACHE_EXPIRY

session: Optional[CachedSession] = None


async def init_http_session() -> None:
    global session
    if session is None:
        session = CachedSession(
            follow_redirects=True,
            cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
        )


async def close_http_session() -> None:
    global session
    if session is not None:
        await session.close()
        session = None
