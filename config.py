from pathlib import Path
import logging

# If you don't have Spotify Premium, you can't disable Spotify features here
SPOTIFY_ENABLED = True

# SETTINGS
COMMANDS_FOLDER = Path('./commands')
TEMP_FOLDER = Path('.') / 'temp'
CACHE_SIZE = 100  # Cache size limit (in number of files) for custom sources
CACHE_EXPIRY = 2592000  # Cache expiry time (in seconds) for custom sources
AUTO_LEAVE_DURATION = 300 # Duration before killing an audio session (in seconds)

# Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()
    ]
)
