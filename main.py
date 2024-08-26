import os
import logging
import config

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


for filename in os.listdir('./commands'):
    if filename.endswith('.py'):
        logging.info(f'Loading {filename}')
        bot.load_extension(f'commands.{filename[:-3]}')


bot.run(BOT_TOKEN)
