from openai import OpenAI
from gtts import gTTS
from AIfunc.responses import generate_gpt_response, analyze_image, generate_image, transform_image, start_monitoring
from funfunc.image_search import main as search_image
from funfunc.prompt import GPTSearchPrompt
from chatbotfunc.utils import fetch_message_history, async_chat_completion
from chatbotfunc.personalitymanager import PersonalityManager
from AIfunc.simulate import ConversationSimulator
from gamefunc.minecraft import MinecraftServer
from gamefunc.valheim import ValheimServer, EnshroudedServer
from gamefunc.snake import SnakeGame
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
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
import re

# Load environment variables
load_dotenv()

# Initialize colorama for colored console output
init(autoreset=True)

# Initialize the personality manager
personality_manager = PersonalityManager()

# Global variable to track the game state
active_games = {}

# Global dictionary to store text file content for each channel
channel_file_contents = {}

# Global variable to store bytes of last generated image
last_generated_image_bytes = None

# Initialize Game servers
valheim_server = ValheimServer()
enshrouded_server = EnshroudedServer()

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

# Rate limiting
RATE_LIMIT = 0.5

def format_error_message(error):
    try:
        # Check for OpenAI specific errors
        if isinstance(error, openai.OpenAIError):
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
personality = os.getenv("PERSONALITY")
chatgpt_behaviour = personality

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


def split_message(message_content, max_length=1995):
    if not message_content.strip():
        return []

    if len(message_content) <= max_length:
        return [message_content]

    chunks = []
    # Split into alternating plain-text and code-block parts
    parts = re.split(r'(```[\s\S]*?```)', message_content)
    current_chunk = ""

    for part in parts:
        if not part:
            continue

        if part.startswith("```") and part.endswith("```"):
            # Complete code block
            if len(part) <= max_length:
                if len(current_chunk) + len(part) + 1 <= max_length:
                    current_chunk += ("\n" if current_chunk else "") + part
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = part
            else:
                # Code block too big — split by lines, re-wrapping each chunk
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
                    line_len = len(line) + 1  # +1 for \n
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
            # Plain text — split by sentences
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
    observer = start_monitoring(bot)
    print(chatgpt_behaviour)

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
            prompt = f"{user.display_name} has reacted to your last message with: {emoji_name}. What is your response? Stay in character"
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
                    max_completion_tokens=max_tokens
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
    global last_generated_image_bytes

    if not prompt:
        await ctx.send("Please provide a prompt for the image generation.")
        return

    async with ctx.channel.typing():
        try:
            image_bytes = await generate_image(prompt)

            if isinstance(image_bytes, str):
                # generate_image returned a content policy message, not image data
                await ctx.send(f"Could not generate image: {image_bytes}")
                return

            if not image_bytes:
                raise ValueError("Failed to generate an image.")

            last_generated_image_bytes = image_bytes

            image_file = discord.File(fp=BytesIO(image_bytes), filename="image.png")
            await ctx.send(
                f"Generated Image -- every image you generate costs $0.04 so please keep that in mind\nPrompt: {prompt}",
                file=image_file,
            )

        except openai.BadRequestError as e:
            await ctx.send(f"Request rejected: {e}")
        except Exception as e:
            formatted_error = format_error_message(e)
            await ctx.send(formatted_error)
            print(Fore.RED + formatted_error + Fore.RESET)
        
@bot.command()
async def transform(ctx, *, instructions: str):
    global last_generated_image_bytes

    use_last = instructions.lower().startswith("last")
    if use_last:
        instructions = instructions[4:].strip()
        if not last_generated_image_bytes:
            await ctx.send("No previously generated image found. Use `!generate` first.")
            return
        image_bytes = last_generated_image_bytes
    elif ctx.message.attachments:
        pass  # handled inside the try block below
    else:
        await ctx.send("Please attach an image or use `!transform last <instructions>` to transform the last generated image.")
        return

    async with ctx.typing():
        try:
            if not use_last:
                attachment = ctx.message.attachments[0]
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        image_bytes = await resp.read()

            result = await transform_image(image_bytes, instructions)

            if isinstance(result, str):
                await ctx.send(f"Could not transform image: {result}")
                return
            if not result:
                await ctx.send("Failed to transform the image.")
                return

            await ctx.send(
                f"Transformed Image:\nInstructions: {instructions}",
                file=discord.File(fp=BytesIO(result), filename="transformed_image.png")
            )
        except Exception as e:
            formatted_error = format_error_message(e)
            await ctx.send(f"An error occurred during the transformation: {formatted_error}")
            print(Fore.RED + formatted_error + Fore.RESET)

