import os
from dotenv import load_dotenv
import discord
from discord.ext import bridge
from chatbotfunc.logger import setup_logging
from chatbotfunc.personalitymanager import PersonalityManager

load_dotenv()
setup_logging()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = bridge.Bot(command_prefix='!', intents=intents, help_command=None)

# Shared state accessible by all Cogs via self.bot
bot.active_games = {}
bot.channel_image_state = {}  # dict[channel_id, {"last_generated": bytes|None, "last_transformed": bytes|None}]
bot.personality_manager = PersonalityManager(env_path=".env")
bot.chatgpt_behaviour = bot.personality_manager.get_active()

for extension in [
    'cogs.chat',
    'cogs.images',
    'cogs.personality',
    'cogs.games',
    'cogs.servers',
    'cogs.fun',
    'cogs.rag',
    'cogs.reminders',
]:
    bot.load_extension(extension)

discord_token = os.getenv("DISCORD_TOKEN")
if not discord_token:
    raise ValueError("DISCORD_TOKEN not set in environment.")

bot.run(discord_token)
