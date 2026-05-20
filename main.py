import asyncio
import logging
import os
import discord

from config import (
    COMMANDS_FOLDER,
    SPOTIFY_API_ENABLED,
    GEMINI_ENABLED,
    PINECONE_INDEX_NAME,
    DEEZER_ENABLED,
    TEMP_FOLDER,
)
from bot.misc.quickstart_view import QuickstartView
from bot.utils import cleanup_cache
from bot.vocal.spotify import SpotifySessions, Spotify
from bot.http_client import init_http_session, close_http_session




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


@bot.event
async def on_ready() -> None:
    # Cache
    TEMP_FOLDER.mkdir(parents=True, exist_ok=True)
    await init_http_session()

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
            tasks.append(bot.deezer.setup(create_refresh_task=True))

    if GEMINI_ENABLED:
        tasks.append(memory.init_pinecone(PINECONE_INDEX_NAME))
    await asyncio.gather(*tasks, return_exceptions=True)

    # Party !
    logging.info(f"{bot.user} is running !")


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    channel = guild.system_channel
    if channel is None:
        for c in guild.text_channels:
            if c.permissions_for(guild.me).send_messages:
                channel = c
                break
    if channel is not None:
        quickstart_view = QuickstartView(timeout=None)
        await quickstart_view.display(respond_func=channel.send)


@bot.event
async def on_close() -> None:
    await close_http_session()


async def clean_cache_task() -> None:
    while True:
        await cleanup_cache()
        await asyncio.sleep(60)


if __name__ == "__main__":
    for filepath in COMMANDS_FOLDER.rglob("*.py"):
        relative_path = filepath.relative_to(COMMANDS_FOLDER).with_suffix("")
        module_name = f"commands.{relative_path.as_posix().replace('/', '.')}"
        logging.info(f"Loading {module_name}")
        bot.load_extension(module_name)

    bot.run(BOT_TOKEN)
