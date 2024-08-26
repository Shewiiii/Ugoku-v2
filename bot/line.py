import re
from pathlib import Path
import shutil
import logging
import os
from bot.exceptions import IncorrectURL
from discord import ApplicationContext

from bs4 import BeautifulSoup
import requests
from PIL import Image
import imageio.v3

from bot.search import link_grabber
from bot.utils import sanitize_filename
import config


logger = logging.getLogger(__name__)


# Setup the folders
output_path = Path('.') / 'temp'

sticker_path = output_path / 'stickers'
sticker_path.mkdir(parents=True, exist_ok=True)

archives_path = output_path / 'archives' / 'stickers'
archives_path.mkdir(parents=True, exist_ok=True)


def get_link(string: str) -> Path:
    return re.findall(
        link_grabber, string
    )[-1][0]


def convert_to_gif(sticker_count: int, path: Path) -> None:
    for i in range(sticker_count):
        png_file = path / f'{i + 1}.png'
        gif_file = path / f'{i + 1}.gif'

        # Read the APNG and save as GIF
        with imageio.get_reader(png_file) as reader:
            first_frame_meta = reader.get_meta_data(0)
            # Default duration of 100ms if not found
            duration = first_frame_meta.get('duration', 100)

            with imageio.get_writer(gif_file, duration=duration, disposal=2) as writer:
                for frame in reader:
                    rgba_frame = Image.fromarray(frame).convert("RGBA")
                    writer.append_data(rgba_frame)

        # Remove the original PNG file
        os.remove(png_file)


async def get_stickerpack(
    link: str,
    ctx: ApplicationContext | None = None
) -> str:
    """
    Get every sticker from a LINE Store page.

    Args:
        link: URL of a specific LINE sticker page.
        gif: If True, converts animated stickers to GIF if available.
        ctx: Optional context for asynchronous operations.

    Returns:
        The path to the created ZIP archive containing all stickers.
    """
    # Setup
    try:
        response = requests.get(link)
        response.raise_for_status()
        raw = BeautifulSoup(response.text, features="html.parser")

        # Pack name
        pack_name = raw.find(
            'p', {'data-test': 'sticker-name-title'}).get_text(strip=True)
    except Exception as e:
        logging.error(f"Error fetching or parsing the page: {e}")
        raise IncorrectURL from e

    # Remove unwanted characters from the pack name
    pack_name = sanitize_filename(pack_name)

    # Setup the folders
    folder_path = Path(sticker_path) / pack_name
    archive_path = Path(archives_path) / pack_name
    folder_path.mkdir(parents=True, exist_ok=True)

    # Get HTML elements of the stickers
    stickers = raw.find_all('li', {'class': 'FnStickerPreviewItem'})
    if not stickers:
        raise ValueError("No stickers found on the page.")

    # Get sticker type and count
    sticker_type = stickers[0].get('class', [''])[2]
    sticker_count = len(stickers)

    # Save the stickers
    logging.info(f'Downloading {pack_name}, Sticker count: {sticker_count}.')
    if ctx:
        await ctx.edit(content='Saving the stickers...')
    for i, sticker in enumerate(stickers):
        preview_link = get_link(sticker['data-preview'])
        sticker_image = requests.get(preview_link).content

        file_path = folder_path / f'{i + 1}.png'
        with open(file_path, 'wb') as png_file:
            png_file.write(sticker_image)

    # Convert APNGs to GIFs if needed
    if sticker_type in ['animation-sticker', 'popup-sticker']:
        if ctx:
            await ctx.edit(content='Converting APNG files to GIF...')
        convert_to_gif(sticker_count, folder_path)

    # Archive the folder
    archive_file = archive_path.with_suffix('.zip')
    if archive_file.is_file():
        archive_file.unlink()

    if ctx:
        await ctx.edit(content='Archiving...')
    shutil.make_archive(str(archive_path), 'zip', folder_path)
    shutil.rmtree(folder_path)

    return str(archive_file)


# if __name__ == "__main__":
#     get_stickerpack('https://store.line.me/stickershop/product/26625497/en')
