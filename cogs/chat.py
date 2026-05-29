import discord
from discord.ext import commands
import logging
import os
import io
import json
import asyncio
import aiohttp
from chatbotfunc.utils import fetch_message_history, split_message, format_error_message, encode_discord_image, SUPPORTED_DOC_EXTENSIONS

logger = logging.getLogger("bot.chat")
from AIfunc.responses import analyze_image, generate_gpt_response, generate_image, transform_image
from ragfunc.memory import async_store_message, async_retrieve, async_store_document
from funfunc.web_search import web_search

RATE_LIMIT = 0.5

_GENERATE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "Generate and post an image to the chat. Use this when the user explicitly asks for a picture, image, drawing, or photo of something.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed image generation prompt describing what to create"}
            },
            "required": ["prompt"]
        }
    }
}

_TRANSFORM_TOOL = {
    "type": "function",
    "function": {
        "name": "transform_image",
        "description": "Transform or modify the most recent image in this channel. Use this when the user asks to change, edit, modify, or transform the current or last image.",
        "parameters": {
            "type": "object",
            "properties": {
                "instructions": {"type": "string", "description": "Instructions describing how to transform the image"}
            },
            "required": ["instructions"]
        }
    }
}

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "google_search",
        "description": "Search the web for current information. Use this for recent events, specific facts, or anything that may be outside your training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"]
        }
    }
}

async def _execute_search(args: dict) -> str:
    return await web_search(args.get("query", ""))