@bot.command()
async def image(ctx, *, query: str):
    try:
        # Define a basic message history structure for the command context
        # This can be an empty list or a starting message
        command_message_history = [{"role": "user", "content": query}]
        result = search_image(query)  # Pass 'query' as an argument
        data = json.loads(result)
        if "image_url" in data:
            image_url = data["image_url"]
            await ctx.send(image_url)

            # Process the image for analysis
            base64_image = await encode_discord_image(image_url)
            if base64_image:
                analysis_result = await analyze_image(base64_image, "Describe this image.", command_message_history, chatgpt_behaviour)
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
    global last_generated_image_bytes

    if last_generated_image_bytes is None:
        await ctx.send("No previous image found. Use !generate first.")
        return

    async with ctx.typing():
        try:
            image = Image.open(io.BytesIO(last_generated_image_bytes))

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

percmd = bot.create_group("personality")

@bot.command()
async def new(ctx, *, new_personality: str):
    if personality_manager.add_personality(new_personality):
        await ctx.send(f"New personality added: {new_personality}")
    else:
        await ctx.send("This personality already exists.")

@percmd.command(description="create new personality and add to file")
async def new(ctx, *, new_personality = None):
    if new_personality is None:
        await ctx.respond("please specify a personality to add.")
    
    if personality_manager.add_personality(new_personality):
        await ctx.respond(f"New personality added: {new_personality}")
    else:
        await ctx.respond(f"personality '{new_personality}' already exists.")

@percmd.command(description="remove personality from list")
async def remove(ctx, *, index: int = None):
    if index is None:
        await ctx.respond("please specify a personality to remove.")
    removed_personality = personality_manager.remove_personality(index)
    if removed_personality:
        await ctx.respond(f"Remove Personality: {removed_personality}")
    else:
        await ctx.respond(f"Invalid index. Personality could not be found")

@bot.command()
async def change(ctx, choice: int = None):
    global chatgpt_behaviour
    if choice is not None and 1 <= choice <= len(behaviours_list):
        chatgpt_behaviour = behaviours_list[choice - 1]
        await ctx.send(f"Behavior changed to: {chatgpt_behaviour}")
    else:
        chatgpt_behaviour = random.choice(behaviours_list)
        await ctx.send(f"Random behavior selected! New behavior is: {chatgpt_behaviour}")

@percmd.command(description="change personality to one in file '/personality list' for options")
async def change(ctx, choice: int = None):
    global chatgpt_behaviour
    new_behaviours_list = personality_manager.personalities
    if choice is not None and 1 <= choice <= len(new_behaviours_list):
        chatgpt_behaviour = new_behaviours_list[choice - 1]
        await ctx.respond(f"Behavior changed to: {chatgpt_behaviour}")

        # Update PERSONALITY in .env file
        with open(".env", "r") as file:
            lines = file.readlines()
        with open(".env", "w") as file:
            for line in lines:
                if line.startswith("PERSONALITY="):
                    file.write(f"PERSONALITY={chatgpt_behaviour}\n")
                else:
                    file.write(line)
    else:
        chatgpt_behaviour = random.choice(new_behaviours_list)
        await ctx.respond(f"Random behavior selected! New behavior is: {chatgpt_behaviour}")

        # Update PERSONALITY in .env file
        with open(".env", "r") as file:
            lines = file.readlines()
        with open(".env", "w") as file:
            for line in lines:
                if line.startswith("PERSONALITY="):
                    file.write(f"PERSONALITY={chatgpt_behaviour}\n")
                else:
                    file.write(line)

@bot.command()
async def list(ctx):
    # Fetch the updated list of personalities
    updated_behaviours_list = personality_manager.personalities

    # Create a temporary file to store the updated list
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_file:
        temp_file_name = temp_file.name
        # Enumerate and write each personality in the updated list to the file
        for index, behaviour in enumerate(updated_behaviours_list, start=1):
            temp_file.write(f"{index}: {behaviour}\n")

    # Send the file in Discord
    with open(temp_file_name, 'rb') as file:
        await ctx.send("Available Personalities:", file=discord.File(file, 'personalities_list.txt'))

    # Delete the temporary file
    os.remove(temp_file_name)
    
@percmd.command(description="list personalities")
async def list(ctx):
    # Fetch the updated list of personalities
    updated_behaviours_list = personality_manager.personalities

    # Create a temporary file to store the updated list
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_file:
        temp_file_name = temp_file.name
        # Enumerate and write each personality in the updated list to the file
        for index, behaviour in enumerate(updated_behaviours_list, start=1):
            temp_file.write(f"{index}: {behaviour}\n")

    # Send the file in Discord
    with open(temp_file_name, 'rb') as file:
        await ctx.respond("Available Personalities:", file=discord.File(file, 'personalities_list.txt'))

    # Delete the temporary file
    os.remove(temp_file_name)

#######################
#####Discord Games#####
#######################

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

