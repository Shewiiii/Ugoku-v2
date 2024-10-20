import os
import logging
import asyncio
from config import COMMANDS_FOLDER, SPOTIFY_ENABLED
import api

import discord
from dotenv import load_dotenv

if SPOTIFY_ENABLED:
    from bot.vocal.spotify import SpotifySessions, Spotify

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
# DEV_TOKEN = os.getenv('DEV_TOKEN')
logger = logging.getLogger(__name__)


# Init bot
intents = discord.Intents.default()
intents.message_content = True
loop = asyncio.get_event_loop()
bot = discord.Bot(intents=intents, loop=loop)
server = api.server
api.bot = bot


@bot.event 
async def on_ready() -> None:
    logging.info(f"{bot.user} is running !")
    if SPOTIFY_ENABLED:
        spotify_sessions = SpotifySessions()
        await spotify_sessions.init_spotify()
        spotify = Spotify(spotify_sessions)
        bot.spotify = spotify
        bot.downloading = False

for filepath in COMMANDS_FOLDER.rglob('*.py'):
    relative_path = filepath.relative_to(COMMANDS_FOLDER).with_suffix('')
    module_name = f"commands.{relative_path.as_posix().replace('/', '.')}"

    logging.info(f'Loading {module_name}')
    bot.load_extension(module_name)

async def start() -> None:
    await asyncio.gather(bot.start(BOT_TOKEN), server.serve())

try:
    loop.run_until_complete(start())
finally:
    if not bot.is_closed():
        loop.run_until_complete(bot.close())
    if server.started:
        loop.run_until_complete(server.shutdown())
