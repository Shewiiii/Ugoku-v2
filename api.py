from fastapi import FastAPI, Query
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from discord import Bot
import os
from dotenv import load_dotenv

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

bot: Bot = None
user_details_dict = {}

@app.get("/")
async def ping():
    return { "message": "pong" }

@app.get("/play")
async def play():
    return { "message": str(bot.voice_clients) }

@app.get("/auth/discord")
async def auth_discord(code: str = Query(...)):
    response = exchange_code(code)

    access_token = response.get("access_token")
    token_type = response.get("token_type")

    try:
        user_details = get_user_details(access_token, token_type)

        # Generate a temporary token
        temp_token = secrets.token_urlsafe(32)
        user_details["temp_token"] = temp_token

        # Add the avatar URL
        user_details["avatar"] = f"https://cdn.discordapp.com/avatars/{user_details['id']}/{user_details['avatar']}.png"

        user_details_dict[temp_token] = user_details

        return RedirectResponse(url=f"http://localhost:5173/auth-callback?token={temp_token}")
    except Exception as e:
        return JSONResponse(content={ "error": str(e) }, status_code=400)
    
@app.get("/api/user")
async def get_user(token: str = Query(...)):
    if token in user_details_dict:
        return { "message": "Success!", "user": user_details_dict[token] }
    else:
        return { "message": "Invalid token" }
    