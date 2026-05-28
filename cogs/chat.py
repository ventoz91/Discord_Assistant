import discord
from discord.ext import commands
import os
import asyncio
import aiohttp
from colorama import Fore
from chatbotfunc.utils import fetch_message_history, async_chat_completion, split_message, format_error_message, encode_discord_image
from AIfunc.responses import analyze_image, generate_gpt_response

RATE_LIMIT = 0.5


class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _should_respond(self, message) -> bool:
        channel_ids_str = os.getenv("CHANNEL_IDS")
        if not channel_ids_str:
            return False
        allowed = [int(cid) for cid in channel_ids_str.split(',')]
        if message.author == self.bot.user or message.channel.id not in allowed:
            return False
        if "Generated Image" in message.content:
            return False
        mentioned_users = [u for u in message.mentions if not u.bot]
        if mentioned_users or not (self.bot.user in message.mentions or message.channel.id in allowed):
            return False
        return True

    @staticmethod
    async def _download_text_file(url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                print(Fore.RED + f"Error downloading text file: HTTP status {response.status}" + Fore.RESET)
                return None

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user.name}')
        print(self.bot.chatgpt_behaviour)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if reaction.message.author != self.bot.user or user == self.bot.user:
            return
        messages = await fetch_message_history(
            reaction.message.channel, self.bot, self.bot.channel_file_contents, include_file_content=False
        )
        last_bot_message = next((m for m in messages if m['role'] == 'assistant'), None)
        if not last_bot_message:
            return
        emoji_name = reaction.emoji.name if hasattr(reaction.emoji, 'name') else str(reaction.emoji)
        prompt = f"{user.display_name} has reacted to your last message with: {emoji_name}. What is your response? Stay in character"
        messages += [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "What is your reply?"},
        ]
        try:
            max_tokens = int(os.getenv("MAX_TOKENS", 500))
            response = await async_chat_completion(
                model=os.getenv("MODEL_CHAT"),
                messages=messages,
                temperature=1.5,
                top_p=0.9,
                max_completion_tokens=max_tokens,
            )
            if response.choices:
                await reaction.message.channel.send(response.choices[0].message.content)
        except Exception as e:
            msg = format_error_message(e)
            await reaction.message.channel.send(msg)
            print(Fore.RED + msg + Fore.RESET)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if message.content.startswith(self.bot.command_prefix):
            await self.bot.process_commands(message)
            return
        if self.bot.active_games.get(message.channel.id, False):
            return

        if 'main.py' in message.content.lower():
            try:
                with open('main.py', 'r') as f:
                    source = f.read()
                self.bot.channel_file_contents[message.channel.id] = (
                    source + "\n" + self.bot.channel_file_contents.get(message.channel.id, "")
                )
                print("Source code added to chat history")
            except Exception as e:
                print(Fore.RED + f"Error reading source file: {e}" + Fore.RESET)

        image_processed = False
        if message.attachments and self._should_respond(message):
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    async with message.channel.typing():
                        print(f"Processing image: {attachment.filename}")
                        base64_image = await encode_discord_image(attachment.url)
                        instructions = message.content if message.content else "What's in this image?"
                        message_history = await fetch_message_history(
                            message.channel, self.bot, self.bot.channel_file_contents
                        )
                        analysis_result = await analyze_image(
                            base64_image, instructions, message_history, self.bot.chatgpt_behaviour
                        )
                        response_text = (
                            analysis_result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        )
                        await message.channel.send(response_text or "Sorry, I couldn't analyze the image.")
                        image_processed = True
                        break

        if image_processed:
            return

        text_file_content = None
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith('.txt'):
                    text_file_content = await self._download_text_file(attachment.url)
                    if text_file_content:
                        self.bot.channel_file_contents[message.channel.id] = text_file_content
                        print("Text file processed and added to chat history")

        if self._should_respond(message) or self.bot.user in message.mentions:
            async with message.channel.typing():
                message_history = await fetch_message_history(
                    message.channel, self.bot, self.bot.channel_file_contents
                )
                combined_content = message.content + "\n" + (text_file_content or "")
                message_history.append({"role": "user", "content": combined_content})
                gpt_response = await generate_gpt_response(message_history, self.bot.chatgpt_behaviour)
                for chunk in split_message(gpt_response):
                    await message.channel.send(chunk)
                    await asyncio.sleep(RATE_LIMIT)

        await self.bot.process_commands(message)


def setup(bot):
    bot.add_cog(ChatCog(bot))
