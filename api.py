from datetime import datetime, timedelta
from fastapi import FastAPI, Query, Depends, HTTPException, Request, Body
from fastapi.params import Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from discord import Bot, VoiceClient
from sse_starlette.sse import EventSourceResponse
import uvicorn
import os
import json
from dotenv import load_dotenv
import secrets
import requests
import asyncio
from typing import Optional, Dict, Any, List, Set, Dict
from pydantic import BaseModel
from bot.vocal import seek_playback, toggle_loop, skip_track, shuffle_queue, previous_track, set_volume

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
config = uvicorn.Config(app, loop="asyncio")
server = uvicorn.Server(config)
active_servers: List[Dict[str, Any]] = []
connected_clients: Set[asyncio.Queue] = set()

load_dotenv()

bot : Optional[Bot] = None

# Discord OAuth2 Credentials
API_ENDPOINT = "https://discord.com/api/v10"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/discord"

IMAGE_BASE_URL = "https://cdn.discordapp.com"

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

user_sessions: Dict[str, Dict[str, Any]] = {}
active_servers: List[Dict[str, Any]] = []
connected_clients: Set[asyncio.Queue] = set()


security = HTTPBearer()

class SeekRequest(BaseModel):
    guildId: str
    position: int

class LoopRequest(BaseModel):
    guildId: str
    mode: str

class SkipRequest(BaseModel):
    guildId: str

class ShuffleRequest(BaseModel):
    guildId: str
    isActive: bool

class PreviousRequest(BaseModel):
    guildId: str

class VolumeRequest(BaseModel):
    guildId: str
    volume: int

@app.on_event("startup")
async def startup_event():
    global user_sessions
    user_sessions = load_sessions()
    logger.info(f"Loaded {len(user_sessions)} sessions from file")

def load_sessions():
    try:
        with open("sessions.json", "r") as f:
            sessions = json.load(f)
        # Convert expiration strings back to datetime objects
        for session in sessions.values():
            session['expiration'] = datetime.fromisoformat(session['expiration'])
        return sessions
    except FileNotFoundError:
        return {}

def save_sessions():
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
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post(
        f"{API_ENDPOINT}/oauth2/token",
        data=data,
        headers=headers,
        auth=(CLIENT_ID, CLIENT_SECRET) if CLIENT_ID and CLIENT_SECRET else None
    )
    response.raise_for_status()
    return response.json()

def get_user_details(access_token: str, token_type: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"{token_type} {access_token}"
    }
    return requests.get(f"{API_ENDPOINT}/users/@me", headers=headers).json()

def create_session(user_details: Dict[str, Any]) -> tuple[str, str, datetime]:
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
    logger.info(f"Notifying {len(connected_clients)} clients of server update")
    for queue in connected_clients:
        await queue.put(json.dumps({
            "message": "Success!" if active_servers else "No active voice connections",
            "server_time": datetime.now().isoformat(),
            "guilds": active_servers
        }))
    logger.info("All clients notified")

async def update_active_servers(guild_infos: List[Dict[str, Any]]):
    global active_servers
    active_servers = guild_infos
    logger.info(f"Active servers updated.")
    await notify_clients()

@app.get("/")
async def ping():
    return {"message": "pong"}

@app.get("/play/stream")
async def stream_active_servers(request: Request):
    if bot is None:
        return { "message": "Bot is not online" }

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
    try:
        response = exchange_code(code)
        access_token = response["access_token"]
        token_type = response["token_type"]
        user_details = get_user_details(access_token, token_type)

        user_id = user_details["id"]
        session_token, _, _ = create_session(user_details)

        user_details["avatar"] = f"{IMAGE_BASE_URL}/avatars/{user_id}/{user_details['avatar']}.png" if user_details["avatar"] else None

        return RedirectResponse(
            url=f"http://localhost:5173/auth-callback?token={session_token}"
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.post("/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token in user_sessions:
        del user_sessions[token]
        save_sessions()
        return {"message": "Logged out successfully!"}
    raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/api/user")
async def get_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
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
    refresh_token = credentials.credentials
    for token, session in user_sessions.items():
        if session["refresh_token"] == refresh_token:
            new_token, new_refresh_token, new_expiration = create_session(session["user_details"])
            del user_sessions[token]
            save_sessions()
            return JSONResponse({
                "access_token": new_token,
                "refresh_token": new_refresh_token,
                "expires_at": new_expiration.isoformat()
            })

    raise HTTPException(status_code=401, detail="Invalid refresh token")

@app.post("/api/playback/toggle")
async def toggle_playback(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        raise HTTPException(status_code=400, detail="Bot is not connected to a voice channel")

    if voice_client.is_playing():
        voice_client.pause()
    else:
        voice_client.resume()

    return {"message": "Success!"}

@app.post("/api/playback/seek")
async def seek_playback_route(request: SeekRequest):
    success = await seek_playback(request.guildId, request.position)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Failed to seek. The guild might not be playing any audio.")

@app.post("/api/playback/loop")
async def toggle_loop_route(request: LoopRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        raise HTTPException(status_code=400, detail="Failed to toggle loop. The guild might not be playing any audio.")

@app.post('/api/playback/skip')
async def skip_track_route(request: SkipRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        raise HTTPException(status_code=400, detail="Failed to skip track. The guild might not be playing any audio.")

@app.post("/api/playback/shuffle")
async def shuffle_playback(request: ShuffleRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        raise HTTPException(status_code=400, detail="Failed to shuffle. The guild might not be playing any audio.")

@app.post("/api/playback/previous")
async def play_previous_track_route(request: PreviousRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        raise HTTPException(status_code=400, detail="Failed to play previous track. The guild might not be playing any audio.")
@app.post("/api/playback/volume")
async def set_volume_route(request: VolumeRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        raise HTTPException(status_code=400, detail="Failed to set volume. The guild might not be playing any audio.")