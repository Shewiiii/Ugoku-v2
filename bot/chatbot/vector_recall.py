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


class QueryType(enum.Enum):
    QUESTION = 'question'
    INFO = 'info'
    OTHER = 'other'
    IMPORTANT_CARACTERISTIC = 'important_caracteristic'


class VectorMetadata(typing.TypedDict):
    query_type: QueryType
    text: str


class Memory:
    def __init__(self) -> None:
        self.timezone = pytz.timezone(CHATBOT_TIMEZONE)
        self.prompt = (
            "The user is sending a msg to Ugoku, the chatbot."
            "Precise type of query,"
            "Mark it as an 'important_caracteristic' __ONLY__ if  "
            "it TELLS SOMETHING VERY IMPORTANT YOU MUST NOT FORGET, "
            "PUT __EVERYTHING__ ELSE AS INFO/QUESTION/OTHER."
            "Extract facts synthetically, "
            "Write English:"
        )
        self.active = False

    async def init_pinecone(self, index_name: str) -> None:
        if not PINECONE_API_KEY:
            logging.warning("No valid Pinecone API key has been provided")
            return

        logging.info("Initialization of Pinecone..")
        while not self.active:
            try:
                self.pc = Pinecone(api_key=PINECONE_API_KEY)
                self.active = True
            except:
                await logging.error(
                    "Connection to Pinecone API failed, trying again in 60 seconds.")
                await asyncio.sleep(60)

        existing_indexes = [index.name for index in self.pc.list_indexes()]
        if not index_name in existing_indexes:
            self.pc.create_index(
                index_name,
                dimension=1024,
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
        self.index = self.pc.Index(index_name)
        logging.info("Pinecone has been initialized successfully")

    async def generate_embeddings(self, inputs: list) -> list:
        embeddings = await asyncio.to_thread(
            self.pc.inference.embed,
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
        if not self.active:
            return

        # Infos to summarize
        date: str = datetime.now(self.timezone).strftime("%Y-%m-%d")

        # Generate metadata using Gemini
        metadata = json.loads((await model.generate_content_async(
            f"{self.prompt}{author} said {user_text}",
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema=VectorMetadata,
                candidate_count=1
            )
        )).text)
        metadata['id'] = id
        metadata['text'] = f"{date}-{author}: {metadata['text']}"

        if metadata['query_type'] in ['info', 'question', 'other']:
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
    ) -> Optional[str]:
        if not self.active:
            return

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


memory = Memory()
