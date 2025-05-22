from dataclasses import dataclass
from datetime import datetime
from pinecone.core.openapi.db_data.model.scored_vector import ScoredVector
import pytz
from typing import Optional, List


from config import CHATBOT_TIMEZONE, CHATBOT_HISTORY_SIZE, OPENAI_ENABLED
from dataclasses import field


@dataclass
class ChatbotMessage:
    message_id: int
    guild_id: int
    author: str
    content: str
    recall_vectors: list[Optional[ScoredVector]] = field(default_factory=list)
    referenced_author: Optional[str] = None
    referenced_content: Optional[str] = None
    response: str = "*filtered*"
    date_: datetime = datetime.now()
    timezone = pytz.timezone(CHATBOT_TIMEZONE)
    sources: Optional[str] = None
    urls: Optional[list[str]] = None

    def __init_subclass__(cls):
        pass

    def format_recall_vectors(self) -> str:
        """Format recall vectors to a text for the prompt."""
        texts = [vector["metadata"].get("text") for vector in self.recall_vectors]
        if texts:
            recall_string = ", ".join(str(recall).replace("\n", "") for recall in texts)
            return recall_string
        else:
            return ""

    def date(self):
        """Return the date corresponding to when the message has been creating.
        Follows the format %Y-%m-%d %H:%M."""
        return self.date_.strftime("%Y-%m-%d %H:%M")

    def prompt(self) -> str:
        """Return the formatted prompt of the message to generate a response."""
        infos = [datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M")]

        if recall_text := self.format_recall_vectors():
            infos.append(f"memory: {recall_text}")

        if self.referenced_author and self.referenced_content:
            infos.append(
                f"Message replying to *{self.referenced_author}*: "
                f'"{self.referenced_content}"'
            )

        infos.append(f"**{self.author} talks to you**")
        message = f"[{', '.join(infos)}] {self.content}"

        return message


@dataclass
class ChatbotHistory:
    guild_id: int
    messages: List[ChatbotMessage] = field(default_factory=list)
    openai_input: List[str] = field(default_factory=list)
    pinecone_history: List[ChatbotMessage] = field(default_factory=list)
    # So 3 histories here:
    # - messages is the standard one, used in vector recalls
    # - openai input, used for openai compatibility
    # - pinecone_history is used to analyse the messages, put new vectors in the Pinecone index, then
    # messages used to generate it are removed from pinecone_history, to avoid superfluous vectors
    recalled_vector_ids: set[str] = field(default_factory=set)

    def __format__(self, format_spec):
        if format_spec == "pinecone_last_3":
            formatted_messages = [msg.content for msg in self.pinecone_history[-3:]]
            return ", ".join(formatted_messages)
        return str(self)

    def add(self, chatbot_message: ChatbotMessage) -> None:
        """If OpenAI features are enabled, this method should be used after
        the `store_recall` one, to save recalls in the OpenAI input."""
        msg = chatbot_message
        if not isinstance(msg, ChatbotMessage):
            raise TypeError("Not a ChatbotMessage class")
        self.messages.append(msg)
        self.pinecone_history.append(msg)

        if OPENAI_ENABLED:
            recall = msg.format_recall_vectors()
            infos = [f"memory: {recall}"] if recall else []
            infos.append(f"**{msg.author} talks to you**")
            new_prompt = f"[{', '.join(infos)}]: {msg.content}"
            self.openai_input = self.create_openai_input(new_prompt, msg.urls)

        for h in self.messages, self.pinecone_history, self.openai_input:
            while len(h) > CHATBOT_HISTORY_SIZE:
                h.pop(0)

        while len(self.openai_input) > CHATBOT_HISTORY_SIZE * 2:  # Including Q&A
            self.openai_input.pop(0)

    def create_openai_input(
        self, new_prompt: str, urls: Optional[list[str]] = None
    ) -> List[str]:
        """Return an input for OpenAI responses based on the history and a new message."""
        new_entry = {
            "role": "user",
            "content": [
                {"type": "input_text", "text": new_prompt},
            ],
        }
        if urls:
            for url in urls:
                new_entry["content"].append(
                    {
                        "type": "input_image",
                        "image_url": url,
                    }
                )

        return self.openai_input + [new_entry]

    def add_openai_assistant_response(self, response: str) -> None:
        self.openai_input.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": response},
                ],
            }
        )
        if len(self.openai_input) > CHATBOT_HISTORY_SIZE * 2:  # Including Q&A
            self.openai_input.pop(0)

    def pinecone_remove_last_three(self) -> None:
        for _ in range(3):
            if self.pinecone_history:
                self.pinecone_history.pop()

    def store_recall(self, vectors: list[ScoredVector]) -> None:
        for vector in vectors:
            self.recalled_vector_ids.add(vector["id"])
