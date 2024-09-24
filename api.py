import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

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
    toggle_loop
)
from bot.vocal.types import ActiveGuildInfo

"""FastAPI-based API for managing Discord bot audio playback and authentication.

This module provides a FastAPI application that interfaces with a Discord bot,
allowing for control of audio playback across multiple Discord servers (guilds).
It also handles user authentication via Discord OAuth2.

The API includes endpoints for:
- User authentication and session management
- Audio playback control (play, pause, seek, skip, etc.)
- Real-time updates on active voice connections

Attributes:
    app (FastAPI): The main FastAPI application instance.
    bot (Optional[Bot]): The Discord bot instance (set externally).
    active_servers (List[Dict[str, Any]]): List of currently active voice connections.
    connected_clients (Set[asyncio.Queue]): Set of connected SSE clients.
    user_sessions (Dict[str, Dict[str, Any]]): Dictionary of active user sessions.

Functions:
    startup_event(): Loads saved sessions on application startup.
    load_sessions(): Loads user sessions from a JSON file.
    save_sessions(): Saves current user sessions to a JSON file.
    exchange_code(code: str): Exchanges an OAuth2 code for access tokens.
    get_user_details(access_token: str, token_type: str): Fetches user details from Discord API.
    create_session(user_details: Dict[str, Any]): Creates a new user session.
    notify_clients(): Notifies all connected SSE clients of server updates.
    update_active_servers(guild_infos: List[ActiveGuildInfo]): Updates the list of active servers.

API Endpoints:
    GET /: Simple ping endpoint.
    GET /play/stream: SSE endpoint for real-time server updates.
    GET /auth/discord: Handles Discord OAuth2 callback.
    POST /auth/logout: Logs out a user.
    GET /api/user: Retrieves authenticated user details.
    POST /auth/refresh: Refreshes an authentication token.
    POST /api/playback/toggle: Toggles playback for a specific guild.
    POST /api/playback/seek: Seeks to a specific position in the current track.
    POST /api/playback/loop: Toggles loop mode for a guild.
    POST /api/playback/skip: Skips the current track for a guild.
    POST /api/playback/shuffle: Toggles shuffle mode for a guild.
    POST /api/playback/previous: Plays the previous track for a guild.
    POST /api/playback/volume: Sets the volume for a guild.

Note:
    This API requires environment variables for Discord OAuth2 credentials
    and allowed CORS origins. It also depends on an external Discord bot
    instance to be set.
"""


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()
config = uvicorn.Config(app, loop="asyncio")
server = uvicorn.Server(config)
active_servers: List[Dict[str, Any]] = []
connected_clients: Set[asyncio.Queue] = set()

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
    allow_origins=os.getenv("ALLOWED_ORIGINS"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

user_sessions: Dict[str, Dict[str, Any]] = {}
security = HTTPBearer()


class SeekRequest(BaseModel):
    """Request model for seeking to a position in a track."""
    guildId: str
    position: int


class LoopRequest(BaseModel):
    """Request model for toggling loop mode."""
    guildId: str
    mode: str


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
async def startup_event():
    global user_sessions
    user_sessions = load_sessions()
    logger.info(f"Loaded {len(user_sessions)} sessions from file")


def load_sessions():
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


def save_sessions():
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


def exchange_code(code: str) -> Dict[str, Any]:
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


def get_user_details(access_token: str, token_type: str) -> Dict[str, Any]:
    """Fetch user details from Discord API.

    Args:
        access_token (str): The OAuth2 access token.
        token_type (str): The type of token (usually "Bearer").

    Returns:
        Dict[str, Any]: User details from Discord.
    """
    headers = {"Authorization": f"{token_type} {access_token}"}
    return requests.get(f"{API_ENDPOINT}/users/@me", headers=headers).json()


def create_session(user_details: Dict[str, Any]) -> tuple[str, str, datetime]:
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


async def notify_clients():
    """Notify all connected SSE clients of server updates."""
    logger.info(f"Notifying {len(connected_clients)} clients of server update")
    for queue in connected_clients:
        await queue.put(json.dumps({
            "message": "Success!" if active_servers else "No active voice connections",
            "server_time": datetime.now().isoformat(),
            "guilds": active_servers
        }))
    logger.info("All clients notified")


async def update_active_servers(guild_infos: List[ActiveGuildInfo]):
    """Update the list of active servers and notify clients.

    Args:
        guild_infos (List[ActiveGuildInfo]): List of active guild information.
    """
    global active_servers
    active_servers = guild_infos
    logger.info("Active servers updated.")
    await notify_clients()


@app.get("/")
async def ping():
    """Simple ping endpoint. :Elaina_Magic:

    Returns:
        dict: A dictionary with a "pong" message.
    """
    return {"message": "pong"}


@app.get("/play/stream")
async def stream_active_servers(request: Request):
    """SSE endpoint for real-time server updates.

    Args:
        request (Request): The incoming request object.

    Returns:
        EventSourceResponse: An SSE response for real-time updates.
    """
    if bot is None:
        return {"message": "Bot is not online"}

    async def event_generator():
        queue = asyncio.Queue()
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


@app.get("/auth/discord")
async def auth_discord(code: str = Query(...)):
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
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
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
async def get_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get authenticated user details.

    Args:
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: User details.

    Raises:
        HTTPException: If the token is invalid or expired.
    """
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    return {"message": "Success!", "user": session["user_details"]}


@app.post("/auth/refresh")
async def refresh(credentials: HTTPAuthorizationCredentials = Depends(security)):
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
async def toggle_playback(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Toggle playback for a specific guild.

    Args:
        request (Request): The incoming request object.
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A success message.

    Raises:
        HTTPException: If the token is invalid, expired, or if the bot is not connected.
    """
    data = await request.json()
    guild_id = data.get("guildId")
    logger.info(f"Received playback toggle request for guild {guild_id}")
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    if bot is None:
        raise HTTPException(status_code=400, detail="Bot is not online")

    guild = bot.get_guild(int(guild_id))
    if guild is None:
        raise HTTPException(status_code=400, detail="Guild not found")

    voice_client = guild.voice_client
    if voice_client is None:
        raise HTTPException(
            status_code=400,
            detail="Bot is not connected to a voice channel"
        )

    if voice_client.is_playing():
        voice_client.pause()
    else:
        voice_client.resume()

    return {"message": "Success!"}


@app.post("/api/playback/seek")
async def seek_playback_route(request: SeekRequest):
    """Seek to a specific position in the current track.

    Args:
        request (SeekRequest): The seek request containing guild ID and position.

    Returns:
        dict: A success status.

    Raises:
        HTTPException: If seeking fails.
    """
    success = await seek_playback(request.guildId, request.position)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to seek. The guild might not be playing any audio."
        )


