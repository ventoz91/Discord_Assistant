import discord
from discord.ext import commands
import openai
import io
from io import BytesIO
import base64
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

    @commands.command()
    async def generate(self, ctx, *, prompt: str = None):
        if not prompt:
            await ctx.send("Please provide a prompt for the image generation.")
            return
        async with ctx.channel.typing():
            try:
                image_bytes = await generate_image(prompt)
                if isinstance(image_bytes, str):
                    await ctx.send(f"Could not generate image: {image_bytes}")
                    return
                if not image_bytes:
                    raise ValueError("Failed to generate an image.")
                self.bot.last_generated_image_bytes = image_bytes
                await ctx.send(
                    f"Generated Image -- every image you generate costs $0.04 so please keep that in mind\nPrompt: {prompt}",
                    file=discord.File(fp=BytesIO(image_bytes), filename="image.png"),
                )
            except openai.BadRequestError as e:
                await ctx.send(f"Request rejected: {e}")
            except Exception as e:
                msg = format_error_message(e)
                await ctx.send(msg)
                print(Fore.RED + msg + Fore.RESET)

    @commands.command()
    async def transform(self, ctx, *, instructions: str):
        use_last = instructions.lower().startswith("last")
        if use_last:
            instructions = instructions[4:].strip()
            if not self.bot.last_generated_image_bytes:
                await ctx.send("No previously generated image found. Use `!generate` first.")
                return
            image_bytes = self.bot.last_generated_image_bytes
        elif ctx.message.attachments:
            image_bytes = None
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
                    file=discord.File(fp=BytesIO(result), filename="transformed_image.png"),
                )
            except Exception as e:
                msg = format_error_message(e)
                await ctx.send(f"An error occurred during the transformation: {msg}")
                print(Fore.RED + msg + Fore.RESET)

    @commands.command()
    async def image(self, ctx, *, query: str):
        try:
            result = search_image(query)
            data = json.loads(result)
            if "image_url" in data:
                image_url = data["image_url"]
                await ctx.send(image_url)
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
                    await ctx.send(f"Image Description: {description}")
                else:
                    await ctx.send("Could not encode image for analysis.")
            else:
                await ctx.send("Sorry, no images found.")
        except Exception as e:
            await ctx.send(f"Error fetching image: {e}")
            print(f"Error: {e}")

    @commands.command()
    async def variation(self, ctx):
        if self.bot.last_generated_image_bytes is None:
            await ctx.send("No previous image found. Use !generate first.")
            return
        async with ctx.typing():
            try:
                image = Image.open(io.BytesIO(self.bot.last_generated_image_bytes))
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                buffered.seek(0)
                if buffered.getbuffer().nbytes > 4 * 1024 * 1024:
                    image = image.resize((1024, 1024), Image.ANTIALIAS)
                    buffered = io.BytesIO()
                    image.save(buffered, format="PNG")
                    buffered.seek(0)
                response = openai.images.create_variation(
                    image=buffered.getvalue(),
                    n=3,
                    size="1024x1024",
                )
                if hasattr(response, 'data'):
                    for image_data in response.data:
                        image_bytes = base64.b64decode(image_data["image"])
                        with io.BytesIO(image_bytes) as image_file:
                            image_file.seek(0)
                            await ctx.send(file=discord.File(fp=image_file, filename='variation.png'))
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")


def setup(bot):
    bot.add_cog(ImagesCog(bot))
