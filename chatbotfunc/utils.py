import openai
import asyncio
import aiohttp
import logging
import os
import io
import re
import base64
from PIL import Image
from discord.ext import commands

logger = logging.getLogger("bot.utils")

SUPPORTED_DOC_EXTENSIONS = frozenset({
    '.txt', '.py', '.md', '.js', '.ts', '.jsx', '.tsx',
    '.json', '.csv', '.yaml', '.yml', '.html', '.css',
    '.sh', '.toml', '.ini', '.cfg', '.pdf',
})

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')


def describe_extras(message) -> str:
    """Placeholders for non-text content so attachment/sticker-only messages
    don't vanish from history — the model at least sees they happened."""
    parts = []
    for att in message.attachments:
        ctype = getattr(att, "content_type", None) or ""
        if ctype.startswith("image/") or att.filename.lower().endswith(IMAGE_EXTENSIONS):
            kind = "image"
        elif ctype.startswith("video/") or att.filename.lower().endswith(VIDEO_EXTENSIONS):
            kind = "video"
        else:
            kind = "file"
        parts.append(f"[shared {kind}: {att.filename}]")
    for sticker in getattr(message, "stickers", ()):
        parts.append(f"[sticker: {sticker.name}]")
    return " ".join(parts)


def split_message(message_content, max_length=1995):
    if not message_content.strip():
        return []
    if len(message_content) <= max_length:
        return [message_content]
    chunks = []
    parts = re.split(r'(```[\s\S]*?```)', message_content)
    current_chunk = ""
    for part in parts:
        if not part:
            continue
        if part.startswith("```") and part.endswith("```"):
            if len(part) <= max_length:
                if len(current_chunk) + len(part) + 1 <= max_length:
                    current_chunk += ("\n" if current_chunk else "") + part
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = part
            else:
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
                    line_len = len(line) + 1
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


def format_error_message(error):
    try:
        if isinstance(error, openai.OpenAIError):
            return f"OpenAI Error: {str(error)}"
        elif hasattr(error, 'response') and error.response is not None:
            try:
                error_json = error.response.json()
                error_message = error_json.get('error', {}).get('message', 'No error message')
                return f"HTTP Error: {error_message}"
            except Exception as json_error:
                return f"Error in parsing HTTP response: {json_error}"
        else:
            return f"General Error: {str(error)}"
    except Exception as e:
        logger.error("format_error_message failed: %s | original: %s", e, error)
        return "An unexpected error occurred in formatting the error."


def _jpeg_b64(raw: bytes) -> str:
    """Decode raw image bytes with PIL, cap at 1000px, return base64 JPEG."""
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    if max(image.size) > 1000:
        image.thumbnail((1000, 1000))
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


async def encode_discord_image(image_url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                content = await resp.read()
        return _jpeg_b64(content)
    except Exception:
        logger.exception("encode_discord_image failed")


async def _extract_video_frame(video_url: str, ts: float | None = None) -> str | None:
    """Extract one frame at timestamp ts (seconds; None = first frame) via
    ffmpeg, which reads the URL directly. Returns base64 JPEG or None."""
    try:
        args = ["ffmpeg", "-loglevel", "error"]
        if ts:
            args += ["-ss", f"{ts:.3f}"]
        args += ["-i", video_url, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning("ffmpeg timed out extracting frame from %s", video_url)
            return None
        if proc.returncode != 0 or not out:
            logger.warning("ffmpeg frame extraction failed: %s", err.decode(errors="replace")[:200])
            return None
        return _jpeg_b64(out)
    except FileNotFoundError:
        logger.warning("ffmpeg not installed; cannot extract video frame")
        return None
    except Exception:
        logger.exception("frame extraction failed")
        return None


async def _ffprobe_duration(video_url: str) -> float | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        return float(out.strip())
    except Exception:
        return None


async def encode_video_frames(video_url: str, count: int | None = None) -> list[str]:
    """Sample frames evenly across a video (start → ~95% in) and return them
    as base64 JPEGs, oldest first. Falls back to just the first frame when the
    duration can't be probed; empty list if nothing could be extracted."""
    count = count or int(os.getenv("VIDEO_FRAMES", "5"))
    duration = await _ffprobe_duration(video_url)
    if not duration or duration <= 0 or count <= 1:
        frame = await _extract_video_frame(video_url)
        return [frame] if frame else []
    timestamps = [duration * 0.95 * i / (count - 1) for i in range(count)]
    frames = await asyncio.gather(*(_extract_video_frame(video_url, ts) for ts in timestamps))
    return [f for f in frames if f]


async def fetch_message_history(channel, bot: commands.Bot, exclude_message_id: int | None = None, return_cutoff: bool = False):
    history_length = int(os.getenv("HISTORYLENGTH", 30))
    message_history = []
    oldest_ts = None  # unix ts of the oldest message in the returned window
    async for message in channel.history(limit=history_length * 2):
        if message.id == exclude_message_id:
            continue
        if len(message_history) >= history_length:
            continue
        extras = describe_extras(message)
        content = f"{message.content} {extras}".strip() if extras else message.content
        if not content:
            continue
        if message.author != bot.user:
            role = "user"
            content = f"{message.author.display_name}: {content}"
        else:
            role = "assistant"
        message_history.append({"role": role, "content": content})
        oldest_ts = int(message.created_at.timestamp())
    message_history = message_history[::-1]
    if return_cutoff:
        return message_history, oldest_ts
    return message_history

async def async_chat_completion(*args, **kwargs):
    response = await asyncio.to_thread(openai.chat.completions.create, *args, **kwargs)
    return response

