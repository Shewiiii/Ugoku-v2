import os
import logging
from config import COMMANDS_FOLDER, SPOTIFY_ENABLED

import discord
from dotenv import load_dotenv


if SPOTIFY_ENABLED:
    from bot.spotify import init_spotify

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
DEV_TOKEN = os.getenv('DEV_TOKEN')
logger = logging.getLogger(__name__)


# Init bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    logging.info(f"{bot.user} is running !")
    if SPOTIFY_ENABLED:
        await init_spotify(bot)


for filepath in COMMANDS_FOLDER.rglob('*.py'):
    relative_path = filepath.relative_to(COMMANDS_FOLDER).with_suffix('')
    module_name = f"commands.{relative_path.as_posix().replace('/', '.')}"

    logging.info(f'Loading {module_name}')
    bot.load_extension(module_name)


bot.run(DEV_TOKEN)
