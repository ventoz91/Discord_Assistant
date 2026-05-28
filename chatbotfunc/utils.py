import openai
import asyncio
import os
import io
import re
import base64
import requests
from PIL import Image
from discord.ext import commands
from colorama import Fore


def split_message(message_content, max_length=1995):
    if not message_content.strip():
        return []
    if len(message_content) <= max_length:
        return [message_content]
    chunks = []
    parts = re.split(r'(```[\s\S]*?```)', message_content)
    current_chunk = ""
    for part in parts:
        if not part:
            continue
        if part.startswith("```") and part.endswith("```"):
            if len(part) <= max_length:
                if len(current_chunk) + len(part) + 1 <= max_length:
                    current_chunk += ("\n" if current_chunk else "") + part
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = part
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                inner = part[3:-3]
                first_newline = inner.find('\n')
                if first_newline != -1:
                    lang = inner[:first_newline]
                    code_content = inner[first_newline + 1:]
                else:
                    lang = ""
                    code_content = inner
                overhead = len(f"```{lang}\n") + len("\n```")
                lines = code_content.splitlines()
                code_chunk_lines = []
                code_chunk_len = 0
                for line in lines:
                    line_len = len(line) + 1
                    if code_chunk_len + line_len <= max_length - overhead:
                        code_chunk_lines.append(line)
                        code_chunk_len += line_len
                    else:
                        if code_chunk_lines:
                            chunks.append(f"```{lang}\n" + "\n".join(code_chunk_lines) + "\n```")
                        code_chunk_lines = [line]
                        code_chunk_len = line_len
                if code_chunk_lines:
                    chunks.append(f"```{lang}\n" + "\n".join(code_chunk_lines) + "\n```")
        else:
            for sentence in re.split(r'(?<=\.)\s+', part):
                if not sentence:
                    continue
                if len(sentence) > max_length:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
                    while len(sentence) > max_length:
                        chunks.append(sentence[:max_length])
                        sentence = sentence[max_length:]
                    current_chunk = sentence
                elif len(current_chunk) + len(sentence) + 1 <= max_length:
                    current_chunk += (" " if current_chunk else "") + sentence
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def format_error_message(error):
    try:
        if isinstance(error, openai.OpenAIError):
            return f"OpenAI Error: {str(error)}"
        elif hasattr(error, 'response') and error.response is not None:
            try:
                error_json = error.response.json()
                error_message = error_json.get('error', {}).get('message', 'No error message')
                return f"HTTP Error: {error_message}"
            except Exception as json_error:
                return f"Error in parsing HTTP response: {json_error}"
        else:
            return f"General Error: {str(error)}"
    except Exception as e:
        print(f"Error in formatting the error: {e}, Original error: {error}")
        return "An unexpected error occurred in formatting the error."


async def encode_discord_image(image_url: str):
    try:
        response = requests.get(image_url)
        image = Image.open(io.BytesIO(response.content)).convert('RGB')
        if max(image.size) > 1000:
            image.thumbnail((1000, 1000))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(Fore.RED + f"Error in encode_discord_image: {e}" + Fore.RESET)
        return None


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

