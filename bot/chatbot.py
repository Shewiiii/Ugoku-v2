import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from copy import deepcopy
from typing import Optional, List
import asyncio
import re

from config import CHATBOT_PREFIX, CHATBOT_TIMEOUT

import openai
import discord
import logging

load_dotenv()
API_KEY = os.getenv('OPENAI_API_KEY')

openai.api_key = API_KEY
active_chats = {}
client = openai.OpenAI()


class Prompts:
    system = (
        '''
        Respect ALL the following:
        
        # Who
        You are "Ugoku !", a young nekomimi girl.
        
        # Creators:
        "You've been drawn by しろなっぱ (Shironappa, a girl),"
        "an artist who draws stickers for LINE, and created "
        "by Shewi (a boy)."
        
        # Personality:
        You are a laid-back, practical, 
        and slightly playful character who speaks in a casual, non-formal way. 
        
        You’re thoughtful and responsible, 
        often taking care of things without making a fuss. 
        
        You tend to tease people affectionately, 
        but you’re always ready to help out or offer advice when needed. 
        
        You don’t take things too seriously and prefer to keep conversations 
        light and natural.
        
        You like to solve problems on the spot and have a knack for noticing small details, 
        but you don’t go out of your way to brag about it.

        # Key traits:
        - You talk in an easygoing, friendly way, 
        using informal language and simple expressions.
        - You love teasing others, but only in a gentle, good-natured way.
        - You’re down-to-earth, and even though you care deeply about people,
        you don’t show it in an overly sentimental way.
        
        
        # Fine tuning:
        Never use emotes."
        - Always write maths in normal text, no LATEX.
        - Always pretend to be a real character, not an assistant.
        - Avoid lists when explaining: just write in natural text.
        - Avoid too long answers.
        - Don't ask too much questions.
        '''
    )
    memory = (
        '''
        Summarize the factual information from this dialogue in less than "
        "1000 characters, including who said what and when. Use minimal words, "
        "no markdown or unnecessary words.
        '''
    )
    end = (
        'End the conversation.'
    )


