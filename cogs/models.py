import logging

import discord
from discord.ext import bridge, commands

from chatbotfunc import model_settings as ms

logger = logging.getLogger("bot.models")

_DEFAULT = "__default__"
_TITLES = {"chat": "Chat model", "image": "Image model"}


def build_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🧠 Models",
        description="Pick from the dropdowns — changes apply to the whole bot right away.",
        color=0x5865F2,
    )
    for kind in ("chat", "image"):
        entry = ms.override(kind)
        value = f"`{ms.current(kind)}`"
        value += f"\n-# set by {entry['set_by']}" if entry else "\n-# default from .env"
        embed.add_field(name=_TITLES[kind], value=value, inline=True)
    return embed


class ModelSelect(discord.ui.Select):
    def __init__(self, kind: str, choices: list[tuple[str, str]]):
        self.kind = kind
        current = ms.current(kind)
        options = [
            discord.SelectOption(label=model, value=model, description=desc, default=(model == current))
            for model, desc in choices
        ]
        options.append(discord.SelectOption(
            label=f"Default ({ms.env_default(kind)})", value=_DEFAULT,
            description="Clear the override and use the .env setting",
        ))
        super().__init__(placeholder=f"{_TITLES[kind]}: {current}", options=options,
                         row=0 if kind == "chat" else 1)

    async def callback(self, interaction: discord.Interaction):
        picked = self.values[0]
        before = ms.current(self.kind)
        ms.set_model(self.kind, None if picked == _DEFAULT else picked, interaction.user.display_name)
        after = ms.current(self.kind)
        view = ModelView()
        await interaction.response.edit_message(embed=build_embed(), view=view)
        view.message = interaction.message
        if after != before:
            await interaction.followup.send(
                f"🔁 **{interaction.user.display_name}** switched the {_TITLES[self.kind].lower()} "
                f"from `{before}` to `{after}`."
            )


class ModelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.message: discord.Message | None = None
        self.add_item(ModelSelect("chat", ms.CHAT_CHOICES))
        self.add_item(ModelSelect("image", ms.IMAGE_CHOICES))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ModelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @bridge.bridge_command(name="model", description="See or switch the bot's chat and image models")
    async def model(self, ctx):
        view = ModelView()
        msg = await ctx.respond(embed=build_embed(), view=view)
        view.message = await msg.original_response() if hasattr(msg, "original_response") else msg


def setup(bot):
    bot.add_cog(ModelsCog(bot))
