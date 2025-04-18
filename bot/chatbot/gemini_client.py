from google import genai
import os

from config import GEMINI_ENABLED

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_ENABLED else None
