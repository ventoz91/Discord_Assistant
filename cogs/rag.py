import discord
from discord.ext import commands, bridge
import logging
import aiohttp
import asyncio
import io

logger = logging.getLogger("bot.rag")
from ragfunc.memory import async_store_document, async_count, async_clear_documents, async_clear_all
from chatbotfunc.profiles import get_facts, delete_fact, clear_facts
from chatbotfunc.utils import fetch_message_history, split_message, SUPPORTED_DOC_EXTENSIONS
from AIfunc.responses import generate_gpt_response


class RAGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def _download_bytes(url: str) -> bytes | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.read() if resp.status == 200 else None

    @staticmethod
    def _pdf_to_text(pdf_bytes: bytes) -> str:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p for p in pages if p.strip())

    async def _file_to_text(self, url: str, filename: str) -> str | None:
        ext = ('.' + filename.rsplit('.', 1)[-1].lower()) if '.' in filename else ''
        raw = await self._download_bytes(url)
        if raw is None:
            return None
        if ext in PDF_EXTENSIONS:
            return await asyncio.to_thread(self._pdf_to_text, raw)
        try:
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return None

    # ── !learn / /learn ───────────────────────────────────────────────────────

    @commands.command(name="learn")
    async def learn_prefix(self, ctx, *, text: str = None):
        """Store text or an attached file as a searchable document."""
        content, source = await self._resolve_learn_input(ctx.message.attachments, text, None)
        if content is None:
            await ctx.send(f"Provide some text or attach a supported file ({', '.join(sorted(SUPPORTED_DOC_EXTENSIONS))}).")
            return
        n = await async_store_document(ctx.channel.id, content, source=source)
        await ctx.send(f"Stored **{n}** chunk{'s' if n != 1 else ''} from `{source}` in memory.")

    @discord.slash_command(name="learn", description="Store text or a file as a searchable document")
    async def learn_slash(
        self,
        ctx,
        text: discord.Option(str, "Text to store", required=False) = None,
        file: discord.Option(discord.Attachment, "File to store (.txt, .py, .pdf, etc.)", required=False) = None,
    ):
        await ctx.defer()
        try:
            content, source = await self._resolve_learn_input([], text, file)
            if content is None:
                await ctx.respond(f"Provide some text or attach a supported file ({', '.join(sorted(SUPPORTED_DOC_EXTENSIONS))}).")
                return
            n = await async_store_document(ctx.channel.id, content, source=source)
            await ctx.respond(f"Stored **{n}** chunk{'s' if n != 1 else ''} from `{source}` in memory.")
        except Exception as e:
            logger.exception("learn failed")
            await ctx.respond(f"Error storing document: {e}")

    async def _resolve_learn_input(self, attachments, text, slash_file):
        if slash_file is not None:
            ext = ('.' + slash_file.filename.rsplit('.', 1)[-1].lower()) if '.' in slash_file.filename else ''
            if ext not in SUPPORTED_DOC_EXTENSIONS:
                return None, None
            return await self._file_to_text(slash_file.url, slash_file.filename), slash_file.filename
        for att in attachments:
            ext = ('.' + att.filename.rsplit('.', 1)[-1].lower()) if '.' in att.filename else ''
            if ext in SUPPORTED_DOC_EXTENSIONS:
                return await self._file_to_text(att.url, att.filename), att.filename
        if text:
            return text, "text"
        return None, None

    # ── !memory / /memory ─────────────────────────────────────────────────────

    @bridge.bridge_command(name="memory", description="Show memory stats for this channel")
    async def memory(self, ctx):
        await ctx.defer()
        try:
            stats = await async_count(ctx.channel.id)
            await ctx.respond(f"**Memory — #{ctx.channel.name}**\nTotal stored chunks: `{stats['total']}`")
        except Exception as e:
            logger.exception("memory stats failed")
            await ctx.respond(f"Error reading memory stats: {e}")

    # ── !cleardocs / /cleardocs ───────────────────────────────────────────────

    @bridge.bridge_command(name="cleardocs", description="Remove all stored documents from memory (keeps message history)")
    async def cleardocs(self, ctx):
        await ctx.defer()
        try:
            n = await async_clear_documents(ctx.channel.id)
            await ctx.respond(f"Removed **{n}** document chunk{'s' if n != 1 else ''} from memory.")
        except Exception as e:
            logger.exception("cleardocs failed")
            await ctx.respond(f"Error clearing documents: {e}")

    # ── !summarize / /summarize ───────────────────────────────────────────────

    @bridge.bridge_command(name="summarize", description="TL;DR of recent conversation in this channel")
    async def summarize(self, ctx):
        await ctx.defer()
        try:
            history = await fetch_message_history(ctx.channel, self.bot)
            if not history:
                await ctx.respond("No conversation history found to summarize.")
                return
            history.append({
                "role": "user",
                "content": "Give me a concise TL;DR of this conversation. Cover the main topics, key points, and anything notable. Be brief.",
            })
            summary = await generate_gpt_response(history, self.bot.chatgpt_behaviour)
            chunks = split_message(f"**TL;DR — #{ctx.channel.name}**\n{summary}")
            await ctx.respond(chunks[0])
            for chunk in chunks[1:]:
                await ctx.channel.send(chunk)
        except Exception as e:
            logger.exception("summarize failed")
            await ctx.respond(f"Error generating summary: {e}")

    # ── !missed / /missed ─────────────────────────────────────────────────────

    @bridge.bridge_command(name="missed", description="Summarize what happened since you were last here")
    async def missed(self, ctx):
        await ctx.defer()
        try:
            # Find when the user last spoke in this channel
            invoked_at = getattr(getattr(ctx, 'message', None), 'created_at', None)
            raw = [m async for m in ctx.channel.history(limit=500, oldest_first=False)]

            cutoff = None
            for msg in raw:
                if msg.author.id == ctx.author.id:
                    if invoked_at and msg.created_at >= invoked_at:
                        continue
                    cutoff = msg
                    break

            if cutoff:
                since_msgs = [m for m in raw if m.created_at > cutoff.created_at
                              and not (invoked_at and m.created_at >= invoked_at and m.author.id == ctx.author.id)]
                since_label = f"<t:{int(cutoff.created_at.timestamp())}:t>"
            else:
                since_msgs = raw
                since_label = "the start of recorded history here"

            if not since_msgs:
                await ctx.respond("Nothing happened since you were last here.")
                return

            lines = []
            for msg in reversed(since_msgs[:100]):
                if not msg.content:
                    continue
                name = "Ralph" if msg.author == self.bot.user else msg.author.display_name
                lines.append(f"{name}: {msg.content[:300]}")

            if not lines:
                await ctx.respond("Nothing to catch you up on.")
                return

            summary = await generate_gpt_response(
                [{"role": "user", "content": (
                    f"Summarize for {ctx.author.display_name} what happened in this Discord channel "
                    f"since {since_label}. Be in character. Be concise and punchy — highlight "
                    f"anything interesting, funny, or important.\n\nCHANNEL LOG:\n" + "\n".join(lines)
                )}],
                self.bot.chatgpt_behaviour,
            )
            chunks = split_message(f"**What you missed:**\n{summary}")
            await ctx.respond(chunks[0])
            for chunk in chunks[1:]:
                await ctx.channel.send(chunk)
        except Exception as e:
            logger.exception("missed failed")
            await ctx.respond(f"Error generating summary: {e}")

    # ── !whoami / !forget — user profile transparency ─────────────────────────

    @bridge.bridge_command(name="whoami", description="See what I remember about you")
    async def whoami(self, ctx):
        facts = await asyncio.to_thread(get_facts, ctx.author.id)
        if not facts:
            await ctx.respond(f"I haven't stored any facts about you yet, {ctx.author.display_name}.")
            return
        listing = "\n".join(f"{i}. {fact}" for i, fact in enumerate(facts, 1))
        await ctx.respond(
            f"**What I remember about {ctx.author.display_name}:**\n{listing}\n"
            f"-# Remove one with `!forget <number>`, or everything with `!forget all`."
        )

    @bridge.bridge_command(name="forget", description="Delete a stored fact about you: a number from !whoami, or 'all'")
    async def forget(self, ctx, target: str):
        if target.strip().lower() == "all":
            count = await asyncio.to_thread(clear_facts, ctx.author.id)
            if count:
                await ctx.respond(f"Forgotten — all {count} facts about you are gone.")
            else:
                await ctx.respond("There was nothing stored about you to forget.")
            return
        try:
            index = int(target)
        except ValueError:
            await ctx.respond("Give me a fact number from `!whoami`, or `all`.")
            return
        removed = await asyncio.to_thread(delete_fact, ctx.author.id, index)
        if removed:
            await ctx.respond(f"Forgotten: ~~{removed}~~")
        else:
            await ctx.respond(f"No fact #{index} — check `!whoami` for the current list.")

    # ── !clearall (prefix only — too destructive for accidental slash) ────────

    @commands.command(name="clearall")
    @commands.has_permissions(manage_messages=True)
    async def clearall_prefix(self, ctx):
        """Wipe all memory (messages + documents) for this channel. Requires Manage Messages."""
        try:
            await async_clear_all(ctx.channel.id)
            await ctx.send("All memory cleared for this channel.")
        except Exception as e:
            logger.exception("clearall failed")
            await ctx.send(f"Error clearing memory: {e}")


def setup(bot):
    bot.add_cog(RAGCog(bot))
