from dataclasses import dataclass
from datetime import datetime
import pytz
from typing import Optional, List


from config import CHATBOT_TIMEZONE, GEMINI_HISTORY_SIZE
from dataclasses import field


@dataclass
class ChatbotMessage:
    message_id: int
    guild_id: int
    author: str
    content: str
    pinecone_recall: Optional[str] = None
    referenced_author: Optional[str] = None
    referenced_content: Optional[str] = None
    response: str = "*filtered*"
    date: datetime = datetime.now()
    timezone = pytz.timezone(CHATBOT_TIMEZONE)

    def __init_subclass__(cls):
        pass

    def __format__(self, format_spec):
        # To honor my friend Hibiki, a C# dev
        match format_spec:
            case "date":
                return self.date.strftime("%Y-%m-%d %H:%M")
            case "prompt":
                infos = [
                    f"Time in Kyoto: {datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M")}",
                    f"Pinecone recall: {self.pinecone_recall}"
                    if self.pinecone_recall
                    else "No Pinecone recall",
                ]

                if self.referenced_author and self.referenced_content:
                    infos.append(
                        f"Message referencing {self.referenced_author}: "
                        f'"{self.referenced_content}"'
                    )

                message = f"[{', '.join(infos)}, **{self.author} talks to you**] {self.content}"
                return message
            case _:
                return str(self)


@dataclass
class ChatbotHistory:
    guild_id: int
    history: List[ChatbotMessage] = field(default_factory=list)
    pinecone_history: List[ChatbotMessage] = field(default_factory=list)
    # So 2 histories here:
    # - history is the standard one, no real use right now
    # - pinecone_history is used to analyse the messages, put new vectors in the Pinecone index, then
    # messages used to generate it are removed from pinecone_history, to avoid superfluous vectors

    def __format__(self, format_spec):
        if format_spec == "pinecone_last_3":
            formatted_messages = [msg.content for msg in self.pinecone_history[-3:]]
            return ", ".join(formatted_messages)
        return str(self)

    def add(self, chatbot_message: ChatbotMessage) -> None:
        if not isinstance(chatbot_message, ChatbotMessage):
            raise TypeError("Not a ChatbotMessage class")
        self.history.append(chatbot_message)
        self.pinecone_history.append(chatbot_message)
        for h in self.history, self.pinecone_history:
            if len(h) > GEMINI_HISTORY_SIZE:
                h.pop(0)

    def pinecone_remove_last_three(self) -> None:
        for _ in range(3):
            if self.pinecone_history:
                self.pinecone_history.pop()
