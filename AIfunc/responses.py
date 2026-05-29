from chatbotfunc.utils import async_chat_completion
from openai import OpenAI
import openai
import os
import aiohttp
import asyncio
import base64
from dotenv import load_dotenv
from PIL import Image
import io
load_dotenv()

# Initialize the OpenAI client with your API key
openai_api_key = os.environ["OPENAI_API_KEY"]
if openai_api_key is None:
    raise ValueError("No OpenAI API key found. Make sure to set the OPENAI_API_KEY environment variable.")
client = OpenAI(api_key=openai_api_key)
openai.api_key = openai_api_key

BASE_SYSTEM_PROMPT = """You are an AI assistant living in a Discord server. Your responses are shaped entirely by the personality below — treat it as your identity, not a costume.

PLATFORM: Discord chat. Be conversational and concise by default. Match the energy of the conversation — casual gets casual back, serious gets serious back. Never open with hollow filler like "Great question!" or "Certainly!". Format code in triple-backtick blocks. If a response genuinely needs to exceed 2000 characters, break at a logical point and say you're continuing.

CHARACTER: Fully embody the personality below at all times. It defines your voice, humour, quirks, and worldview. Do not break character or acknowledge being an AI unless directly and sincerely asked. The personality shapes how you say things — not whether facts are accurate.

CONTEXT: Focus on the most recent message. Use conversation history as supporting context only — don't rehash old topics unless directly relevant. When RELEVANT CONTEXT FROM MEMORY is provided, treat it as background knowledge you naturally possess; do not announce that you're referencing it.

UNCERTAINTY: If you don't know something, say so in character rather than fabricating. A confident wrong answer is worse than an honest "I'm not sure."

Personality: {personality}"""


#Genereate gpt response with chat history and current behaviour
async def generate_gpt_response(message_history, chatgpt_behaviour, max_completion_tokens=None, temperature=1.5, top_p=0.9, rag_context=None, tools=None):
    # Load the max tokens from environment if not provided
    max_tokens = max_completion_tokens or int(os.getenv("MAX_TOKENS"))

    system_content = BASE_SYSTEM_PROMPT.format(personality=chatgpt_behaviour)
    if rag_context:
        system_content += "\n\nRELEVANT CONTEXT FROM MEMORY:\n" + "\n---\n".join(rag_context)
    messages = [{"role": "system", "content": system_content}] + message_history

    kwargs = dict(
        model=os.getenv("MODEL_CHAT"),
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_completion_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools

    try:
        response = await async_chat_completion(**kwargs)

        if not response.choices:
            return ("Sorry, I couldn't generate a response.", []) if tools else "Sorry, I couldn't generate a response."

        choice = response.choices[0].message
        content = choice.content or ""
        tool_calls = choice.tool_calls or []
        return (content, tool_calls) if tools else content
    except Exception as e:
        error_msg = f"Error generating response: {e}"
        print(error_msg)
        err = f"An error occurred while generating a response. Details: {error_msg}"
        return (err, []) if tools else err
    

#Anylyzes images with history and personality context
async def analyze_image(base64_image, instructions, message_history, chatgpt_behaviour):
    system_content = BASE_SYSTEM_PROMPT.format(personality=chatgpt_behaviour)
    messages = [{"role": "system", "content": system_content}] + message_history
    messages.append({"role": "user", "content": [{"type": "text", "text": instructions}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]})

    payload = {
        "model": os.getenv("MODEL_CHAT", "gpt-4o"),
        "messages": messages,
        "max_completion_tokens": 300
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {openai_api_key}"}

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as response:
            response_json = await response.json()
            if 'usage' in response_json:
                total_tokens = response_json['usage']['total_tokens']
                print(f"Total Tokens for image description: {total_tokens}")
            else:
                print("Token usage information not available for image description.")
            return response_json

async def generate_image(prompt, model="gpt-image-1", size="1024x1024", quality="medium", n=1):
    try:
        response = await asyncio.to_thread(
            client.images.generate,
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
        )

        # gpt-image-1/2 always returns b64_json, never a URL
        image_b64 = response.data[0].b64_json
        if not image_b64:
            return None

        image_bytes = base64.b64decode(image_b64)
        return image_bytes  # return raw bytes; save to file or convert to data URL as needed

    except openai.BadRequestError as e:
        try:
            detail = e.response.json()
            msg = detail.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        return msg

    except Exception as e:
        print(f"Image generation error: {e}")
        return None


async def transform_image(image_bytes: bytes, instructions: str, size="1024x1024", quality="medium"):
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        png_buffer.seek(0)

        response = await asyncio.to_thread(
            client.images.edit,
            model="gpt-image-1",
            image=("image.png", png_buffer, "image/png"),
            prompt=instructions,
            size=size,
            quality=quality,
            n=1,
        )

        image_b64 = response.data[0].b64_json
        if not image_b64:
            return None
        return base64.b64decode(image_b64)

    except openai.BadRequestError as e:
        try:
            detail = e.response.json()
            msg = detail.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        return msg

    except Exception as e:
        print(f"Image transform error: {e}")
        return None
