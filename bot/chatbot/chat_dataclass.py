from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


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
    date: datetime = datetime.now()

    def __init_subclass__(cls):
        pass

    def __format__(self, format_spec):
        # To honor my friend Hibiki, a C# dev
        match format_spec:
            case "date":
                return datetime.now(self.date).strftime("%Y-%m-%d %H:%M")
            case "prompt":
                infos = [
                    f"Time in Kyoto: {datetime.now()}",
                    f"Pinecone recall: {self.pinecone_recall}"
                    if self.pinecone_recall
                    else "No Pinecone recall",
                ]
                if self.referenced_author and self.referenced_content:
                    infos.append(
                        f'Message referencing {self.referenced_author}: "{self.referenced_content}"'
                    )
                message = (
                    f"[{', '.join(infos)}, {self.author} talks to you] {self.content}"
                )
                return message
            case _:
                return str(self)


@dataclass
class ChatbotHistory:
    guild_id: int
    messages: List[ChatbotMessage]