@app.post("/api/playback/loop")
async def toggle_loop_route(
    request: LoopRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Toggle loop mode for a guild.

    Args:
        request (LoopRequest): The loop request containing guild ID and mode.
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A success status.

    Raises:
        HTTPException: If toggling loop fails or if the token is invalid.
    """
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    success = await toggle_loop(request.guildId, request.mode)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to toggle loop. The guild might not be playing any audio."
        )


@app.post("/api/playback/skip")
async def skip_track_route(
    request: SkipRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Skip the current track for a guild.

    Args:
        request (SkipRequest): The skip request containing guild ID.
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A success status and message.

    Raises:
        HTTPException: If skipping fails or if the token is invalid.
    """
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    success = await skip_track(request.guildId)
    if success:
        return {"status": "success", "message": "Skipped track!"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to skip track. The guild might not be playing any audio."
        )


@app.post("/api/playback/shuffle")
async def shuffle_playback(
    request: ShuffleRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Toggle shuffle mode for a guild.

    Args:
        request (ShuffleRequest): The shuffle request containing guild ID and active status.
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A success status.

    Raises:
        HTTPException: If shuffling fails or if the token is invalid.
    """
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    success = await shuffle_queue(request.guildId, request.isActive)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to shuffle. The guild might not be playing any audio."
        )


@app.post("/api/playback/previous")
async def play_previous_track_route(
    request: PreviousRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Play the previous track for a guild.

    Args:
        request (PreviousRequest): The previous track request containing guild ID.
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A success status.

    Raises:
        HTTPException: If playing the previous track fails or if the token is invalid.
    """
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    success = await previous_track(request.guildId)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to play previous track. The guild might not be playing any audio."
        )


@app.post("/api/playback/volume")
async def set_volume_route(
    request: VolumeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Set the volume for a guild.

    Args:
        request (VolumeRequest): The volume request containing guild ID and volume level.
        credentials (HTTPAuthorizationCredentials): The user's credentials.

    Returns:
        dict: A success status.

    Raises:
        HTTPException: If setting the volume fails or if the token is invalid.
    """
    token = credentials.credentials
    session = user_sessions.get(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    success = await set_volume(request.guildId, request.volume)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to set volume. The guild might not be playing any audio."
        )
