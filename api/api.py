import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Union
from typing_extensions import TypedDict

import requests
import uvicorn
from discord import Bot
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from bot.vocal.audio_controls import (
    previous_track,
    seek_playback,
    set_volume,
    shuffle_queue,
    skip_track,
    toggle_loop, toggle_playback
)
from bot.vocal.types import (
    ActiveGuildInfo,
    ActiveGuildInfo,
    LoopMode
)


"""FastAPI-based API for managing Discord bot audio playback and authentication.

This module provides a FastAPI application that interfaces with a Discord bot,
allowing for control of audio playback across multiple Discord servers (guilds).
It also handles user authentication via Discord OAuth2 and provides real-time
updates on active voice connections.

Key Features:
- User authentication and session management using Discord OAuth2
- Audio playback control (play, pause, seek, skip, loop, shuffle, etc.)
- Real-time updates on active voice connections using Server-Sent Events (SSE)
- Secure session handling with token refresh capabilities

Main Components:
- FastAPI application with various endpoints for authentication and playback control
- Session management system with JSON file persistence
- Server-Sent Events (SSE) for real-time updates
- Integration with Discord API for OAuth2 and user details
- Custom exception handling for various error scenarios

API Endpoints:
- GET /: Simple ping endpoint
- GET /play/stream: SSE endpoint for real-time server updates
- GET /auth/discord: Handles Discord OAuth2 callback
- POST /auth/logout: Logs out a user
- GET /api/user: Retrieves authenticated user details
- POST /auth/refresh: Refreshes an authentication token
- POST /api/playback/*: Various endpoints for playback control (toggle, seek, loop, skip, etc.)

The module uses environment variables for configuration, including Discord OAuth2 credentials
and allowed CORS origins. It depends on an external Discord bot instance to be set.

Note: This module should be used in conjunction with appropriate Discord bot implementation
and requires proper setup of environment variables and Discord Developer Application settings.
"""

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()
config = uvicorn.Config(app, loop="asyncio")
server = uvicorn.Server(config)
active_servers: List[ActiveGuildInfo] = []
connected_clients: Set[asyncio.Queue[str]] = set()

load_dotenv()

bot: Optional[Bot] = None

# Discord OAuth2 Credentials
API_ENDPOINT = "https://discord.com/api/v10"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
BASE_REDIRECT_URI = os.getenv("REDIRECT_URI")
REDIRECT_URI = f"{BASE_REDIRECT_URI}/auth/discord"
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
REDIRECT_RESPONSE = f"{BASE_REDIRECT_URI}/auth-callback"

IMAGE_BASE_URL = "https://cdn.discordapp.com"

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserDetails(TypedDict):
    """User details from Discord OAuth

    Attributes:
        id (str): User ID.
        username (str): User's username.
        avatar (Optional[str]): User's avatar hash.
        discriminator (str): User's discriminator.
        public_flags (int): Public flags.
        flags (int): Flags.
        banner (Optional[str]): User's banner hash.
        banner_color (Optional[str]): Banner color.
        accent_color (Optional[int]): Accent color.
        locale (str): User's locale.
        mfa_enabled (bool): Whether MFA is enabled.
        premium_type (int): Premium type.
    """
    id: str
    username: str
    avatar: Optional[str]
    discriminator: str
    public_flags: int
    flags: int
    banner: Optional[str]
    banner_color: Optional[str]
    accent_color: Optional[int]
    locale: str
    mfa_enabled: bool
    premium_type: int


class UserSession(TypedDict):
    """User session data.

    Attributes:
        user_details (UserDetails): User details from Discord.
        refresh_token (str): Refresh token for the session.
        expiration (datetime): Expiration time for the session.
    """
    user_details: UserDetails
    refresh_token: str
    expiration: datetime


user_sessions: Dict[str, UserSession] = {}
security = HTTPBearer()

# ========== Custom exceptions ============


class InvalidTokenError(HTTPException):
    """Exception raised for invalid session tokens."""

    def __init__(self):
        super().__init__(status_code=401, detail="Invalid token")


class ExpiredTokenError(HTTPException):
    """Exception raised for expired session tokens."""

    def __init__(self):
        super().__init__(status_code=401, detail="Token expired")


class BotOfflineError(HTTPException):
    """Exception raised when the bot is not connected."""

    def __init__(self):
        super().__init__(status_code=503, detail="Bot is not online")


class GuildNotFoundError(HTTPException):
    """Exception raised when a guild is not found."""

    def __init__(self):
        super().__init__(status_code=400, detail="Guild not found")


class VoiceClientError(HTTPException):
    """Exception raised when the bot is not connected to a voice channel."""

    def __init__(self):
        super().__init__(status_code=400, detail="Bot is not connected to a voice channel")


