from chatbotfunc.utils import async_chat_completion
import azure.cognitiveservices.speech as speechsdk
from openai import OpenAI
import openai
import discord
import os
import aiohttp
import asyncio
import aiofiles
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from gtts import gTTS
import base64
from dotenv import load_dotenv
load_dotenv()

# Initialize the OpenAI client with your API key
openai_api_key = os.environ["OPENAI_API_KEY"]
if openai_api_key is None:
    raise ValueError("No OpenAI API key found. Make sure to set the OPENAI_API_KEY environment variable.")
client = OpenAI(api_key=openai_api_key)
openai.api_key = openai_api_key


# Azure credentials
subscription_key = "f51fae5c9c6f4ac98e550a83d5442809"
service_region = "eastus"
    
async def process_voice(voice):
    try:
        print(f"Processing audio file: {voice}")

        # Set up the Azure speech configuration
        speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=service_region)

        # Audio configuration for the file
        audio_input = speechsdk.AudioConfig(filename=voice)

        # Initialize speech recognizer
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

        # Perform speech recognition
        result = speech_recognizer.recognize_once_async().get()

        # Check the result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print(f"Recognized: {result.text}")
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            print("No speech could be recognized")
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"Speech Recognition canceled: {cancellation.reason}")
            if cancellation.reason == speechsdk.CancellationReason.Error:
                print(f"Error details: {cancellation.error_details}")
        return None
    except Exception as e:
        print(f"Exception occurred: {e}")
        return None


class NewRecordingHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        print(f"New file detected: {file_path}")
        
        # Check for .ogg, .wav, and .mp3 files
        if file_path.endswith(('.ogg', '.wav', '.mp3')):
            print(f"File is an audio file ({file_path.split('.')[-1]}), proceeding to process and speak")
            asyncio.run_coroutine_threadsafe(self.process_and_speak(file_path), self.bot.loop)

    async def process_and_speak(self, file_path):
        try:
            print(f"Processing file: {file_path}")

            # Process the audio file
            transcript = await process_voice(file_path)
            if transcript:
                recognized_text = transcript
                print(f"Transcript: {recognized_text}")

                # Prepare message history for GPT response
                message_history = [{"role": "user", "content": recognized_text}]
                chatgpt_behaviour = "You are a AI chat assistant who burps a lot here to help with any video game questions. Please keep your answers short and concise"  # Adjust as needed

                # Get GPT response
                gpt_response = await generate_gpt_response(message_history, chatgpt_behaviour)
                await self.speak_in_voice_channel(gpt_response)
        except Exception as e:
            print(f"Error in process_and_speak: {e}")

    async def speak_in_voice_channel(self, text):
        print("Preparing to speak in voice channel")

        # Generate the TTS audio from the text
        tts = gTTS(text, lang='en')
        tts_file = "tts_output.mp3"
        tts.save(tts_file)

        # Find a connected voice client
        voice_client = next((vc for vc in self.bot.voice_clients if vc.is_connected()), None)

        if voice_client:
            print("Voice client found and connected, playing audio")
            # Ensure no other audio is playing
            if not voice_client.is_playing():
                voice_client.play(discord.FFmpegPCMAudio(tts_file), after=lambda e: os.remove(tts_file))
        else:
            print("Voice client not found or not connected.")



# Function to initiate monitoring
def start_monitoring(bot):
    os.makedirs('./recordings', exist_ok=True)
    event_handler = NewRecordingHandler(bot)
    observer = Observer()
    observer.schedule(event_handler, './recordings', recursive=False)
    observer.start()
    return observer

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
        
#For Analyzing images when personality and chat history is not needed
async def analyze_img(base64_image, instructions):
    payload = {
        "model": "gpt-5.4",
        "messages": [{"role": "user", "content": [{"type": "text", "text": instructions}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
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
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,  # must be "low", "medium", or "high"
            n=n,
        )

        # gpt-image-1/2 always returns b64_json, never a URL
        image_b64 = response.data[0].b64_json
        if not image_b64:
            return None

        image_bytes = base64.b64decode(image_b64)
        return image_bytes  # return raw bytes; save to file or convert to data URL as needed

    except openai.BadRequestError as e:
        error_message = str(e)
        if 'content_policy_violation' in error_message:
            start = error_message.find("'message': '") + len("'message': '")
            end = error_message.find("', 'param'")
            return error_message[start:end]
        return f"Bad request: {error_message}"

    except Exception as e:
        print(f"Image generation error: {e}")  # log it so you can actually see failures
        return None

# async def process_voice(voice):
#     try:
#         print(f"Opening file: {voice}")
#         async with aiofiles.open(voice, 'rb') as audio_file:
#             audio_data = await audio_file.read()
#             print("File read successfully, sending for transcription")
#             transcript = client.audio.transcriptions.create(
#                 model="whisper-1", 
#                 file=audio_data
#             )
#         print("Transcription received")
#         return transcript
#     except openai.BadRequestError as e:
#         print(f"BadRequestError: {e}")
#         return None, str(e)
#     except Exception as e:
#         print(f"Exception occurred: {e}")
#         return None, str(e)
