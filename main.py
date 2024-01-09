from openai import OpenAI
from funfunc.image_search import main as search_image
from funfunc.prompt import GPTSearchPrompt
from chatbotfunc.utils import fetch_message_history, async_chat_completion
from chatbotfunc.personalitymanager import PersonalityManager
from AIfunc.simulate import ConversationSimulator
from gamefunc.minecraft import MinecraftServer
from gamefunc.valheim import ValheimServer
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
#from discord import app_commands
#from discord.commands import Option
import openai
import random
import time
import asyncio
from colorama import init, Fore
import io
from io import BytesIO
import requests
from PIL import Image
import base64
import tempfile
import subprocess
import gamefunc.tictactoe as tictactoe
import aiohttp
import json
import requests

# Load environment variables
load_dotenv()

# Initialize colorama for colored console output
init(autoreset=True)

# Initialize the personality manager
personality_manager = PersonalityManager()

# Global variable to track the game state
active_games = {}

# Global variable to track if !image command was used
image_command_used = False

# Global dictionary to store text file content for each channel
channel_file_contents = {}

# Global variable to store url for last generated image
last_generated_image_url = None

# Initialize Valheim server
valheim_server = ValheimServer()

# Initialize the OpenAI client with your API key
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key is None:
    raise ValueError("No OpenAI API key found. Make sure to set the OPENAI_API_KEY environment variable.")
client = OpenAI(api_key=openai_api_key)
openai.api_key = openai_api_key

# Initialize Discord intents and bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
#bot = commands.Bot(command_prefix='!', intents=discord.Intents.default())

# Rate limiting
RATE_LIMIT = 0.5

def format_error_message(error):
    try:
        # Check for OpenAI specific errors
        if isinstance(error, openai.error.OpenAIError):
            return f"OpenAI Error: {str(error)}"

        # Handling HTTP request errors
        elif hasattr(error, 'response') and error.response is not None:
            try:
                error_json = error.response.json()
                error_message = error_json.get('error', {}).get('message', 'No error message')
                return f"HTTP Error: {error_message}"
            except Exception as json_error:
                return f"Error in parsing HTTP response: {json_error}"

        # General error handling
        else:
            return f"General Error: {str(error)}"

    except Exception as e:
        # Log the original error and the exception in formatting
        print(f"Error in formatting the error: {e}, Original error: {error}")
        return "An unexpected error occurred in formatting the error."
        
# Load personalities directly into behaviours_list
behaviours_list = personality_manager.read_personalities_from_file()

# behaviour variable set
chatgpt_behaviour = personality_manager.get_random_personality()
transform_behaviour = os.getenv("TRANSFORM")

########################################
#####Refactor everything below this#####
########################################

# Determine if the bot should respond to the message
def should_bot_respond_to_message(message):
    channel_ids_str = os.getenv("CHANNEL_IDS")
    if not channel_ids_str:
        return False

    allowed_channel_ids = [int(channel_id) for channel_id in channel_ids_str.split(',')]
    # Check if the message is from the bot itself or from a channel not in the allowed list
    if message.author == bot.user or message.channel.id not in allowed_channel_ids:
        return False

    # Check for bot's own 'Generated Image' messages
    if "Generated Image" in message.content:
        return False

    mentioned_users = [user for user in message.mentions if not user.bot]
    if mentioned_users or not (bot.user in message.mentions or message.channel.id in allowed_channel_ids):
        return False

    return (bot.user in message.mentions or message.channel.id in allowed_channel_ids)


# Split message into chunks of a specified maximum length
def split_message(message_content, max_length=1500):
    if len(message_content) <= max_length:
        return [message_content]

    # Splitting at sentence boundaries for better readability
    sentences = message_content.split(". ")
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_length:
            current_chunk += sentence + ". "
        else:
            chunks.append(current_chunk)
            current_chunk = sentence + ". "

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
    
def read_source_code(file_path):
    try:
        with open(file_path, 'r') as file:
            return file.read()
    except Exception as e:
        print(Fore.RED + f"Error reading source file: {e}" + Fore.RESET)
        return None
    
# Process an image URL and return a base64 encoded string
async def encode_discord_image(image_url):
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
        
async def analyze_image(base64_image, instructions):
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