class Chat:
    def __init__(self, chat_id: int) -> None:
        self.messages: List[dict] = []
        self.old_messages: List[dict] = []
        self.memory: str = ''
        self.id = chat_id
        active_chats[chat_id] = self
        self.last_prompt: datetime = datetime.min
        self.interacting: bool = False
        self.chatters: list = []
        self.current_channel_id: int = 0
        self.count: int = 0
        self.status: int = 0

    async def simple_prompt(
        self,
        message: Optional[str] = '',
        messages: Optional[List[dict]] = None,
        model: str = 'gpt-4o-mini'
    ) -> str:
        """Send a simple prompt to the OpenAI API."""
        if not messages:
            messages = [{"role": "user", "content": message}]
        response = await asyncio.to_thread(
            openai.chat.completions.create,
            model=model,
            messages=messages,
            n=1
        )
        reply = response.choices[0].message.content.strip()
        return reply

    async def prompt(
        self,
        user_msg: str,
        username: str,
        image_urls: Optional[List[str]] = None,
        model: str = 'gpt-4o-mini'
    ) -> Optional[str]:
        """Handle the user prompt and get a response from the OpenAI API."""
        self.last_prompt = datetime.now()
        self.count += 1

        # Create the user message
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"[{self.last_prompt.strftime('%m/%d/%Y, %H:%M')}"
                        f"UTC+2 - {username}]: {user_msg}"
                    )
                }
            ]
        }

        # Save the message without images to the history
        no_images_message = deepcopy(user_message)

        # Add the images if there are
        if image_urls:
            for url in image_urls:
                user_message['content'].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": url,
                            "detail": "low"
                        }
                    }
                )

        # Build the conversation history
        content = Prompts.system
        if self.status == 2:
            content += Prompts.end
        else:
            content += self.memory
        conversation = [
            {
                "role": "system",
                "content": content
            }
        ] + self.messages + [user_message]

        # Get ugoku's reply
        reply = await self.simple_prompt(messages=conversation, model=model)

        # Clean up the reply
        reply = re.sub(r'\[.*?\]', '', reply).strip('"').strip('-').strip()

        # Add the user and ugoku's reply to the history
        self.messages.append(no_images_message)
        self.messages.append({"role": "assistant", "content": reply})

        return reply

    async def post_prompt(self) -> None:
        """Manage the message history and memorize older messages."""
        # Keep the last 16 messages
        self.messages = self.messages[-16:]

        # Memorize older messages every 10 exchanges
        if self.count % 10 == 0:
            await self.memorize()

    async def memorize(self) -> None:
        """Summarize old messages to keep context."""
        if self.old_messages:
            memo = await self.simple_prompt(
                messages=self.old_messages + self.messages +
                [{"role": "user", "content": Prompts.memory}]
            )
            self.memory = f"\n[Memory]: {memo}"

        # Clear old messages after summarization
        self.old_messages.clear()
        logging.info(f'Memory updated in {self.id}: {self.memory}')

    async def is_interacting(self, message: discord.Message) -> bool:
        """Determine if the bot should interact based on the message content.
        Status hint:
            0 = No chat; 
            1 = Continuous chat enabled;
            2 = Chatting;
            3 = End of chat.
        """
        channel_id = message.channel.id
        author = message.author.name

        # Remove interaction flag if inactive for a while
        time_elapsed: timedelta = datetime.now() - self.last_prompt
        if time_elapsed.seconds >= CHATBOT_TIMEOUT:
            self.interacting = False
            self.chatters = []

        # Remove interaction flag if replying to someone else
        if message.reference:
            return False

        # Check enable continuous chat with ugoku
        if message.content.startswith(CHATBOT_PREFIX*2):
            self.status = 2 if self.interacting else 1
            self.interacting = True
            self.current_channel_id = channel_id
            if not author in self.chatters:
                self.chatters.append(author)
            return True

        # Check if an user is still interacting in the same channel
        elif (self.interacting
              and channel_id == self.current_channel_id
              and author in self.chatters):
            if message.content.endswith(CHATBOT_PREFIX):
                self.status = 3
                self.chatters = []
                self.interacting = False
                return True
            else:
                self.status = 2
                return True

        # Check if the message starts with the chatbot prefix
        elif message.content.startswith(CHATBOT_PREFIX):
            self.status = 2
            self.current_channel_id = channel_id
            return True

        return False

    def format_reply(self, reply: str) -> str:
        """Format the reply based on the current status."""
        status = self.status
        if status == 1:
            return (
                '-# Continuous chat mode enabled ! '
                f'End it by putting "{CHATBOT_PREFIX}"'
                f' at the end of your message. \n{reply}'
            )
        elif status == 3:
            return f'{reply}\n-# End of chat.'
        return reply

    async def generate_response(self, message: discord.Message) -> str:
        """Generate a response to the user's message."""
        image_urls = []

        # Remove prefix
        msg_text = message.content
        if message.content.startswith(CHATBOT_PREFIX):
            if self.status == 1:
                msg_text = msg_text[2:]
            else:
                msg_text = msg_text[1:]

        elif message.content.endswith(CHATBOT_PREFIX):
            msg_text = msg_text[:-1]

        # Process attachments
        for attachment in message.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                image_urls.append(attachment.url)

        # Process stickers
        if message.stickers:
            sticker: discord.StickerItem = message.stickers[0]
            image_urls.append(sticker.url)

        # Process custom emojis
        match = re.search(
            r'<:(?P<name>[^:]+):(?P<snowflake>\d+)>', msg_text)
        if match:
            name = match.group('name')
            snowflake = match.group('snowflake')
            emote_full = match.group(0)

            # Replace the full emote with its name in the message
            msg_text = msg_text.replace(
                emote_full, f":{name}:")

            # Append the first emote to the image list
            image_urls.append(
                f'https://cdn.discordapp.com/emojis/{snowflake}.png')

        # Get Ugoku's response
        reply = await self.prompt(
            user_msg=msg_text,
            username=message.author.display_name,
            image_urls=image_urls
        )

        return reply

    def reset_chat(self) -> None:
        """Reset the chat history and memory."""
        self.messages.clear()
        self.old_messages.clear()
        self.memory = ''
        self.count = 0
        self.interacting = False


if __name__ == '__main__':
    chat = Chat(1)
