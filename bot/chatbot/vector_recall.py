import os
import asyncio
from typing import Optional
import logging
import uuid
from datetime import datetime
import json

from google.genai import types
from pinecone.core.openapi.db_data.model.scored_vector import ScoredVector
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec
import pytz

from bot.chatbot.chat_dataclass import ChatbotHistory
from bot.chatbot.gemini_client import client
from config import (
    GEMINI_UTILS_MODEL,
    CHATBOT_TIMEZONE,
    PINECONE_ENABLED,
    GEMINI_SAFETY_SETTINGS,
)


# Init
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
response_schema = {
    "type": "object",
    "properties": {
        "query_type": {
            "type": "string",
            "enum": ["question", "info", "other", "important_caracteristic"],
        },
        "text": {"type": "string"},
    },
    "required": ["query_type", "text"],
}


class Memory:
    def __init__(self) -> None:
        self.timezone = pytz.timezone(CHATBOT_TIMEZONE)
        self.prompt = """
Here a set of 3 messages categorize and memorize.
Use these rules to define the type:
- “important_caracteristic”: IF ANY OF THE MESSAGE countains an information about personal tastes (e.g. favorite food), 
personal factual data (birthday, age, etc.), real-world facts (historical events, fun facts, life info) 
or if the user asks to remember something. 
- “question”: The messages explicitly or implicitly **asks something**, or contains a question mark, while not having “important_caracteristic”
- “info”: It provides information or opinions that are not personal preferences or factual personal details.
- “other”: If it doesn't fit the other categories.
In the text field, add what info we should remember if the type == “important_caracteristic”,  It should not loose information 
but nothing otherwise.\n
"""
        self.active = False

    async def init_pinecone(self, index_name: str) -> None:
        if not PINECONE_ENABLED:
            return
        if not PINECONE_API_KEY:
            logging.warning("No valid Pinecone API key has been provided")
            return

        logging.info("Initialization of Pinecone..")
        while not self.active:
            try:
                self.pc = await asyncio.to_thread(Pinecone, api_key=PINECONE_API_KEY)
                self.active = True
            except Exception as e:
                await logging.error(
                    f"Connection to Pinecone API failed: {e}, trying again in 60 seconds."
                )
                await asyncio.sleep(60)

        existing_indexes = [index.name for index in self.pc.list_indexes()]
        if index_name not in existing_indexes:
            self.pc.create_index(
                index_name,
                dimension=1024,
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self.index = self.pc.Index(index_name)
        logging.info("Pinecone has been initialized successfully")

    async def generate_embeddings(self, inputs: list) -> list:
        embeddings = await asyncio.to_thread(
            self.pc.inference.embed,
            model="multilingual-e5-large",
            inputs=inputs,
            parameters={"input_type": "query", "truncate": "END"},
        )
        vectors: list = [vector["values"] for vector in embeddings]
        return vectors

    # async def store(self, chatbot_message: ChatbotMessage) -> bool:
    async def store(self, history: ChatbotHistory) -> bool:
        """If relevant, store a Pinecone vector in the index based on the last 3 messages."""
        if not self.active:
            return

        # Generate metadata using Gemini
        date: str = datetime.now(self.timezone).strftime("%Y-%m-%d")
        metadata = json.loads(
            (
                await client.aio.models.generate_content(
                    model=GEMINI_UTILS_MODEL,
                    contents=f"{self.prompt}{history:pinecone_last_3}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema,
                        candidate_count=1,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                        safety_settings=GEMINI_SAFETY_SETTINGS,
                    ),
                )
            ).text
        )
        last_message = history.history[-1]
        metadata["id"] = last_message.guild_id
        metadata["text"] = f"{date}-{last_message.author}: {metadata['text']}"

        if metadata["query_type"] in {"info", "question", "other"}:
            return False
        else:
            # Important carac: remove the messages from the Pinecone history
            history.pinecone_remove_last_three()

        # Create the embeddings/vectors
        vector_values = await self.generate_embeddings(metadata["text"])
        unique_id = str(uuid.uuid4())
        vectors = [{"id": unique_id, "values": vector_values[0], "metadata": metadata}]

        # Add to db
        await asyncio.to_thread(self.index.upsert, vectors=vectors)

        logging.info(f"Added to Pinecone: {metadata['text']}")
        return True

    async def get_vectors(
        self, text: str, id: int, top_k=999
    ) -> list[Optional[ScoredVector]]:
        if not self.active:
            raise RuntimeError("Pinecone class not active")
        vectors = await self.generate_embeddings([text])
        results = await asyncio.to_thread(
            self.index.query,
            vector=vectors[0],
            filter={
                "id": {"$eq": id}  # Guild id
            },
            top_k=top_k,
            include_metadata=True,
        )
        vectors = [vector for vector in results["matches"]]
        return vectors


memory = Memory()
