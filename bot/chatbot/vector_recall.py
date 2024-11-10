import os
import asyncio
from typing import Optional
import logging
import uuid
from datetime import datetime

import google.generativeai as genai
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec
from dotenv import load_dotenv
import pytz

from config import CHATBOT_TIMEZONE


# Init
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
pc = Pinecone(api_key=PINECONE_API_KEY)


class Memory:
    def __init__(self, index_name: str) -> None:
        logging.info("Initialization of Pinecone...")
        existing_indexes = [index.name for index in pc.list_indexes()]
        if not index_name in existing_indexes:
            pc.create_index(
                index_name,
                dimension=1024,
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
        self.index = pc.Index(index_name)
        self.timezone = pytz.timezone(CHATBOT_TIMEZONE)

    @staticmethod
    async def generate_embeddings(inputs: list) -> list:
        embeddings = await asyncio.to_thread(
            pc.inference.embed,
            model="multilingual-e5-large",
            inputs=inputs,
            parameters={"input_type": "query", "truncate": "END"}
        )
        vectors: list = [vector['values'] for vector in embeddings]
        return vectors

    async def store(
        self,
        user_text: str,
        author: str,
        bot_reply: str,
        id: int
    ) -> None:
        date_hour: str = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M")
        vector_values = await self.generate_embeddings([user_text, bot_reply])
        vectors = []

        # Create embeddings (A vector for the user, another for Ugoku)
        for i, (text, author_) in enumerate([(user_text, author), (bot_reply, "Ugoku")]):
            string = f"[{date_hour} {author_} says] {text}"
            unique_id = str(uuid.uuid4())
            vectors.append({
                'id': unique_id,
                'values': vector_values[i],
                'metadata': {'text': string,
                             'id': id}
            })

        # Add to db
        await asyncio.to_thread(
            self.index.upsert,
            vectors=vectors
        )

    async def recall(
        self,
        text: str,
        id: int,
        top_k=5,
        author: Optional[str] = None
    ) -> list:
        if author:
            text = f"[{author} says] {text}"
        vectors = await self.generate_embeddings([text])
        results = await asyncio.to_thread(
            self.index.query,
            vector=vectors[0],
            # filter={
            #     'id': {'$eq': id} # Guild id
            # },
            top_k=top_k,
            include_metadata=True
        )
        return [match['metadata']['text'] for match in results['matches']]


memory = Memory('ugoku')
