import os
from dotenv import load_dotenv
import discord
from discord.ext import bridge
from colorama import init
from chatbotfunc.personalitymanager import PersonalityManager

load_dotenv()
init(autoreset=True)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = bridge.Bot(command_prefix='!', intents=intents)

# Shared state accessible by all Cogs via self.bot
bot.active_games = {}
bot.last_generated_image_bytes = None
bot.personality_manager = PersonalityManager(filepath=".env")
bot.chatgpt_behaviour = bot.personality_manager.personalities[0] if bot.personality_manager.personalities else ""

for extension in [
    'cogs.chat',
    'cogs.images',
    'cogs.personality',
    'cogs.games',
    'cogs.servers',
    'cogs.fun',
    'cogs.rag',
]:
    bot.load_extension(extension)

discord_token = os.getenv("DISCORD_TOKEN")
if not discord_token:
    raise ValueError("DISCORD_TOKEN not set in environment.")

bot.run(discord_token)
