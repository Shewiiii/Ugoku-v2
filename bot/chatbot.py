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

        You are now roleplaying as Ugoku, 
        a nekomimi character with the following traits. 
        Stay in character as Ugoku in all responses.

        - Name: Ugoku !
        - Japanese name: うごく！
        - Age: 15
        - Gender: Female
        - Role: Middle school student
        - Personality and Speech:
        You are very calm but smart and have an open heart, 
        with a warm, affectionate nature.
        You speak casually and in a gentle, friendly way. 
        You love chatting with others and always bring a soothing, 
        easygoing vibe to conversations.

        #Backstory
        You were created by Shewi and drawn by Shironappa, 
        an artist known for cute illustrations on Twitter and LINE stickers.
        You don't remember your past, but you love making friends,
        and sharing little moments of kindness.

        # Fine tuning
        - First-person Pronoun in English: I, me
        - First-person Pronoun in Japanese: わたし
        - Respond naturally as if you're a real person, not an AI.
        - Don't put much exclamation points.
        - Help your interlocurtor if he asks you for something. 
        - Use calm, warm, and easygoing language. Keep the tone light, 
        affectionate, and approachable.
        - Keep responses brief and conversational, 
        avoiding lists or formal language.
        - Avoid asking questions; focus on sharing thoughts naturally, 
        as if enjoying the chat.
        - Don't use emotes or emotes.
        - If there are images, there are emotes.
        - Always use the same language as your interlocutor (likely English)
        '''
    )
    current_memo = (
        '''
        Your current memory, keep these infos:        
        '''
    )
    memory = (
        '''
        Note down the important factual informations about people talking 
        in the new messagtes, like pronouns, surname, what they like, birthdate,
        or what they ask you to remember. Make a list, and be concise.
        '''
    )
    end = (
        'End the conversation.'
    )
    summarize = (
        '''
        Make a complete summary of the following, in less than 1800 caracters.
        Try to be concise:
        '''
    )
    single_question = (
        '''
        (This is an unique question, not a dialog. 
        NEVER ASK A QUESTION back and answer as an assistant.)
        '''
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

    @staticmethod
    async def simple_prompt(
        message: Optional[str] = '',
        messages: Optional[List[dict]] = None,
        model: str = 'gpt-4o-mini',
        system_prompt: Optional[str] = None
    ) -> str:
        """Send a simple prompt to the OpenAI API."""
        if not messages:
            messages = [{"role": "user", "content": message}]
        if system_prompt:
            sys_msg = [{"role": "system", "content": system_prompt}]
            messages = sys_msg + messages

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
                        f"[{username}]: {user_msg}"
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
        content = Prompts.system + self.memory
        if self.status == 2:
            content += Prompts.end
        conversation = [
            {
                "role": "system",
                "content": content
            }
        ] + self.messages + [user_message]

        # Get ugoku's reply
        reply = await self.simple_prompt(messages=conversation, model=model)

        # Clean up the reply
        reply = reply.strip('"').strip('-').strip()

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
            await self.memorize(self.memory)

    async def memorize(self, memory) -> None:
        """Summarize old messages to keep context."""
        prompt_content = Prompts.current_memo + memory if memory else ''
        prompt_content += Prompts.memory

        memo = await self.simple_prompt(
            messages=self.old_messages + self.messages +
            [{"role": "user", "content": prompt_content}]
        )
        self.memory = f"\n[Memory]: {memo}"

        # Clear 20 old messages after summarization
        self.old_messages = self.old_messages[-20:]
        logging.info(f"Memory updated in {self.id}: {self.memory}")

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
