import os
import logging
import config
from config import COMMANDS_FOLDER

import discord
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
logger = logging.getLogger(__name__)


# Init bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f"{bot.user} is running !")


for filepath in COMMANDS_FOLDER.rglob('*.py'):
    relative_path = filepath.relative_to(COMMANDS_FOLDER).with_suffix('')
    module_name = f"commands.{relative_path.as_posix().replace('/', '.')}"

    logging.info(f'Loading {module_name}')
    bot.load_extension(module_name)


bot.run(BOT_TOKEN)
