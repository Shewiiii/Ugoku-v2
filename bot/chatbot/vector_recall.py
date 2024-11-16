import os
import asyncio
from typing import Optional
import logging
import uuid
from datetime import datetime
import typing_extensions as typing
import enum
import json

import google.generativeai as genai
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec
from dotenv import load_dotenv
import pytz

from config import (
    CHATBOT_TIMEZONE,
    GEMINI_UTILS_MODEL,
    PINECONE_RECALL_WINDOW
)


# Init
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name=GEMINI_UTILS_MODEL
)
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
pc = Pinecone(api_key=PINECONE_API_KEY)


class QueryType(enum.Enum):
    QUESTION = 'question'
    INFO = 'info'
    OTHER = 'other'


class VectorMetadata(typing.TypedDict):
    query_type: QueryType
    text: str


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
        self.prompt = (
            "Precise type of query."
            "Summarize the message, "
            "write English:"
        )

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
        id: int
    ) -> None:
        # Infos to summarize
        date_hour: str = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M")

        # Generate metadata using Gemini
        metadata = json.loads((await model.generate_content_async(
            self.prompt+user_text,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema=VectorMetadata,
                candidate_count=1
            )
        )).text)
        metadata['id'] = id
        metadata['text'] = f"{author}, {date_hour}: {metadata['text']}"

        if metadata['query_type'] in ['question', 'other']:
            return

        # Create the embeddings/vectors
        vector_values = await self.generate_embeddings(metadata['text'])
        unique_id = str(uuid.uuid4())
        vectors = [{
            'id': unique_id,
            'values': vector_values[0],
            'metadata': metadata
        }]

        # Add to db
        await asyncio.to_thread(
            self.index.upsert,
            vectors=vectors
        )
        logging.info(f"Added to Pinecone: {metadata['text']}")

    async def recall(
        self,
        text: str,
        id: int,
        top_k: int = PINECONE_RECALL_WINDOW,
        author: Optional[str] = '?',
        date_hour: str = ''
    ) -> str:
        infos = [
            date_hour,
            f"{author} says"
        ]
        text = f"[{', '.join(infos)}] {text}"

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
        rec = [match['metadata'].get('text') for match in results['matches']]
        if rec:
            rec_string = ', '.join(str(recall).replace('\n', '')
                                   for recall in rec)

        return rec_string


memory = Memory('ugoku')
