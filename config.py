from pathlib import Path
import logging

# If you don't have Spotify Premium, you can't disable Spotify features here
SPOTIFY_ENABLED = True

# Settings
TEMP_SONGS_PATH = Path('.') / 'temp' / 'vc_songs'

# Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()
    ]
)