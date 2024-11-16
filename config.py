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
AUTO_LEAVE_DURATION = 900 # Duration before killing an audio session (in seconds)
SPOTIFY_TOP_COUNTRY = 'JP' # Used to establish an artist's top tracks, can be changed to any country you want
LIBRESPOT_REFRESH_INTERVAL = 120 # How often Librespot sessions should be regenerated (in seconds) 
DEFAULT_EMBED_COLOR = (145, 153, 252) # If the Now playing song doesn't have a cover
DEFAULT_AUDIO_VOLUME = 30 # The recommended value is 30 since the bot can get pretty loud
# Onsei filters
ONSEI_WHITELIST = ['mp3'] # Onsei tracks with one of these extensions and in a foldername containing one of these words, will be choose
ONSEI_BLACKLIST = ['なし'] # Chosen tracks containing one of these words will be blacklisted
# Chatbot settings
CHATBOT_ENABLED = True
CHATBOT_WHITELIST = [] # All server ids allowed to use the chatbot
CHATBOT_PREFIX = '-' # Prefix to trigger the chatbot
CHATBOT_TIMEOUT = 300 # Time before disabling continuous chat (in seconds, enabled with double prefix)
CHATBOT_TIMEZONE = 'Asia/Tokyo'
CHATBOT_EMOTES = {} # Add here all the discord emotes the chatbot should use ! 
  #E.g: {'Happy': <:emote1:1234567890123456789>, 'Sad': <:sad:1234567890123456789>} etc.
  # Get the snowflake id by adding a \ before sending the emote. Eg: \:emote:
PINECONE_RECALL_WINDOW = 20
GEMINI_MODEL = 'gemini-1.5-pro'
GEMINI_UTILS_MODEL = 'gemini-1.5-flash' # Used for summaries and lyrics
GEMINI_HISTORY_SIZE = 20 # How many messages to remember per chat instance
GEMINI_SAFETY_SETTINGS = [
    {
        "category": "HARM_CATEGORY_DANGEROUS",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE",
    },
] # See https://ai.google.dev/gemini-api/docs/safety-settings
LANGUAGES = [
    # Put any language you want to support in /translate command.
    # Has to be supported by GPT-4o Mini.
    "Arabic", "Bengali", "Dutch", "English", "French", "German", "Greek",
    "Hebrew", "Hindi", "Indonesian", "Italian", "Japanese",
    "Korean", "Mandarin Chinese", "Persian", "Polish", "Portuguese",
    "Russian", "Spanish", "Swedish", "Thai", "Turkish", "Vietnamese"
]
# Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()
    ]
)
