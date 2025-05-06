from datetime import datetime, timedelta
from google import genai
import logging
import os

from config import GEMINI_ENABLED, GEMINI_UTILS_MODELS


class UtilsModelsManager:
    """Manage multiple models for utilities tasks, to reduce rate limit issues."""

    def __init__(self):
        assert len(GEMINI_UTILS_MODELS) != 0, "No Gemini model available"
        self.models = GEMINI_UTILS_MODELS
        self.models_set = set(GEMINI_UTILS_MODELS)
        self.model_count = len(self.models)
        self.down = {}  # Key: model, value: datetime
        self.down_set = set([])

    def update(self):
        for model, date in self.down.items():
            if datetime.now() - date > timedelta(minutes=1):
                del self.down[model]
                self.down_set.remove(model)

    def pick(self) -> str:
        """Pick an available model."""
        self.update()
        for model in self.models:
            if model not in self.down_set:
                return model

        # All models are down
        raise RuntimeError("No more model available")

    def add_down_model(self, model: str) -> None:
        logging.info(f"{model} has been rate limited")
        if model not in self.models:
            return
        self.down[model] = datetime.now()
        self.down_set.add(model)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_ENABLED else None
utils_models_manager = UtilsModelsManager()
