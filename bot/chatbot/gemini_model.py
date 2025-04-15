import google.generativeai as genai
import os

from config import GEMINI_UTILS_MODEL

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
global_model = genai.GenerativeModel(model_name=GEMINI_UTILS_MODEL)