#function for downloading text files sent in chat    
async def download_text_file(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            else:
                print(Fore.RED + f"Error downloading text file: HTTP status {response.status}" + Fore.RESET)
                return None

################
#####events#####
################
            
# Event listener for when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}') 

@bot.event
async def on_reaction_add(reaction, user):
    # Check if the reaction is on a bot's message and not added by the bot itself
    if reaction.message.author == bot.user and user != bot.user:
        # Fetch the message history using the utility function
        messages = await fetch_message_history(reaction.message.channel, bot, channel_file_contents, include_file_content=False)

        # Find the last bot message from the history
        last_bot_message = next((msg for msg in messages if msg['role'] == 'assistant'), None)
        
        if last_bot_message:
            # Extract the emoji name
            emoji_name = reaction.emoji.name if hasattr(reaction.emoji, 'name') else str(reaction.emoji)
            
            # Prepare the prompt for OpenAI completion
            prompt = f"{user.display_name} has reacted to your last message with: {emoji_name}. What is your response?"
            messages += [{"role": "user", "content": prompt}, 
                         {"role": "assistant", "content": "What is your reply?"}]

            # Generate a response using the same personality as on_message
            try:
                max_tokens = int(os.getenv("MAX_TOKENS"))
                response = await async_chat_completion(
                    model=os.getenv("MODEL_CHAT"),
                    messages=messages,
                    temperature=1.5,
                    top_p=0.9,
                    max_tokens=max_tokens
                )
                if response.choices:
                    ai_response = response.choices[0].message.content
                    await reaction.message.channel.send(ai_response)
            except Exception as e:
                formatted_error = format_error_message(e)
                await reaction.message.channel.send(formatted_error)
                print(Fore.RED + formatted_error + Fore.RESET)

########################
#####Image Commands#####
########################
                
@bot.command()
async def generate(ctx, *, prompt: str = None):
    global last_generated_image_url

    if not prompt:
        await ctx.send("Please provide a prompt for the image generation.")
        return
    
    try:
        print(f"Creating image based on: {prompt}")
        async with ctx.typing():
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            last_generated_image_url = image_url
            image_data = requests.get(image_url).content
            image_file = BytesIO(image_data)
            image_file.seek(0)
            image_discord = discord.File(fp=image_file, filename='image.png')

        await ctx.send(f"Generated Image -- every image you generate costs $0.04 so please keep that in mind\nPrompt: {prompt}", file=image_discord)

    except openai.BadRequestError as e:
        # Extracting the relevant error message
        error_message = str(e)
        if 'content_policy_violation' in error_message:
            # Find the start and end of the important message
            start = error_message.find("'message': '") + len("'message': '")
            end = error_message.find("', 'param'")
            important_message = error_message[start:end]

            # Send the extracted message to the channel
            await ctx.send(f"Error: {important_message}")

    except Exception as e:
        formatted_error = format_error_message(e)
        await ctx.send(f"An error occurred during image generation: {formatted_error}")
        print(Fore.RED + formatted_error + Fore.RESET)
        
@bot.command()
async def transform(ctx, *, instructions: str):
    global last_generated_image_url  # Access the global variable

    if instructions.startswith("last"):
        if last_generated_image_url is None:
            await ctx.send("No previous image found. Use !generate first.")
            return
        instructions = instructions[len("last"):].strip()  # Modify the instructions
        attachment_url = last_generated_image_url  # Use the last image URL
    elif ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        attachment_url = attachment.url
    else:
        await ctx.send("Please attach an image or use 'last' for the last generated image.")
        return

    # Proceed with the transformation process using attachment_url
    async with ctx.typing():
        try:
            print(Fore.CYAN + f"Transforming image with instructions: {instructions}" + Fore.RESET)
            base64_image = await encode_discord_image(attachment_url)

            # Analyze the image and get its description
            description_result = await analyze_image(base64_image, "Describe this image, give detailed and accurate descriptions...")
            if 'choices' in description_result and description_result['choices']:
                original_description = description_result['choices'][0].get('message', {}).get('content', '')
                if not original_description.strip():
                    raise ValueError("Failed to generate an original description for the image.")
            else:
                raise ValueError("Invalid response format from image analysis.")

            print(Fore.BLUE + "Original Description: " + original_description + Fore.RESET)
            prompt = f"Rewrite the following description to incorporate the given transformation.\n\nOriginal Description: {original_description}\n\nTransformation: {instructions}\n\nTransformed Description:"

            # Use GPT to rewrite the description
            rewriting_result = await async_chat_completion(
                model="gpt-4",
                messages=[{"role": "system", "content": transform_behaviour},
                          {"role": "user", "content": prompt}],
                max_tokens=250
            )

            if rewriting_result.choices:
                modified_description = rewriting_result.choices[0].message.content.strip()
                print(Fore.GREEN + "Transformed Description: " + modified_description + Fore.RESET)

                # Generate a new image based on the modified description
                response = client.images.generate(
                    model="dall-e-3",
                    prompt=modified_description,
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                new_image_url = response.data[0].url
                new_image_data = requests.get(new_image_url).content
                new_image_file = BytesIO(new_image_data)
                new_image_file.seek(0)
                new_image_discord = discord.File(fp=new_image_file, filename='transformed_image.png')
                await ctx.send(f"Transformed Image:\nOriginal instructions: {instructions}", file=new_image_discord)

        except Exception as e:
            formatted_error = format_error_message(e)
            await ctx.send(f"An error occurred during the transformation: {formatted_error}")
            print(Fore.RED + formatted_error + Fore.RESET)

@bot.command()
async def image(ctx, *, query: str):
    try:
        result = search_image(query)  # Pass 'query' as an argument
        data = json.loads(result)
        if "image_url" in data:
            image_url = data["image_url"]
            await ctx.send(image_url)

            # Process the image for analysis (if you have this functionality)
            base64_image = await encode_discord_image(image_url)
            if base64_image:
                analysis_result = await analyze_image(base64_image, "Describe this image.")
                description = analysis_result.get("choices", [{}])[0].get("message", {}).get("content", "No description available.")
                await ctx.send(f"Image Description: {description}")
            else:
                await ctx.send("Could not encode image for analysis.")
        else:
            await ctx.send("Sorry, no images found.")

    except Exception as e:
        # Handle exceptions
        error_message = str(e)
        await ctx.send(f"Error fetching image: {error_message}")
        print(f"Error: {error_message}")

@bot.command()
async def variation(ctx):
    global last_generated_image_url

    if last_generated_image_url is None:
        await ctx.send("No previous image found. Use !generate first.")
        return

    async with ctx.typing():
        try:
            # Fetch the image from the URL
            response = requests.get(last_generated_image_url)
            image = Image.open(io.BytesIO(response.content))

            # Convert to PNG and ensure the size is less than 4 MB
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            buffered.seek(0)  # Reset buffer pointer to the beginning after saving

            # Resize the image if it's too large
            if buffered.getbuffer().nbytes > 4 * 1024 * 1024:
                image = image.resize((1024, 1024), Image.ANTIALIAS)
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                buffered.seek(0)

            # Create variations using the OpenAI API
            response = openai.images.create_variation(
                image=buffered.getvalue(),
                n=3,
                size="1024x1024",
            )

            # Check the structure of the response and extract image data appropriately
            if hasattr(response, 'data'):
                for image_data in response.data:
                    image_bytes = base64.b64decode(image_data["image"])
                    with io.BytesIO(image_bytes) as image_file:
                        image_file.seek(0)
                        discord_file = discord.File(fp=image_file, filename='variation.png')
                        await ctx.send(file=discord_file)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

##############################
#####Personality Commands#####    
##############################
            
@bot.command()
async def new(ctx, *, new_personality: str):
    if personality_manager.add_personality(new_personality):
        await ctx.send(f"New personality added: {new_personality}")
    else:
        await ctx.send("This personality already exists.")

@bot.command()
async def change(ctx, choice: int = None):
    global chatgpt_behaviour
    if choice is not None and 1 <= choice <= len(behaviours_list):
        chatgpt_behaviour = behaviours_list[choice - 1]
        await ctx.send(f"Behavior changed to: {chatgpt_behaviour}")
    else:
        chatgpt_behaviour = random.choice(behaviours_list)
        await ctx.send(f"Random behavior selected! New behavior is: {chatgpt_behaviour}")
        
@bot.command()
async def list(ctx):
    # Create a temporary file to store the list
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_file:
        temp_file_name = temp_file.name
        for index, behaviour in enumerate(behaviours_list, start=1):
            temp_file.write(f"{index}: {behaviour}\n")

    # Send the file in Discord
    with open(temp_file_name, 'rb') as file:
        await ctx.send("Available Personalities:", file=discord.File(file, 'personalities_list.txt'))

    # Optionally, delete the temporary file if you don't need it after sending
    os.remove(temp_file_name)
        
#######################
#####Discord Games#####
#######################
    
# Global variable to track the game state in each channel
active_games = {}

@bot.command()
async def game(ctx, player_symbol: str = None):
    global active_games

    # Check if a game is already in progress in this channel
    if active_games.get(ctx.channel.id, False):
        await ctx.send("A game is already in progress in this channel.")
        return

    # Check if the player_symbol is provided and valid
    if player_symbol is None or player_symbol.upper() not in ['X', 'O']:
        await ctx.send("Please enter 'X' or 'O' to start the game. For example, `!game X`.")
        return

    # Set the game state to True for this channel to indicate a game is in progress
    active_games[ctx.channel.id] = True

    try:
        # Call the Tic Tac Toe game function from tictactoe.py
        await tictactoe.play_tic_tac_toe(ctx, bot, player_symbol)
    finally:
        # Ensure the game state is set to False when the game ends
        active_games[ctx.channel.id] = False

###################################
#####Minecraft Server Commands#####
###################################
        
@bot.command()
async def start(ctx, server_type: str):
    server = MinecraftServer(ctx)
    await server.start_server(server_type.lower())

@bot.command()
async def stop(ctx, server_type: str):
    server = MinecraftServer(ctx)
    await server.stop_server(server_type.lower())

@bot.command()
async def restart(ctx, server_type: str):
    server = MinecraftServer(ctx)
    await server.restart_server(server_type.lower())

@bot.command()
async def players(ctx, server_type: str):
    server = MinecraftServer(ctx)
    await server.list_players(server_type.lower())

# @bot.slash_command(description="Stops a Minecraft server")
# async def stop(ctx, 
#                server_type: Option(str, "Choose server type", choices=["vanilla", "modded"], required=True)):
#     # Logic to stop the server based on server_type
#     await ctx.respond(f"Stopping {server_type} server...")

##########################
#####Valheim Commands#####
##########################
        
@bot.command()
async def start_valheim(ctx):
    response = valheim_server.start_server()
    await ctx.send(response) 

@bot.command()
async def stop_valheim(ctx):
    response = valheim_server.stop_server()
    await ctx.send(response)     

@bot.command()
async def valheim_status(ctx):
    response = valheim_server.server_status()
    await ctx.send(response)    

###########################
######For Fun Commands#####
###########################

#command will create a prompt for a google search then send a link to the google search
@bot.command()
async def prompt(ctx, *, topic: str):
    try:
        prompt_generator = GPTSearchPrompt(openai_api_key, os.getenv("MODEL_CHAT", "gpt-3.5-turbo"))
        search_query = await prompt_generator.generate_search_query(topic)
        if search_query:
            google_search_url = GPTSearchPrompt.construct_google_search_url(search_query)
            await ctx.send(google_search_url)
        else:
            await ctx.send("Failed to generate search query.")
    except Exception as e:
        await ctx.send(f"Error: {e}")
        print(f"Error: {e}")
        
#command will simulate a conversation between two random or two chosen bot personalities
@bot.command()
async def simulate(ctx, *args):
    # Default values
    turns = 6  # Default number of turns
    delay = 3  # Default delay in seconds

    # Check if enough arguments are provided
    if len(args) < 1:
        await ctx.send("Please provide a topic for the conversation.")
        return

    topic = args[-1]  # The last argument is always the topic
    personalities = args[:-1]  # The rest of the arguments are personality indices

    # Validate personality indices
    if len(personalities) > 2:
        await ctx.send("Please provide up to two personality indices followed by a topic.")
        return

    # Convert personality indices to integers
    try:
        personality_indices = [int(index) for index in personalities]
    except ValueError:
        await ctx.send("Please provide valid personality indices (as numbers).")
        return

    # Start the simulation with the provided topic and personalities
    simulator = ConversationSimulator(openai_api_key, os.getenv("MODEL_CHAT", "gpt-3.5-turbo"))
    conversation_lines = await simulator.simulate_conversation(ctx.channel, topic, personality_indices, turns, bot, channel_file_contents)
    for line in conversation_lines:
        message_chunks = split_message(line, 2000)
        for chunk in message_chunks:
            await ctx.send(chunk)
            await asyncio.sleep(delay)

#command creates a random sandwich from set list of ingredients
@bot.command()
async def sandwich(ctx):
    try:
        # Run the sandwich.py script and capture its output
        result = subprocess.run(['python', 'funfunc/sandwich.py'], capture_output=True, text=True, check=True)
        sandwich_description = result.stdout.strip()

        # Send the output as a message
        await ctx.send(sandwich_description)

    except subprocess.CalledProcessError as e:
        # In case of an error during script execution
        await ctx.send(f"Error generating sandwich: {e}")
        print(f"Error: {e}")

###########################################
#####MAIN MESSAGE EVENT HANDLING EVENT#####
###########################################
                
@bot.event
async def on_message(message):
    #initialize global variables
    global channel_file_contents
    global image_command_used
    
    # Remove source code from chat history at the beginning
    if channel_file_contents.get(message.channel.id):
        source_code = read_source_code('main.py')
        if source_code:
            channel_file_contents[message.channel.id] = channel_file_contents[message.channel.id].replace(source_code, "")
            print("Source code removed from chat history, Current history:" + "\n" + channel_file_contents[message.channel.id])
    
    # Initialize local variables
    combined_content = message.content
    text_file_processed = False
    text_file_content = None
    should_respond = False 
    
    # Process any commands that might be part of the message
    await bot.process_commands(message)

    # Prevent duplicate processing for commands
    if message.content.startswith(bot.command_prefix):
        return
        
    # Check if the bot is mentioned in the message
    is_mentioned = bot.user in message.mentions
       
    # Ignore messages sent by the bot itself
    if message.author == bot.user and not image_command_used:
        return

    # Ignore messages if a game is in progress
    if active_games.get(message.channel.id, False):
        return
        
    source_code = None
    if 'main.py' in message.content.lower():
        # Read the source code file
        source_code = read_source_code('main.py')
        if source_code:
            # Add source code to chat history
            channel_file_contents[message.channel.id] = source_code + "\n" + channel_file_contents.get(message.channel.id, "")
            print(channel_file_contents[message.channel.id])
        
    # Initialize a flag to indicate if the message contains an image
    image_processed = False

    # Check if the message contains any attachments
    if message.attachments:
        for attachment in message.attachments:
            # Check for text files and process them
            if attachment.filename.lower().endswith('.txt'):
                text_file_content = await download_text_file(attachment.url)
                if text_file_content:
                    combined_content += "\n" + text_file_content
                    channel_file_contents[message.channel.id] = text_file_content
                    text_file_processed = True

    # Check if the image was processed, if so, return to avoid duplicate processing
    if image_processed:
        return


    if text_file_processed or should_respond:
        messages = await fetch_message_history(message.channel, bot, channel_file_contents)

        if text_file_processed:
            messages.append({"role": "user", "content": combined_content})

        messages.append({"role": "assistant", "content": "What is your reply?"})

        try:
            max_tokens = int(os.getenv("MAX_TOKENS"))
            response = await async_chat_completion(
                model=os.getenv("MODEL_CHAT"),
                messages=messages,
                temperature=1.5,
                top_p=0.9,
                max_tokens=max_tokens
            )

            if response.choices:
                airesponse = response.choices[0].message.content
                for chunk in split_message(airesponse):
                    await message.channel.send(chunk)
                    time.sleep(RATE_LIMIT)

        except Exception as e:
            formatted_error = format_error_message(e)
            await message.channel.send(formatted_error)
            print(Fore.RED + formatted_error + Fore.RESET)        

            
    # Determine if the bot should react to this particular message
    should_respond = should_bot_respond_to_message(message)

    # Check if the message is in a channel where the bot responds to all messages
    always_respond_channel = message.channel.id in [int(cid) for cid in os.getenv("CHANNEL_IDS", "").split(',')]

    # Process image analysis only if the bot is mentioned with an image or in a specific channel
    if message.attachments and (is_mentioned or always_respond_channel):
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                async with message.channel.typing():
                    try:
                        print(Fore.CYAN + f"Processing image: {attachment.filename}" + Fore.RESET)
                        base64_image = await encode_discord_image(attachment.url)
                        instructions = message.content if message.content else "What’s in this image?"
                        analysis_result = await analyze_image(base64_image, instructions)
                        response_text = analysis_result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if response_text:
                            await message.channel.send(response_text)
                            print(Fore.MAGENTA + "Image analysis result: " + response_text + Fore.RESET)
                        else:
                            response_fail_message = "Sorry, I couldn't analyze the image."
                            await message.channel.send(response_fail_message)
                            print(Fore.YELLOW + response_fail_message + Fore.RESET)
                    except Exception as e:
                        formatted_error = format_error_message(e)
                        await message.channel.send(formatted_error)
                        print(Fore.RED + formatted_error + Fore.RESET)
        return  # Return after processing images to avoid duplicate responses

    # Continue with other responses if the bot should respond
    if should_respond or text_file_content:
        print("Processing response.")
        async with message.channel.typing():
            messages = await fetch_message_history(message.channel, bot, channel_file_contents)
            messages += [{"role": "user", "content": combined_content}, 
                         {"role": "assistant", "content": "What is your reply?"}]
            
            # Include text file content if available
            if text_file_content:
                messages += [{"role": "user", "content": text_file_content}]

            messages += [{"role": "assistant", "content": "What is your reply?"}]            
    
        # Initialize variables to store the response
        airesponse_chunks = []
        response = {}
        openai_api_error_occurred = False

        try:
            # Indicate in the Discord channel that the bot is processing a message
            async with message.channel.typing():
                # Process and respond to text messages
                messages = await fetch_message_history(message.channel, bot, channel_file_contents)
                messages = [{"role": "system", "content": chatgpt_behaviour}, {"role": "user", "content": "Here is the message history:"}] + messages
                messages += [{"role": "assistant", "content": "What is your reply?"}, {"role": "system", "content": chatgpt_behaviour}]
            
            # Generate a response using the OpenAI API
            try:
                max_tokens = int(os.getenv("MAX_TOKENS"))
                response = await async_chat_completion(
                    model=os.getenv("MODEL_CHAT"),
                    messages=messages,
                    temperature=1.5,
                    top_p=0.9,
                    max_tokens=max_tokens
                )
                if response.choices:
                    airesponse = response.choices[0].message.content
                    for chunk in split_message(airesponse):
                        await message.channel.send(chunk)
                        time.sleep(RATE_LIMIT)
            except Exception as e:
                print(f"Error generating response: {e}")
                await message.channel.send("An error occurred while generating a response.")

                # Log the chat history for debugging
                print('Chat history:')
                for msg in messages:
                    print(f'{Fore.GREEN}{msg["role"].capitalize()}: {Fore.YELLOW}{msg["content"]}{Fore.RESET}')

                # Set the max_tokens based on the type of response
                max_tokens = int(os.getenv("MAX_TOKENS"))

                # Generate a response using the OpenAI API
                response = await async_chat_completion(model=os.getenv("MODEL_CHAT"), messages=messages, temperature=1.5, top_p=0.9, max_tokens=max_tokens)
                # Print the complete API response for debugging
                #print("Complete API Response:", response)

                # Extract and print the token usage information
                if hasattr(response, 'usage') and hasattr(response.usage, 'total_tokens'):
                    total_tokens = response.usage.total_tokens
                    print(f"Total Tokens for text response: {total_tokens}")
                else:
                    print("Token usage information not available.")

                # Split the AI response into manageable chunks
                airesponse = response.choices[0].message.content
                airesponse_chunks = split_message(airesponse)
                # Introduce a delay based on the response length
                total_sleep_time = RATE_LIMIT * len(airesponse_chunks)
                await asyncio.sleep(total_sleep_time)

        except openai.OpenAIError as e:
            # Log and send OpenAI specific errors
            error_msg = f"Error: OpenAI API Error - {e}"
            print(Fore.RED + error_msg + Fore.RESET)
            airesponse = f"An error has occurred with your request. Please try again. Error details: {e}"
            openai_api_error_occurred = True
            await message.channel.send(airesponse)

        except Exception as e:
            # Log and send unexpected errors
            error_msg = f"Unexpected error: {e}"
            print(Fore.RED + error_msg + Fore.RESET)
            airesponse = "An unexpected error has occurred."

        # Send the response in chunks to avoid message limits
        if not openai_api_error_occurred:
            for chunk in airesponse_chunks:
                await message.channel.send(chunk)
                print(bot.user, ":", Fore.RED + chunk + Fore.RESET)
                time.sleep(RATE_LIMIT)
    else:
        print("No conditions met for the bot to respond")
    # Process any commands included in the message
    await bot.process_commands(message)

# Run the bot with your token
discord_bot_token = os.getenv("DISCORD_TOKEN")
if discord_bot_token is None:
    raise ValueError("No Discord bot token found. Make sure to set the DISCORD_BOT_TOKEN environment variable.")
bot.run(discord_bot_token)