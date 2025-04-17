import os
import asyncio
from typing import Optional
import logging
import uuid
from datetime import datetime
import json

import google.generativeai as genai
from pinecone.core.openapi.db_data.model.scored_vector import ScoredVector
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec
import pytz

from bot.chatbot.chat_dataclass import ChatbotMessage
from bot.chatbot.gemini_model import global_model
from config import (
    CHATBOT_TIMEZONE,
    PINECONE_RECALL_WINDOW,
    PINECONE_ENABLED,
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
You are an assistant that classifies each Discord message into exactly one of four categories: 
“question”, “info”, “other”, or “important_caracteristic”.
Use these rules:
• “question”: The message explicitly or implicitly **asks something**, or contains a question mark.
• “info”: It provides information or opinions that are not personal preferences or factual personal details.
• “other”: It doesn’t fit the other categories (e.g. greetings, jokes, improbable statements, nonsense, vague statements, affirmations).
• “important_caracteristic”: It only concerns crutial informations about personal tastes (e.g. favorite food), 
personal factual data (birthday, age, etc.), real-world facts (historical events, fun facts) or a message the user asks to remember. Not a question! 
Add in the text field the user message. It should be exact and should not loose information.\n
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

    async def store(self, chatbot_message: ChatbotMessage) -> bool:
        if not self.active:
            return

        # Infos to summarize
        date: str = datetime.now(self.timezone).strftime("%Y-%m-%d")

        # Generate metadata using Gemini
        metadata = json.loads(
            (
                await global_model.generate_content_async(
                    f'{self.prompt}{chatbot_message.author} said "{chatbot_message.content}"',
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema,
                        candidate_count=1,
                    ),
                )
            ).text
        )
        metadata["id"] = chatbot_message.guild_id
        metadata["text"] = f"{date}-{chatbot_message.author}: {metadata['text']}"

        if metadata["query_type"] in {"info", "question", "other"}:
            return False

        # Create the embeddings/vectors
        vector_values = await self.generate_embeddings(metadata["text"])
        unique_id = str(uuid.uuid4())
        vectors = [{"id": unique_id, "values": vector_values[0], "metadata": metadata}]

        # Add to db
        await asyncio.to_thread(self.index.upsert, vectors=vectors)

        logging.info(f"Added to Pinecone: {metadata['text']}")
        return True

    async def recall(
        self,
        text: str,
        id: int,
        top_k: int = PINECONE_RECALL_WINDOW,
    ) -> Optional[str]:
        if not self.active:
            return
        vectors = await self.get_vectors(text, id, top_k)
        texts = [vector["metadata"].get("text") for vector in vectors]
        if texts:
            recall_string = ", ".join(str(recall).replace("\n", "") for recall in texts)
            return recall_string

    async def get_vectors(
        self, text: str, id: int, top_k=999
    ) -> Optional[list[ScoredVector]]:
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
