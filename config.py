from pathlib import Path
import logging

# If you don't have Spotify Premium, you can disable Spotify features here
# Please check ./commands/lyrics.py if that's the case
SPOTIFY_ENABLED = True

#  ===SETTINGS===
# Paths
COMMANDS_FOLDER = Path('./commands')
TEMP_FOLDER = Path('.') / 'temp'
# Cache control
CACHE_SIZE = 100  # Cache size limit (in number of files) for custom sources and downloads
CACHE_EXPIRY = 2592000  # Cache expiry time (in seconds) for custom sources and downloads
# VC and audio bot behavior
AUTO_LEAVE_DURATION = 300 # Duration before killing an audio session (in seconds)
SPOTIFY_TOP_COUNTRY = 'JP' # Used to establish an artist's top tracks, can be changed to any country you want
LIBRESPOT_REFRESH_INTERVAL = 120 # How often Librespot sessions should be regenerated (in seconds) 
DEFAULT_EMBED_COLOR = (145, 153, 252) # If the Now playing song doesn't have a cover
# Onsei filters
ONSEI_WHITELIST = ['mp3'] # Onsei tracks with one of these extensions and in a foldername containing one of these words, will be choose
ONSEI_BLACKLIST = ['なし'] # Chosen tracks containing one of these words will be blacklisted
# Chatbot settings
CHATBOT_ENABLED = True
CHATBOT_WHITELIST = [] # All server ids allowed to use the chatbot
CHATBOT_PREFIX = '-' # Prefix to trigger the chatbot
CHATBOT_TIMEOUT = 90 # Time before disabling continuous chat (in seconds, enabled with double prefix)

# Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()
    ]
)
