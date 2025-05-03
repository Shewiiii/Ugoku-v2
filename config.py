from google.genai.types import SafetySetting, HarmCategory, HarmBlockThreshold
from pathlib import Path
import logging
import sys

#  ===FEATURES===
# I strongly recommend enabling the Spotify API to ensure the music bot functions properly.
# Make sure to specify SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in the .env file.
# If the Spotify API is disabled, please check ./commands/lyrics.py for adjustments.
SPOTIFY_API_ENABLED = True
SPOTIFY_ENABLED = False
DEEZER_ENABLED = False
DEFAULT_STREAMING_SERVICE = 'youtube' # spotify/deezer, youtube.
GEMINI_ENABLED = True # Don't forget to whitelist servers for the chatbot ! Scroll down to "CHATBOT_WHITELIST"
PINECONE_ENABLED = True
ALLOW_CHATBOT_IN_DMS = False # Allow everyone to use the bot in dms. Can increase the token usage.

# IN DEVELOPMENT: Used for compatibility purposes
# Make sure to create an OpenAI API key here https://platform.openai.com/api-keys
# If enabled, the OpenAI model will be used only for the chatbot for now
OPENAI_ENABLED = True

# ===CHATBOT MODELS===
GEMINI_MODEL = 'gemini-2.5-flash-preview-04-17'
GEMINI_UTILS_MODEL = 'gemini-2.0-flash' # Used for summaries and lyrics
OPENAI_MODEL = 'gpt-4.1-mini-2025-04-14'

# Display names
GEMINI_MODEL_DISPLAY_NAME = 'Gemini 2.5 Flash'
OPENAI_MODEL_DISPLAY_NAME = "GPT-4.1 mini"

#  ===SETTINGS===
# Ytdlp settings
COOKIES_PATH = './cookies.txt' # Parse cookies to ytdl to help with bot detection. Learn more: https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies
YTDLP_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "soundcloud.com"
] # small letters

# Paths
COMMANDS_FOLDER = Path('./commands')
TEMP_FOLDER = Path('.') / 'temp'
PREMIUM_CHANNEL_ID = None # Upload files too big to a channel in a boosted server instead

# Cache control & preloading
AGRESSIVE_CACHING = True # Download Spotify streams on disk before and when playing. Can be useful if Spotify often closes the connection with Librespot.
MAX_DUMMY_LOAD_INDEX = 6
MAX_PROCESS_POOL_WORKERS = 2 # Max number of simultaneous ytdlp fetching. None defaults to the number of processors
CACHE_SIZE = 100  # Cache size limit (in number of files)
CACHE_EXPIRY = 2592000  # Cache expiry time (in seconds). Default is one month