class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._channel_queues: dict[int, asyncio.Queue] = {}
        self._channel_workers: dict[int, asyncio.Task] = {}

    def _should_respond(self, message) -> bool:
        if message.author == self.bot.user:
            return False
        if self.bot.user in message.mentions:
            return True
        channel_ids_str = os.getenv("CHANNEL_IDS", "")
        if not channel_ids_str:
            return False
        allowed = [int(cid) for cid in channel_ids_str.split(',') if cid.strip()]
        if message.channel.id not in allowed:
            return False
        human_mentions = [u for u in message.mentions if not u.bot]
        return len(human_mentions) == 0

    @staticmethod
    async def _download_file_as_text(url: str, filename: str) -> str | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error("file download failed: HTTP %d", response.status)
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
                logger.exception("PDF extraction error")
                return None
        try:
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return None

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Logged in as %s | personality: %s", self.bot.user.name, self.bot.chatgpt_behaviour)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if os.getenv("REACTION_RESPONSES", "true").lower() != "true":
            return
        if reaction.message.author != self.bot.user or user == self.bot.user:
            return

        channel = reaction.message.channel
        channel_behaviour = (
            self.bot.personality_manager.get_channel_personality(channel.id)
            or self.bot.chatgpt_behaviour
        )

        message_history = await fetch_message_history(channel, self.bot)
        if not any(m['role'] == 'assistant' for m in message_history):
            return

        emoji_name = reaction.emoji.name if hasattr(reaction.emoji, 'name') else str(reaction.emoji)
        prompt = f"{user.display_name} reacted to your last message with {emoji_name}. Respond in character."

        rag_docs = await async_retrieve(channel.id, emoji_name, k=int(os.getenv("RAG_DOC_CONTEXT", "5")), doc_type="document")
        rag_msgs = await async_retrieve(channel.id, emoji_name, k=int(os.getenv("RAG_MESSAGE_CONTEXT", 50)), doc_type="message")
        rag_context = rag_docs + rag_msgs or None

        message_history.append({"role": "user", "content": prompt})
        try:
            response = await generate_gpt_response(message_history, channel_behaviour, rag_context=rag_context)
            if response:
                await channel.send(response)
        except Exception as e:
            logger.exception("on_reaction_add failed")
            msg = format_error_message(e)
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Fast early returns — don't queue these
        if message.author == self.bot.user:
            return
        if message.content.startswith(self.bot.command_prefix):
            return
        if self.bot.active_games.get(message.channel.id, False):
            return

        # Queue message for sequential per-channel processing
        channel_id = message.channel.id
        if channel_id not in self._channel_queues:
            self._channel_queues[channel_id] = asyncio.Queue()
        await self._channel_queues[channel_id].put(message)

        worker = self._channel_workers.get(channel_id)
        if worker is None or worker.done():
            self._channel_workers[channel_id] = asyncio.create_task(
                self._process_queue(channel_id)
            )

    async def _process_queue(self, channel_id: int):
        queue = self._channel_queues[channel_id]
        while not queue.empty():
            message = await queue.get()
            try:
                await self._handle_message(message)
            except Exception as e:
                logger.exception("queue error in channel %d", channel_id)
            finally:
                queue.task_done()

    async def _handle_message(self, message):
        channel_behaviour = (
            self.bot.personality_manager.get_channel_personality(message.channel.id)
            or self.bot.chatgpt_behaviour
        )

        image_processed = False
        if message.attachments and self._should_respond(message):
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    async with message.channel.typing():
                        logger.info("processing image: %s", attachment.filename)
                        base64_image = await encode_discord_image(attachment.url)
                        instructions = message.content if message.content else "What's in this image?"
                        message_history = await fetch_message_history(message.channel, self.bot)
                        response_text = await analyze_image(
                            base64_image, instructions, message_history, channel_behaviour
                        )
                        sent_analysis = await message.channel.send(response_text or "Sorry, I couldn't analyze the image.")
                        if response_text:
                            await async_store_message(message.channel.id, "user", f"[shared image: {attachment.filename}] {instructions}", message.id)
                            await async_store_message(message.channel.id, "assistant", f"[image analysis: {attachment.filename}] {response_text}", sent_analysis.id)
                        image_processed = True
                        break

        if image_processed:
            return

        if message.attachments and self._should_respond(message):
            for attachment in message.attachments:
                fname = attachment.filename.lower()
                if any(fname.endswith(ext) for ext in SUPPORTED_DOC_EXTENSIONS):
                    text_file_content = await self._download_file_as_text(attachment.url, attachment.filename)
                    if text_file_content:
                        await async_store_document(message.channel.id, text_file_content, source=attachment.filename)
                        logger.info("stored %s in RAG memory", attachment.filename)
                    break

        if self._should_respond(message):
            await async_store_message(message.channel.id, "user", message.content, message.id)

            async with message.channel.typing():
                query = message.content or ""

                # Fetch direct history first so we know the recency cutoff. RAG
                # message retrieval is then restricted to entries older than the
                # oldest in-history message, so it surfaces relevant *older*
                # context instead of re-sending what history already contains.
                message_history, history_cutoff_ts = await fetch_message_history(
                    message.channel, self.bot, exclude_message_id=message.id, return_cutoff=True
                )

                rag_docs = await async_retrieve(message.channel.id, query, k=int(os.getenv("RAG_DOC_CONTEXT", "5")), doc_type="document")
                rag_msgs = await async_retrieve(message.channel.id, query, k=int(os.getenv("RAG_MESSAGE_CONTEXT", 50)), doc_type="message", before_ts=history_cutoff_ts)
                rag_context = rag_docs + rag_msgs or None

                message_history.append({"role": "user", "content": message.content})

                ch_state = self.bot.channel_image_state.get(message.channel.id, {})
                tools = [_GENERATE_TOOL, _SEARCH_TOOL]
                if ch_state.get("last_transformed") or ch_state.get("last_generated"):
                    tools.append(_TRANSFORM_TOOL)

                gpt_response, tool_calls = await generate_gpt_response(
                    message_history, channel_behaviour, rag_context=rag_context, tools=tools,
                    auto_resolve={"google_search": _execute_search}
                )

                for tc in tool_calls:
                    if tc.function.name == "generate_image":
                        prompt = json.loads(tc.function.arguments).get("prompt", "")
                        image_result = await generate_image(prompt)
                        if isinstance(image_result, bytes):
                            self.bot.channel_image_state.setdefault(message.channel.id, {})["last_generated"] = image_result
                            file = discord.File(io.BytesIO(image_result), filename="generated.png")
                            img_msg = await message.channel.send("Generated Image", file=file)
                            await async_store_message(message.channel.id, "assistant", f"[generated image for prompt: {prompt}]", img_msg.id)
                        elif isinstance(image_result, str):
                            await message.channel.send(image_result)

                    elif tc.function.name == "transform_image":
                        instructions = json.loads(tc.function.arguments).get("instructions", "")
                        last_image = ch_state.get("last_transformed") or ch_state.get("last_generated")
                        image_result = await transform_image(last_image, instructions)
                        if isinstance(image_result, bytes):
                            self.bot.channel_image_state.setdefault(message.channel.id, {})["last_transformed"] = image_result
                            file = discord.File(io.BytesIO(image_result), filename="transformed.png")
                            img_msg = await message.channel.send("Transformed Image", file=file)
                            await async_store_message(message.channel.id, "assistant", f"[transformed image: {instructions}]", img_msg.id)
                        elif isinstance(image_result, str):
                            await message.channel.send(image_result)

                if gpt_response:
                    chunks = split_message(gpt_response)
                    sent = await message.channel.send(chunks[0])
                    await asyncio.sleep(RATE_LIMIT)
                    await async_store_message(message.channel.id, "assistant", gpt_response, sent.id)
                    for chunk in chunks[1:]:
                        await message.channel.send(chunk)
                        await asyncio.sleep(RATE_LIMIT)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f"`!{ctx.invoked_with}` is not a recognised command.")


def setup(bot):
    bot.add_cog(ChatCog(bot))
