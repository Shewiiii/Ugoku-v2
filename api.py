from datetime import datetime, timedelta
from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from discord import Bot
import os
from dotenv import load_dotenv
from typing import Optional

import secrets
import requests

app = FastAPI()
load_dotenv()

# Discord OAuth2 Credentials
API_ENDPOINT = "https://discord.com/api/v10"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/discord"

# Discord base URL
BASE_URL = "https://discord.com/api/v10"

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:5173"],  # List of allowed origins
    allow_credentials = True,
    allow_methods = ["*"],  # List of allowed methods
    allow_headers = ["*"],  # List of allowed headers
)

# Access Token Exchange
def exchange_code(code: str):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post(f"{API_ENDPOINT}/oauth2/token", data=data, headers=headers, auth=(CLIENT_ID, CLIENT_SECRET))
    response.raise_for_status()
    return response.json()

def get_user_details(access_token: str, token_type: str):
    headers = {
        "Authorization": f"{token_type} {access_token}"
    }
    user_details = requests.get(f"{BASE_URL}/users/@me", headers=headers).json()
    return user_details

config = uvicorn.Config(app, loop="asyncio")
server = uvicorn.Server(config)

bot: Optional[Bot] = None
user_sessions = {}

def create_session(user_details: dict):
    session_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    expiration = datetime.now() + timedelta(days=7)

    user_sessions[session_token] = {
        "user_details": user_details,
        "refresh_token": refresh_token,
        "expiration": expiration
    }

    return session_token, refresh_token, expiration

@app.get("/")
async def ping():
    return { "message": "pong" }

@app.get("/play")
async def play():
    return { "message": str(bot.voice_clients) }

security = HTTPBearer()

@app.get("/auth/discord")
async def auth_discord(code: str = Query(...)):
    response = exchange_code(code)

    access_token = response.get("access_token")
    token_type = response.get("token_type")

    try:
        user_details = get_user_details(access_token, token_type)

        # Generate a temporary token
        user_id = user_details["id"]
        session_token, refresh_token, expiration = create_session(user_details)

        # Add the avatar URL
        user_details["avatar"] = f"https://cdn.discordapp.com/avatars/{user_id}/{user_details['avatar']}.png"

        return RedirectResponse(
            url=f"http://localhost:5173/auth-callback?token={session_token}"
        )
    except Exception as e:
        return JSONResponse(content={ "error": str(e) }, status_code=400)

@app.post("/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token in user_sessions:
        del user_sessions[token]
        return { "message": "Logged out successfully!" }
    else:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/user")
async def get_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    session = user_sessions[token]

    if session["expiration"] < datetime.now():
        del user_sessions[token]
        raise HTTPException(status_code=401, detail="Token expired")

    if token in user_sessions:
        return { "message": "Success!", "user": session["user_details"] }
    else:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/auth/refresh")
async def refresh(credentials: HTTPAuthorizationCredentials = Depends(security)):
    refresh_token = credentials.credentials
    # Check if the refresh token is valid
    for token, session in user_sessions.items():
        if session["refresh_token"] == refresh_token:
            new_token, new_refresh_token, new_expiration = create_session(session["user_details"])
            # Delete the old session
            del user_sessions[token]
            return JSONResponse({
                "access_token": new_token,
                "refresh_token": new_refresh_token,
                "expires_at": new_expiration.isoformat()
            })

    raise HTTPException(status_code=401, detail="Invalid refresh token")
