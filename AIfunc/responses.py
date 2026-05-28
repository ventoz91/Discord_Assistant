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


#Genereate gpt response with chat history and current behaviour
async def generate_gpt_response(message_history, chatgpt_behaviour, max_completion_tokens=None, temperature=1.5, top_p=0.9):
    # Load the max tokens from environment if not provided
    max_tokens = max_completion_tokens or int(os.getenv("MAX_TOKENS"))

    # Prepare the messages, including the system behavior message
    messages = [{"role": "system", "content": chatgpt_behaviour}] + message_history
    messages.append({"role": "assistant", "content": "What is your reply?"})

    try:
        response = await async_chat_completion(
            model=os.getenv("MODEL_CHAT"),
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_tokens
        )

        if response.choices:
            return response.choices[0].message.content
        else:
            return "Sorry, I couldn't generate a response."
    except Exception as e:
        error_msg = f"Error generating response: {e}"
        print(error_msg)
        return f"An error occurred while generating a response. Details: {error_msg}"
    

#Anylyzes images with history and personality context
async def analyze_image(base64_image, instructions, message_history, chatgpt_behaviour):
    # Prepend the chat behavior and message history to the messages list
    messages = [{"role": "system", "content": chatgpt_behaviour}] + message_history
    messages.append({"role": "user", "content": [{"type": "text", "text": instructions}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]})

    payload = {
#        "model": "chatgpt-4o-latest"
        "model": "gpt-5.4",
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
