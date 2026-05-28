import discord
from discord.ext import commands
import os
import asyncio
import aiohttp
from colorama import Fore
from chatbotfunc.utils import fetch_message_history, async_chat_completion, split_message, format_error_message, encode_discord_image
from AIfunc.responses import analyze_image, generate_gpt_response
from ragfunc.memory import async_store_message, async_retrieve, async_store_document

RATE_LIMIT = 0.5


class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _should_respond(self, message) -> bool:
        if message.author == self.bot.user:
            return False
        if "Generated Image" in message.content:
            return False
        # Always respond when directly @mentioned, even outside allowed channels
        if self.bot.user in message.mentions:
            return True
        channel_ids_str = os.getenv("CHANNEL_IDS", "")
        if not channel_ids_str:
            return False
        allowed = [int(cid) for cid in channel_ids_str.split(',') if cid.strip()]
        if message.channel.id not in allowed:
            return False
        # In an allowed channel, stay quiet if the message is directed at a specific human
        human_mentions = [u for u in message.mentions if not u.bot]
        return len(human_mentions) == 0

    @staticmethod
    async def _download_file_as_text(url: str, filename: str) -> str | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(Fore.RED + f"Error downloading file: HTTP {response.status}" + Fore.RESET)
                    return None
                raw = await response.read()
        if filename.lower().endswith('.pdf'):
            try:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                pages = [page.extract_text() or "" for page in reader.pages]
                return "\n\n".join(p for p in pages if p.strip()) or None
            except Exception as e:
                print(Fore.RED + f"PDF extraction error: {e}" + Fore.RESET)
                return None
        try:
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return None

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user.name}')
        print(self.bot.chatgpt_behaviour)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if reaction.message.author != self.bot.user or user == self.bot.user:
            return
        messages = await fetch_message_history(reaction.message.channel, self.bot)
        last_bot_message = next((m for m in messages if m['role'] == 'assistant'), None)
        if not last_bot_message:
            return
        emoji_name = reaction.emoji.name if hasattr(reaction.emoji, 'name') else str(reaction.emoji)
        prompt = f"{user.display_name} has reacted to your last message with: {emoji_name}. What is your response? Stay in character"
        messages.append({"role": "user", "content": prompt})
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
            return
        if self.bot.active_games.get(message.channel.id, False):
            return

        image_processed = False
        if message.attachments and self._should_respond(message):
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    async with message.channel.typing():
                        print(f"Processing image: {attachment.filename}")
                        base64_image = await encode_discord_image(attachment.url)
                        instructions = message.content if message.content else "What's in this image?"
                        message_history = await fetch_message_history(message.channel, self.bot)
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

        # Store any supported text/code/pdf attachments in RAG and surface
        # their content directly in the immediate response.
        text_file_content = None
        if message.attachments:
            for attachment in message.attachments:
                fname = attachment.filename.lower()
                if any(fname.endswith(ext) for ext in ('.txt', '.py', '.md', '.js', '.ts', '.jsx', '.tsx',
                                                        '.json', '.csv', '.yaml', '.yml', '.html', '.css',
                                                        '.sh', '.toml', '.ini', '.cfg', '.pdf')):
                    text_file_content = await self._download_file_as_text(attachment.url, attachment.filename)
                    if text_file_content:
                        await async_store_document(message.channel.id, text_file_content, source=attachment.filename)
                        print(f"Stored {attachment.filename} in RAG memory")
                    break

        if self._should_respond(message):
            await async_store_message(message.channel.id, "user", message.content, message.id)

            async with message.channel.typing():
                query = message.content or ""
                rag_docs = await async_retrieve(message.channel.id, query, k=3, doc_type="document")
                rag_msgs = await async_retrieve(message.channel.id, query, k=3, doc_type="message")
                rag_context = rag_docs + rag_msgs or None

                message_history = await fetch_message_history(message.channel, self.bot)
                combined_content = message.content + ("\n" + text_file_content if text_file_content else "")
                message_history.append({"role": "user", "content": combined_content})
                gpt_response = await generate_gpt_response(
                    message_history, self.bot.chatgpt_behaviour, rag_context=rag_context
                )
                await async_store_message(message.channel.id, "assistant", gpt_response)
                for chunk in split_message(gpt_response):
                    await message.channel.send(chunk)
                    await asyncio.sleep(RATE_LIMIT)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f"`!{ctx.invoked_with}` is not a recognised command.")


def setup(bot):
    bot.add_cog(ChatCog(bot))
