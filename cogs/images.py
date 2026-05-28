import discord
from discord.ext import commands, bridge
import io
from io import BytesIO
import aiohttp
import json
from PIL import Image
from colorama import Fore
from AIfunc.responses import generate_image, transform_image, analyze_image
from funfunc.image_search import main as search_image
from chatbotfunc.utils import format_error_message, encode_discord_image


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
            self.bot.last_generated_image_bytes = image_bytes
            await ctx.respond(
                f"Generated Image -- every image you generate costs $0.04 so please keep that in mind\nPrompt: {prompt}",
                file=discord.File(fp=BytesIO(image_bytes), filename="image.png"),
            )
        except openai.BadRequestError as e:
            await ctx.respond(f"Request rejected: {e}")
        except Exception as e:
            msg = format_error_message(e)
            await ctx.respond(msg)
            print(Fore.RED + msg + Fore.RESET)

    async def _transform_impl(self, ctx, instructions: str, image_bytes: bytes):
        try:
            result = await transform_image(image_bytes, instructions)
            if isinstance(result, str):
                await ctx.respond(f"Could not transform image: {result}")
                return
            if not result:
                await ctx.respond("Failed to transform the image.")
                return
            await ctx.respond(
                f"Transformed Image:\nInstructions: {instructions}",
                file=discord.File(fp=BytesIO(result), filename="transformed_image.png"),
            )
        except Exception as e:
            msg = format_error_message(e)
            await ctx.respond(f"An error occurred during the transformation: {msg}")
            print(Fore.RED + msg + Fore.RESET)

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
                    analysis_result = await analyze_image(
                        base64_image, "Describe this image.",
                        [{"role": "user", "content": query}],
                        self.bot.chatgpt_behaviour,
                    )
                    description = (
                        analysis_result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "No description available.")
                    )
                    await ctx.channel.send(f"Image Description: {description}")
                else:
                    await ctx.channel.send("Could not encode image for analysis.")
            else:
                await ctx.respond("Sorry, no images found.")
        except Exception as e:
            await ctx.respond(f"Error fetching image: {e}")
            print(f"Error: {e}")

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
            if not self.bot.last_generated_image_bytes:
                await ctx.send("No previously generated image found. Use `!generate` first.")
                return
            image_bytes = self.bot.last_generated_image_bytes
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
        if use_last or attachment is None:
            if not self.bot.last_generated_image_bytes:
                await ctx.respond("No previously generated image found. Use `/generate` first.")
                return
            image_bytes = self.bot.last_generated_image_bytes
        else:
            image_bytes = await attachment.read()
        await self._transform_impl(ctx, instructions, image_bytes)


def setup(bot):
    bot.add_cog(ImagesCog(bot))