# VC and audio bot behavior
AUTO_LEAVE_DURATION = 900 # Duration before killing an audio session (in seconds)
DEEZER_REFRESH_INTERVAL = 3600 # How often should the bot refresh the Deezer session
SPOTIFY_REFRESH_INTERVAL = 180 # How often should the bot check and refresh the Spotify session
SPOTIFY_TOP_COUNTRY = 'JP' # Used to establish an artist's top tracks, can be changed to any country you want
DEFAULT_EMBED_COLOR = (237, 205, 85) # If the Now playing song doesn't have a cover
DEFAULT_AUDIO_VOLUME = 15 # Linear scale! The recommended value is around 15.
DEFAULT_ONSEI_VOLUME = 100 # Audio works are generally quieter for a higher dynamic range
DEFAULT_AUDIO_BITRATE = 510 # From 6 to 510 kbps (opus output)
IMPULSE_RESPONSE_PARAMS = {
    'bass boost (mono)': {
        'left_ir_file': 'bass.wav',
        'right_ir_file': 'bass.wav',
        'dry': 1,
        'wet': 7,
        'volume_multiplier': 0.3,
    },
    'reverb (mono)': {
        'left_ir_file': 'reverb.wav',
        'right_ir_file': 'reverb.wav',
        'dry': 7,
        'wet': 9,
        'volume_multiplier': 1.3
    },
    'north church': {
        'left_ir_file': 'north_church_L.wav',
        'right_ir_file': 'north_church_R.wav',
        'dry': 7,
        'wet': 5,
        'volume_multiplier': 1.3
    },
    'cinema': {
        'left_ir_file': 'cinema_L.wav',
        'right_ir_file': 'cinema_R.wav',
        'dry': 7,
        'wet': 3,
        'volume_multiplier': 0.8
    },
    'bass XXL': {
        'left_ir_file': 'bass_xxl_L.wav',
        'right_ir_file': 'bass_xxl_R.wav',
        'dry': 7,
        'wet': 2,
        'volume_multiplier': 0.6
    },
    'Raum airy default': {
        'left_ir_file': 'raum_default_airy_L.wav',
        'right_ir_file': 'raum_default_airy_R.wav',
        'dry': 10,
        'wet': 10,
        'volume_multiplier': 1
    },
    'Raum grounded default': {
        'left_ir_file': 'raum_default_grounded_L.wav',
        'right_ir_file': 'raum_default_grounded_R.wav',
        'dry': 10,
        'wet': 10,
        'volume_multiplier': 0.75
    },
    'Raum size 100%, decay 2s': {
        'left_ir_file': 'raum_max_size_L.wav',
        'right_ir_file': 'raum_max_size_R.wav',
        'dry': 10,
        'wet': 10,
        'volume_multiplier': 0.4
    }
} # (Advanced) Add your own audio effects to the /audio-effect list with an impulse response file in ./audio-ir

# Onsei filters
ONSEI_WHITELIST = ['mp3'] # Onsei tracks with one of these extensions and in a folder name containing one of these words will be chosen
ONSEI_BLACKLIST = ['なし'] # Tracks containing one of these words will be blacklisted
ONSEI_SERVER_WHITELIST= {} # All servers ids allowed to stream onsei

# Chatbot settings
CHATBOT_SERVER_WHITELIST = {} # All server ids allowed to use the chatbot and /ask
CHATBOT_ASK_SERVER_WHITELIST = {} # All server ids allow to use the /ask command
CHATBOT_CHANNEL_WHITELIST = {} # All channel/thread ids allowed to use the chatbot
CHATBOT_PREFIX = '!' # Prefix to trigger the chatbot
GEMINI_PREFIX = '-' # If OpenAI is enabled, CHATBOT_PREFIX+GEMINI_PREFIX will force to use Gemini instead
CHATBOT_TIMEOUT = 300 # Time before disabling continuous chat (in seconds, enabled with double prefix)
CHATBOT_TIMEZONE = 'Asia/Tokyo'
CHATBOT_TEMPERATURE = 1.0 # From 0.0 to 2.0. Specifies the randomness/creativity of the chatbot
CHATBOT_EMOTE_FREQUENCY = 1/5 # How often the emotes generated by gemini, will be shown. 
CHATBOT_EMOTES = {} # Add here all the discord emotes the chatbot should use ! 
  #E.g: {'Happy': <:emote1:1234567890123456789>, 'Sad': <:sad:1234567890123456789>} etc.
  # Get the snowflake id by adding a \ before sending the emote. Eg: \:emote:
CHATBOT_MAX_OUTPUT_TOKEN = 3000 # A too low max output token can result in a None ("filtered") output
CHATBOT_HISTORY_SIZE = 20 # How many messages (Q+A) to keep in chat history
CHATBOT_MAX_CONTENT_SIZE = {
    'text': 200000,
    'audio': 10000000,
    'image': 7000000,
    'application': 2000000
} # Max length of an attachment, in bytes
PINECONE_RECALL_WINDOW = 4
PINECONE_INDEX_NAME = 'ugoku2'
GEMINI_SAFETY_SETTINGS = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_NONE
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
] # See https://ai.google.dev/gemini-api/docs/safety-settings
LANGUAGES = [
    # Put any language you want to support in /translate command.
    # Has to be supported by the LLM.
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
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
