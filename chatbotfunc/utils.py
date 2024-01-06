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

# Placeholder for read_personalities_from_file function
def read_personalities_from_file():
    if not os.path.exists("personalities.env"):
        return []
    with open("personalities.env", "r") as file:
        lines = file.readlines()
        return [line.strip().split('=')[1] for line in lines if line.strip() and '=' in line]

# Placeholder for get_personality_name function
async def get_personality_name(model, personality, temperature=0.7):
    # Construct a prompt to ask the personality for its name
    prompt = f"As a {personality}, if you had a first and last name, what would it be? Please type first and last name only"
    # Request a response from OpenAI
    response = await async_chat_completion(
        model=os.getenv("MODEL_CHAT"),
        messages=[{"role": "system", "content": prompt}],  # Wrap the prompt in a message object
        temperature=0.7,
        top_p=0.9,
        max_tokens=10  # Limiting response length for brevity
    )
    # Extracting and returning the GPT response (name)
    return response.choices[0].message.content.strip()

# Asynchronous function to get chat completions from OpenAI
async def async_chat_completion(*args, **kwargs):
    response = await asyncio.to_thread(openai.chat.completions.create, *args, **kwargs)
    return response