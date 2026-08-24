import discord
from discord.ext import commands, bridge
import logging
import io
import os
import aiohttp
import json
import openai
from AIfunc.responses import generate_image, transform_image, analyze_image
from funfunc.image_search import main as search_image
from chatbotfunc.utils import format_error_message, encode_discord_image

logger = logging.getLogger("bot.images")


class ImagesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Shared logic ──────────────────────────────────────────────────────────

    async def _generate_impl(self, ctx, prompt: str):
        await ctx.defer()
        try:
            image_bytes = await generate_image(prompt)
            if isinstance(image_bytes, str):
                await ctx.respond(f"Could not generate image: {image_bytes}")
                return
            if not image_bytes:
                raise ValueError("Failed to generate an image.")
            self.bot.channel_image_state.setdefault(ctx.channel.id, {})["last_generated"] = image_bytes
            size = os.getenv("IMAGE_SIZE", "1024x1024")
            quality = os.getenv("IMAGE_QUALITY", "medium")
            await ctx.respond(
                f"Generated Image -- generation isn't free, keep that in mind (current settings: {size}, {quality} quality)\nPrompt: {prompt}",
                file=discord.File(fp=io.BytesIO(image_bytes), filename="image.png"),
            )
        except openai.BadRequestError as e:
            logger.warning("image request rejected by OpenAI: %s", e)
            await ctx.respond(f"Request rejected: {e}")
        except Exception as e:
            logger.exception("generate failed")
            msg = format_error_message(e)
            await ctx.respond(msg)

    async def _transform_impl(self, ctx, instructions: str, image_bytes: bytes):
        try:
            result = await transform_image(image_bytes, instructions)
            if isinstance(result, str):
                await ctx.respond(f"Could not transform image: {result}")
                return
            if not result:
                await ctx.respond("Failed to transform the image.")
                return
            self.bot.channel_image_state.setdefault(ctx.channel.id, {})["last_transformed"] = result
            await ctx.respond(
                f"Transformed Image:\nInstructions: {instructions}",
                file=discord.File(fp=io.BytesIO(result), filename="transformed_image.png"),
            )
        except Exception as e:
            logger.exception("transform failed")
            msg = format_error_message(e)
            await ctx.respond(f"An error occurred during the transformation: {msg}")

    async def _image_impl(self, ctx, query: str):
        await ctx.defer()
        try:
            result = search_image(query)
            data = json.loads(result)
            if "image_url" in data:
                image_url = data["image_url"]
                await ctx.respond(image_url)
                base64_image = await encode_discord_image(image_url)
                if base64_image:
                    description = await analyze_image(
                        base64_image, "Describe this image.",
                        [{"role": "user", "content": query}],
                        self.bot.chatgpt_behaviour,
                    ) or "No description available."
                    await ctx.channel.send(f"Image Description: {description}")
                else:
                    await ctx.channel.send("Could not encode image for analysis.")
            else:
                await ctx.respond("Sorry, no images found.")
        except Exception as e:
            logger.exception("image search failed")
            await ctx.respond(f"Error fetching image: {e}")

    # ── Prefix + slash bridge commands ────────────────────────────────────────

    @bridge.bridge_command(description="Generate an image with AI")
    async def generate(self, ctx, *, prompt: str):
        await self._generate_impl(ctx, prompt)

    @bridge.bridge_command(name="image", description="Search Google Images and describe the result")
    async def image_cmd(self, ctx, *, query: str):
        await self._image_impl(ctx, query)

    # ── Prefix-only transform (attachment handling differs for slash) ──────────

    @commands.command(name="transform")
    async def transform_prefix(self, ctx, *, instructions: str):
        use_last = instructions.lower().startswith("last")
        if use_last:
            instructions = instructions[4:].strip()
            state = self.bot.channel_image_state.get(ctx.channel.id, {})
            image_bytes = state.get("last_transformed") or state.get("last_generated")
            if not image_bytes:
                await ctx.send("No image in memory for this channel. Use `!generate` first.")
                return
        elif ctx.message.attachments:
            async with aiohttp.ClientSession() as session:
                async with session.get(ctx.message.attachments[0].url) as resp:
                    image_bytes = await resp.read()
        else:
            await ctx.send("Please attach an image or use `!transform last <instructions>` to transform the last generated image.")
            return
        async with ctx.typing():
            await self._transform_impl(ctx, instructions, image_bytes)

    # ── Slash-only transform (takes an explicit attachment option) ────────────

    @discord.slash_command(name="transform", description="Transform an image using AI")
    async def transform_slash(self, ctx,
        instructions: discord.Option(str, "What to do to the image"),
        attachment: discord.Option(discord.Attachment, "Image to transform", required=False) = None,
        use_last: discord.Option(bool, "Use the most recently generated image", required=False) = False):
        await ctx.defer()
        if use_last:
            state = self.bot.channel_image_state.get(ctx.channel.id, {})
            image_bytes = state.get("last_transformed") or state.get("last_generated")
            if not image_bytes:
                await ctx.respond("No image in memory for this channel. Use `/generate` first.")
                return
        elif attachment is not None:
            image_bytes = await attachment.read()
        else:
            await ctx.respond("Attach an image, or set `use_last:True` to transform the most recent image in this channel.")
            return
        await self._transform_impl(ctx, instructions, image_bytes)


def setup(bot):
    bot.add_cog(ImagesCog(bot))