@bot.command()
async def snake(ctx):
    global active_games

    # Check if a game is already in progress in this channel
    if active_games.get(ctx.channel.id, False):
        await ctx.send("A game is already in progress in this channel.")
        return

    game = SnakeGame()
    active_games[ctx.channel.id] = True
    print(active_games)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    game_over = False
    while not game_over:
        await ctx.send("```" + game.render() + "```")
        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await ctx.send("Game Timed Out")
            break

        content = msg.content.lower()
        if content == 'w':
            game.direction = (0, -1)
        elif content == 's':
            game.direction = (0, 1)
        elif content == 'a':
            game.direction = (-1, 0)
        elif content == 'd':
            game.direction = (1, 0)

        game_over = not game.move()

    await ctx.send("Game Over!")
    active_games[ctx.channel.id] = False
    print(active_games)

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

##########################
#####Enshrouded Commands#####
##########################
        
@bot.command()
async def start_enshrouded(ctx):
    response = enshrouded_server.start_server()
    await ctx.send(response) 

@bot.command()
async def stop_enshrouded(ctx):
    response = enshrouded_server.stop_server('enshrouded_server.exe')
    await ctx.send(response)     


###########################
######For Fun Commands#####
###########################
    
@bot.command()
async def join(ctx):
    # Check if the author is connected to a voice channel
    if ctx.author.voice is None:
        await ctx.send("You are not connected to a voice channel.")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        return await ctx.voice_client.move_to(channel)

    await channel.connect()

# Command to leave a voice channel
@bot.command()
async def leave(ctx):
    await ctx.voice_client.disconnect()

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
    # Initialize global variables
    global channel_file_contents, chatgpt_behaviour
    
    # Prevent processing if the message is from the bot or a command
    if message.author == bot.user:
        return
    #if message.author == bot.user and not message.content.startswith("!generate"):
    #    return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return
    if active_games.get(message.channel.id, False):
        return

    # Handle source code exclusion from chat history
    if 'main.py' in message.content.lower():
        source_code = read_source_code('main.py')
        if source_code:
            channel_file_contents[message.channel.id] = source_code + "\n" + channel_file_contents.get(message.channel.id, "")
            print("Source code added to chat history")

    # Check if the message contains an image
    image_processed = False
    if message.attachments and should_bot_respond_to_message(message):
        for attachment in message.attachments:
            async with message.channel.typing():  # Bot starts typing
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    print(f"Processing image: {attachment.filename}")
                    base64_image = await encode_discord_image(attachment.url)
                    instructions = message.content if message.content else "What’s in this image?"
                    message_history = await fetch_message_history(message.channel, bot, channel_file_contents)
                    analysis_result = await analyze_image(base64_image, instructions, message_history, chatgpt_behaviour)
                    response_text = analysis_result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if response_text:
                        await message.channel.send(response_text)
                    else:
                        await message.channel.send("Sorry, I couldn't analyze the image.")
                    image_processed = True
                    break  # Break after processing the first image

    # If an image was processed, return to avoid further text processing
    if image_processed:
        return

    # Handle text file attachments
    text_file_content = None
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith('.txt'):
                text_file_content = await download_text_file(attachment.url)
                if text_file_content:
                    channel_file_contents[message.channel.id] = text_file_content
                    print("Text file processed and added to chat history")

    # Determine if the bot should respond
    should_respond = should_bot_respond_to_message(message) or bot.user in message.mentions
    if should_respond:
        async with message.channel.typing():  # Bot starts typing
            # Fetch message history and prepare it for generating response
            message_history = await fetch_message_history(message.channel, bot, channel_file_contents)
            combined_content = message.content + "\n" + (text_file_content or "")
            message_history.append({"role": "user", "content": combined_content})

            # Generate response using your function
            gpt_response = await generate_gpt_response(message_history, chatgpt_behaviour)
            for chunk in split_message(gpt_response):
                await message.channel.send(chunk)
                time.sleep(RATE_LIMIT)

    # TTS response in voice channel
    voice_client = discord.utils.get(bot.voice_clients, guild=message.guild)
    if voice_client and voice_client.is_connected():
        if message.author != bot.user and not message.content.startswith(bot.command_prefix):
            try:
                print("Fetching message history for TTS")
                message_history = await fetch_message_history(message.channel, bot, channel_file_contents)
                message_history.append({"role": "user", "content": message.content})
                gpt_response = await generate_gpt_response(message_history, chatgpt_behaviour)
                tts = gTTS(gpt_response, lang='en')
                tts_file = 'tts_response.mp3'
                tts.save(tts_file)
                if not voice_client.is_playing():
                    source = discord.FFmpegPCMAudio(executable="ffmpeg", source=tts_file)
                    voice_client.play(source, after=lambda x: os.remove(tts_file))
            except Exception as e:
                print(f"Error in generating or vocalizing GPT response: {e}")

    await bot.process_commands(message)

# Run the bot with your token
discord_bot_token = os.getenv("DISCORD_TOKEN")
if discord_bot_token is None:
    raise ValueError("No Discord bot token found. Make sure to set the DISCORD_BOT_TOKEN environment variable.")
bot.run(discord_bot_token)