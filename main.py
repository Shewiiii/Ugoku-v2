import os
import logging
import asyncio
from config import COMMANDS_FOLDER
import api

import discord
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
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
    print(f"{bot.user} is running !")

@bot.event
async def on_voice_state_update(member, before, after):
    logger.info(f"Voice state update detected for {member.name}")
    logger.info(f"Before: {before.channel}, After: {after.channel}")
    if before.channel != after.channel:
        logger.info("Channel change detected, updating active servers")
        await update_active_servers()
    else:
        logger.info("No channel change detected, ignoring")

async def update_active_servers():
    active_guilds = []
    for vc in bot.voice_clients:
        guild = vc.guild
        guild_info = {
            "id": guild.id,
            "name": guild.name,
            "icon": guild.icon.url if guild.icon else None
        }
        active_guilds.append(guild_info)

    logger.info(f"Updating active servers. Current voice clients: {active_guilds}")
    await api.update_active_servers(active_guilds)

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
