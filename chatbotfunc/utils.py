import openai
import asyncio
import os
from discord.ext import commands

# Modified to include bot and channel_file_contents as parameters
async def fetch_message_history(channel, bot: commands.Bot, channel_file_contents, include_file_content=True):
    history_length = int(os.getenv("HISTORYLENGTH", 30))
    message_history = []
    async for message in channel.history(limit=history_length * 2):
        if len(message_history) < history_length and message.content:
            message_history.append({"role": "user" if message.author != bot.user else "assistant", "content": message.content})
    
    if include_file_content and channel.id in channel_file_contents:
        message_history.insert(0, {"role": "user", "content": channel_file_contents[channel.id]})

    return message_history[::-1]

# Asynchronous function to get chat completions from OpenAI
async def async_chat_completion(*args, **kwargs):
    response = await asyncio.to_thread(openai.chat.completions.create, *args, **kwargs)
    return response