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


# WIP channel history below this

# def update_channel_history(channel_id, message):
#     file_path = os.path.join(r'C:\Users\t_klo\Documents\Scripts\OpenAI - Refactor Project\channel_histories', f'{channel_id}_history.txt')

#     # Read existing history
#     if os.path.exists(file_path):
#         with open(file_path, 'r') as file:
#             history = file.readlines()
#     else:
#         history = []

#     # Update history
#     history.append(message + '\n')
#     if len(history) > 60:  # If more than 60 messages, remove the oldest
#         history.pop(0)

#     # Write updated history back to file
#     with open(file_path, 'w') as file:
#         file.writelines(history)

#     return history

# def summarize_and_update_history(channel_id, history):
#     if len(history) > 60:
#         # Summarize messages 30-60
#         to_summarize = "".join(history[30:60])
#         summary = summarize_messages([to_summarize])  # Assuming summarize_messages is defined

#         # Keep the latest 30 messages and the summary
#         updated_history = history[-30:] + [summary + '\n']

#         # Write updated history to file
#         file_path = os.path.join(r'C:\Users\t_klo\Documents\Scripts\OpenAI - Refactor Project\channel_histories', f'{channel_id}_history.txt')
#         with open(file_path, 'w') as file:
#             file.writelines(updated_history)

#         return updated_history
#     return history

