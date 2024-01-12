from chatbotfunc.utils import async_chat_completion
from dotenv import load_dotenv
from openai import OpenAI
import openai
import os
import aiohttp


load_dotenv()

# Initialize the OpenAI client with your API key
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key is None:
    raise ValueError("No OpenAI API key found. Make sure to set the OPENAI_API_KEY environment variable.")
client = OpenAI(api_key=openai_api_key)
openai.api_key = openai_api_key

#Genereate gpt response with chat history and current behaviour
async def generate_gpt_response(message_history, chatgpt_behaviour, max_tokens=None, temperature=1.5, top_p=0.9):
    # Load the max tokens from environment if not provided
    max_tokens = max_tokens or int(os.getenv("MAX_TOKENS"))

    # Prepare the messages, including the system behavior message
    messages = [{"role": "system", "content": chatgpt_behaviour}] + message_history
    messages.append({"role": "assistant", "content": "What is your reply?"})

    try:
        response = await async_chat_completion(
            model=os.getenv("MODEL_CHAT"),
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
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
        "model": "gpt-4-vision-preview",
        "messages": messages,
        "max_tokens": 300
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
        
#For Analyzing images when personality and chat history is not needed
async def analyze_img(base64_image, instructions):
    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [{"role": "user", "content": [{"type": "text", "text": instructions}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
        "max_tokens": 300
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
        
async def generate_image(prompt, model="dall-e-3", size="1024x1024", quality="standard", n=1):
    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
        )
        image_url = response.data[0].url
        return image_url
    except openai.BadRequestError as e:
        return None, str(e)
    except Exception as e:
        return None

