from dataclasses import dataclass
from datetime import datetime
import pytz
from typing import Optional, List


from config import CHATBOT_TIMEZONE


@dataclass
class ChatbotMessage:
    message_id: int
    guild_id: int
    author: str
    content: str
    pinecone_recall: Optional[str] = None
    referenced_author: Optional[str] = None
    referenced_content: Optional[str] = None
    response: Optional[str] = None
    search_summary: Optional[str] = None
    date: datetime = datetime.now()
    timezone = pytz.timezone(CHATBOT_TIMEZONE)

    def __init_subclass__(cls):
        pass

    def __format__(self, format_spec):
        # To honor my friend Hibiki, a C# dev
        match format_spec:
            case "date":
                return datetime.now(self.date).strftime("%Y-%m-%d %H:%M")
            case "prompt":
                infos = [
                    f"Time in Kyoto: {datetime.now(self.timezone)}",
                    f"Pinecone recall: {self.pinecone_recall}"
                    if self.pinecone_recall
                    else "No Pinecone recall",
                ]

                if self.search_summary:
                    infos.append(f"Google search results: {self.search_summary}")

                if self.referenced_author and self.referenced_content:
                    infos.append(
                        f"Message referencing {self.referenced_author}: "
                        f'"{self.referenced_content}"'
                    )

                message = (
                    f"[{', '.join(infos)}, **{self.author} talks to you**] {self.content}"
                )
                return message
            case _:
                return str(self)


@dataclass
class ChatbotHistory:
    guild_id: int
    messages: List[ChatbotMessage]
