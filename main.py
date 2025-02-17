from bot.vocal.spotify import SpotifySessions, Spotify
from bot.vocal.youtube import Youtube
from config import (
    COMMANDS_FOLDER,
    SPOTIFY_API_ENABLED,
    CHATBOT_ENABLED,
    PINECONE_INDEX_NAME,
    DEEZER_ENABLED,
    TEMP_FOLDER
)
import discord
import os
import logging
import asyncio
from dotenv import load_dotenv
if CHATBOT_ENABLED:
    from bot.chatbot.vector_recall import memory
if DEEZER_ENABLED:
    from bot.vocal.deezer import Deezer_

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')


# Init bot
intents = discord.Intents.default()
intents.message_content = True
loop = asyncio.get_event_loop()
bot = discord.Bot(intents=intents, loop=loop)


@bot.event
async def on_ready() -> None:
    logging.info(f"{bot.user} is running !")

    # Temp folder
    TEMP_FOLDER.mkdir(parents=True, exist_ok=True)

    # Rich presence
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="/help for usage !"
        )
    )

    # Music instances
    if SPOTIFY_API_ENABLED:
        spotify_sessions = SpotifySessions()
        spotify = Spotify(spotify_sessions)
        await spotify_sessions.init_spotify()
        bot.spotify = spotify
        if DEEZER_ENABLED:
            deezer = Deezer_()
            await deezer.init_deezer()
            bot.deezer = deezer
    bot.youtube = Youtube()

    # Chatbot instances
    if CHATBOT_ENABLED:
        await memory.init_pinecone(PINECONE_INDEX_NAME)

for filepath in COMMANDS_FOLDER.rglob('*.py'):
    relative_path = filepath.relative_to(COMMANDS_FOLDER).with_suffix('')
    module_name = f"commands.{relative_path.as_posix().replace('/', '.')}"
    logging.info(f'Loading {module_name}')
    bot.load_extension(module_name)


bot.run(BOT_TOKEN)
