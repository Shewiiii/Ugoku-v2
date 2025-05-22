from datetime import datetime, timedelta
from google import genai
import logging
import os
from typing import Optional

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


def _create_client(env_var: str) -> Optional[genai.Client]:
    api_key = os.getenv(env_var)
    return genai.Client(api_key=api_key) if api_key else None


if GEMINI_ENABLED:
    client: genai.Client = _create_client("GEMINI_API_KEY")
    premium_client: genai.Client = _create_client("PREMIUM_GEMINI_API_KEY")
else:
    client = premium_client = None

utils_models_manager = UtilsModelsManager()