class PlaybackOperationError(HTTPException):
    def __init__(self, operation: str):
        super().__init__(
            status_code=400,
            detail=(f"Failed to {operation}. "
                    "The guild might not be playing any audio.")
        )

# ======= Request models =========

# Base model for guild-related requests


class GuildRequest(BaseModel):
    guildId: str

# Dependency for session validation


async def get_valid_session(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserSession:
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise InvalidTokenError()

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise ExpiredTokenError()

    return session

# Wrapper function for playback operations


async def execute_playback_operation(operation_func, guild_id: str, *args):
    if bot is None:
        raise BotOfflineError()

    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise GuildNotFoundError()

    voice_client = guild.voice_client
    if voice_client is None:
        raise VoiceClientError()

    success = await operation_func(guild_id, *args)
    if not success:
        raise PlaybackOperationError(operation_func.__name__)

    return {"status": "success"}


class SeekRequest(BaseModel):
    """Request model for seeking to a position in a track."""
    guildId: str
    position: int


class LoopRequest(BaseModel):
    """Request model for toggling loop mode."""
    guildId: str
    mode: LoopMode


class SkipRequest(BaseModel):
    """Request model for skipping the current track."""
    guildId: str


class ShuffleRequest(BaseModel):
    """Request model for toggling shuffle mode."""
    guildId: str
    isActive: bool


class PreviousRequest(BaseModel):
    """Request model for playing the previous track."""
    guildId: str


class VolumeRequest(BaseModel):
    """Request model for setting the volume."""
    guildId: str
    volume: int


@app.on_event("startup")
async def startup_event() -> None:
    global user_sessions
    user_sessions = load_sessions()
    logger.info(f"Loaded {len(user_sessions)} sessions from file")


def load_sessions() -> Dict[str, UserSession]:
    """Load user sessions from a JSON file.

    Returns:
        dict: A dictionary of user sessions, with session tokens as keys.
    """
    try:
        with open("sessions.json", "r") as f:
            sessions = json.load(f)
        # Convert expiration strings back to datetime objects
        for session in sessions.values():
            session['expiration'] = datetime.fromisoformat(
                session['expiration'])
        return sessions
    except FileNotFoundError:
        return {}


def save_sessions() -> None:
    """Save current user sessions to a JSON file."""
    sessions_to_save = {
        token: {
            **session,
            'expiration': session['expiration'].isoformat()
        }
        for token, session in user_sessions.items()
    }
    with open("sessions.json", "w") as f:
        json.dump(sessions_to_save, f)


class OAuthResponse(TypedDict):
    """Response from Discord OAuth2 token exchange.

    Attributes:
        access_token (str): OAuth2 access token.
        token_type (str): Token type (usually "Bearer").
        expires_in (int): Token expiration time.
        refresh_token (str): Refresh token.
        scope (str): OAuth2 scope.
    """
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str


def exchange_code(code: str) -> OAuthResponse:
    """Exchange OAuth2 code for access token.

    Args:
        code (str): The OAuth2 code received from Discord.

    Returns:
        Dict[str, Any]: The response from Discord containing access token and other details.

    Raises:
        requests.HTTPError: If the request to Discord API fails.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(
        f"{API_ENDPOINT}/oauth2/token",
        data=data,
        headers=headers,
        auth=(CLIENT_ID, CLIENT_SECRET) if CLIENT_ID and CLIENT_SECRET else None
    )
    response.raise_for_status()
    return response.json()


def get_user_details(access_token: str, token_type: str) -> UserDetails:
    """Fetch user details from Discord API.

    Args:
        access_token (str): The OAuth2 access token.
        token_type (str): The type of token (usually "Bearer").

    Returns:
        Dict[str, Any]: User details from Discord.
    """
    headers = {"Authorization": f"{token_type} {access_token}"}
    return requests.get(f"{API_ENDPOINT}/users/@me", headers=headers).json()


def create_session(user_details: UserDetails) -> tuple[str, str, datetime]:
    """Create a new user session.

    Args:
        user_details (Dict[str, Any]): User information from Discord.

    Returns:
        tuple[str, str, datetime]: A tuple containing session token, refresh token, and expiration time.
    """
    session_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    expiration = datetime.now() + timedelta(days=7)

    user_sessions[session_token] = {
        "user_details": user_details,
        "refresh_token": refresh_token,
        "expiration": expiration
    }

    # Save the session to the json file
    save_sessions()

    return session_token, refresh_token, expiration


@app.get("/")
async def ping() -> Dict[str, str]:
    """Simple ping endpoint. :Elaina_Magic:

    Returns:
        dict: A dictionary with a "pong" message.
    """
    return {"message": "pong"}


@app.get("/play/stream")
async def stream_active_servers(request: Request) -> EventSourceResponse:
    """SSE endpoint for real-time server updates.

    Args:
        request (Request): The incoming request object.

    Returns:
        EventSourceResponse: An SSE response for real-time updates.

    Raises:
        HTTPException: If the bot is not online.
    """
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot is not online")

    async def event_generator():
        queue: asyncio.Queue[str] = asyncio.Queue()
        connected_clients.add(queue)
        try:
            # Send initial update
            initial_data = json.dumps({
                "message": "Success!" if active_servers else "No active voice connections",
                "guilds": active_servers
            })
            yield {
                "event": "message",
                "data": initial_data
            }
            while True:
                if await request.is_disconnected():
                    break
                data = await queue.get()
                yield {
                    "event": "message",
                    "data": data
                }
        finally:
            connected_clients.remove(queue)

    return EventSourceResponse(event_generator())


@app.get("/auth/discord", response_model=None)
async def auth_discord(
    code: str = Query(...)
) -> Union[RedirectResponse, JSONResponse]:
    """Handle Discord OAuth2 callback.

    Args:
        code (str): The OAuth2 code received from Discord.

    Returns:
        RedirectResponse: A redirect to the frontend with the session token.

    Raises:
        HTTPException: If there's an error in the OAuth2 process.
    """
    try:
        response = exchange_code(code)
        access_token = response["access_token"]
        token_type = response["token_type"]
        user_details = get_user_details(access_token, token_type)

        user_id = user_details["id"]
        session_token, _, _ = create_session(user_details)

        user_details["avatar"] = (
            f"{IMAGE_BASE_URL}/avatars/{user_id}/{user_details['avatar']}.png"
            if user_details["avatar"] else None
        )

        return RedirectResponse(
            url=f"{REDIRECT_RESPONSE}?token={session_token}"
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)


@app.post("/auth/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, str]:
    """Log out a user by invalidating their session.

    Args:
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A message confirming successful logout.

    Raises:
        HTTPException: If the token is invalid.
    """
    token = credentials.credentials
    if token in user_sessions:
        del user_sessions[token]
        save_sessions()
        return {"message": "Logged out successfully!"}
    raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/user")
async def get_user(
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, Union[str, UserDetails]]:
    """Get authenticated user details."""
    return {"message": "Success!", "user": session["user_details"]}


@app.post("/auth/refresh")
async def refresh(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> JSONResponse:
    """Refresh an authentication token.

    Args:
        credentials (HTTPAuthorizationCredentials): The user's refresh token.

    Returns:
        JSONResponse: New access token, refresh token, and expiration time.

    Raises:
        HTTPException: If the refresh token is invalid.
    """
    refresh_token = credentials.credentials
    for token, session in user_sessions.items():
        if session["refresh_token"] == refresh_token:
            new_token, new_refresh_token, new_expiration = create_session(
                session["user_details"])
            del user_sessions[token]
            save_sessions()
            return JSONResponse({
                "access_token": new_token,
                "refresh_token": new_refresh_token,
                "expires_at": new_expiration.isoformat()
            })

    raise HTTPException(status_code=401, detail="Invalid refresh token")


@app.post("/api/playback/toggle")
async def toggle_playback_route(
    request: GuildRequest,
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Toggle playback for a specific guild."""
    return await execute_playback_operation(
        toggle_playback,
        request.guildId
    )


@app.post("/api/playback/seek")
async def seek_playback_route(
        request: SeekRequest,
        session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Seek to a specific position in the current track."""
    return await execute_playback_operation(
        seek_playback,
        request.guildId,
        request.position
    )


@app.post("/api/playback/loop")
async def toggle_loop_route(
    request: LoopRequest,
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Toggle loop mode for a guild."""
    return await execute_playback_operation(
        toggle_loop,
        request.guildId,
        request.mode
    )


@app.post("/api/playback/skip")
async def skip_track_route(
    request: SkipRequest,
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Skip the current track for a guild."""
    return await execute_playback_operation(
        skip_track,
        request.guildId
    )


@app.post("/api/playback/shuffle")
async def shuffle_playback(
    request: ShuffleRequest,
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Toggle shuffle mode for a guild."""
    return await execute_playback_operation(
        shuffle_queue,
        request.guildId,
        request.isActive
    )


@app.post("/api/playback/previous")
async def play_previous_track_route(
    request: PreviousRequest,
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Play the previous track for a guild."""
    return await execute_playback_operation(
        previous_track,
        request.guildId
    )


@app.post("/api/playback/volume")
async def set_volume_route(
    request: VolumeRequest,
    session: UserSession = Depends(get_valid_session)
) -> Dict[str, str]:
    """Set the volume for a guild."""
    return await execute_playback_operation(
        set_volume,
        request.guildId,
        request.volume
    )
