from dotenv import load_dotenv

load_dotenv()

import asyncio  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402

import discord  # noqa: E402

from bot.vocal.spotify import SpotifySessions, Spotify  # noqa: E402
from bot.vocal.youtube import Youtube  # noqa: E402
from bot.utils import cleanup_cache  # noqa: E402
from config import (  # noqa: E402
    COMMANDS_FOLDER,
    SPOTIFY_API_ENABLED,
    GEMINI_ENABLED,
    PINECONE_INDEX_NAME,
    DEEZER_ENABLED,
    TEMP_FOLDER,
)


if GEMINI_ENABLED:
    from bot.chatbot.vector_recall import memory
if DEEZER_ENABLED:
    from deezer_decryption.api import Deezer

BOT_TOKEN = os.getenv("BOT_TOKEN")


# Init bot
intents = discord.Intents.default()
intents.message_content = True
loop = asyncio.get_event_loop()
bot = discord.Bot(intents=intents, loop=loop)

for filepath in COMMANDS_FOLDER.rglob("*.py"):
    relative_path = filepath.relative_to(COMMANDS_FOLDER).with_suffix("")
    module_name = f"commands.{relative_path.as_posix().replace('/', '.')}"
    logging.info(f"Loading {module_name}")
    bot.load_extension(module_name)


@bot.event
async def on_ready() -> None:
    # Cache
    TEMP_FOLDER.mkdir(parents=True, exist_ok=True)

    tasks = [
        bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening, name="/help for usage !"
            )
        ),
        clean_cache_task(),
    ]
    if SPOTIFY_API_ENABLED:
        spotify_sessions = SpotifySessions()
        spotify = Spotify(spotify_sessions)
        tasks.append(spotify_sessions.init_spotify())
        bot.spotify = spotify
        if DEEZER_ENABLED:
            bot.deezer = Deezer()
            tasks.append(bot.deezer.setup())
    bot.youtube = Youtube()
    if GEMINI_ENABLED:
        tasks.append(memory.init_pinecone(PINECONE_INDEX_NAME))
    await asyncio.gather(*tasks, return_exceptions=True)

    # Party !
    logging.info(f"{bot.user} is running !")


async def clean_cache_task() -> None:
    while True:
        await cleanup_cache()
        await asyncio.sleep(60)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
