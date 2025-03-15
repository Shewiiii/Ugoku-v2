from aiohttp_client_cache import CachedSession, SQLiteBackend
import aiofiles
from pathlib import Path
from PIL import Image
import asyncio
import shutil
import logging
import re
import os

from discord import ApplicationContext
from bs4 import BeautifulSoup
import imageio.v3

from bot.search import link_grabber
from bot.utils import sanitize_filename
from config import TEMP_FOLDER


def get_link(string: str) -> str:
    return re.findall(link_grabber, string)[-1][0]


async def convert_to_gif(sticker_count: int, path: Path) -> None:
    for i in range(sticker_count):
        png_file = path / f"{i + 1}.png"
        gif_file = path / f"{i + 1}.gif"

        # Read the APNG and save as GIF
        with imageio.get_reader(png_file) as reader:
            first_frame_meta = reader.get_meta_data(0)
            duration = first_frame_meta.get("duration", 100)

            with imageio.get_writer(gif_file, duration=duration, disposal=2) as writer:
                for frame in reader:
                    rgba_frame = Image.fromarray(frame).convert("RGBA")
                    writer.append_data(rgba_frame)

        # Remove the original PNG file
        os.remove(png_file)


async def fetch_sticker_image(
    session: CachedSession, link: str, file_path: Path
) -> None:
    async with session.get(link) as response:
        response.raise_for_status()
        sticker_image = await response.read()
        async with aiofiles.open(file_path, "wb") as png_file:
            await png_file.write(sticker_image)


async def get_stickerpack(link: str, ctx: ApplicationContext | None = None) -> str:
    try:
        async with CachedSession(cache=SQLiteBackend("cache")) as session:
            async with session.get(link) as response:
                response.raise_for_status()
                raw = BeautifulSoup(await response.text(), features="html.parser")
                # Pack name
                pack_name = (
                    raw.find("p", {"data-test": "sticker-name-title"})
                    or raw.find("p", {"data-test": "emoji-name-title"})
                ).get_text(strip=True)

    except Exception as e:
        logging.error(f"Error fetching or parsing the page: {e}")
        raise e

    # Remove unwanted characters from the pack name
    pack_name = sanitize_filename(pack_name)

    # Setup the folders
    folder_path = TEMP_FOLDER / pack_name
    folder_path.mkdir(parents=True, exist_ok=True)
    zip_file = TEMP_FOLDER / f"{pack_name}.zip"
    if zip_file.is_file():
        return zip_file

    # Get HTML elements of the stickers
    stickers = raw.find_all("li", {"class": "FnStickerPreviewItem"})
    if not stickers:
        raise ValueError("No stickers found on the page.")

    # Get sticker type and count
    sticker_class = stickers[0].get("class", [""])
    sticker_type = sticker_class[-1] if len(sticker_class) >= 3 else "emote"
    sticker_count = len(stickers)

    # Save the stickers
    logging.info(f"Downloading {pack_name}, Sticker count: {sticker_count}.")
    if ctx:
        await ctx.edit(content="Saving the stickers...")

    async with CachedSession(cache=SQLiteBackend("cache")) as session:
        tasks = []
        for i, sticker in enumerate(stickers):
            preview_link = get_link(sticker["data-preview"])
            file_path = folder_path / f"{i + 1}.png"
            tasks.append(fetch_sticker_image(session, preview_link, file_path))

        await asyncio.gather(*tasks)

    # Convert APNGs to GIFs if needed
    if sticker_type in ["animation-sticker", "popup-sticker"]:
        if ctx:
            await ctx.edit(content="Converting APNG files to GIF...")
        await convert_to_gif(sticker_count, folder_path)

    # Archive the folder
    if ctx:
        await ctx.edit(content="Archiving...")
    archive_file = shutil.make_archive(folder_path, "zip", folder_path)

    # Remove the original folder
    shutil.rmtree(folder_path)

    return archive_file
