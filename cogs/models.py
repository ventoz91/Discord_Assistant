import logging

import discord
from discord.ext import bridge, commands

from chatbotfunc import model_settings as ms
from chatbotfunc import usage

logger = logging.getLogger("bot.models")

_DEFAULT = "__default__"
_TITLES = {"chat": "Chat model", "image": "Image model", "size": "Image size", "quality": "Image quality"}
_ROWS = {"chat": 0, "image": 1, "size": 2, "quality": 3}


def build_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🧠 Models",
        description="Pick from the dropdowns — changes apply to the whole bot right away.\n"
                    "-# Size is the default; `/generate aspect:` or asking for a shape overrides it per image. "
                    "Transforms keep the source image's shape.",
        color=0x5865F2,
    )
    for kind in _TITLES:
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
        super().__init__(placeholder=f"{_TITLES[kind]}: {current}", options=options, row=_ROWS[kind])

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
        self.add_item(ModelSelect("size", ms.SIZE_CHOICES))
        self.add_item(ModelSelect("quality", ms.QUALITY_CHOICES))

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

    @bridge.bridge_command(name="model", description="See or switch the bot's chat model and image model, size and quality")
    async def model(self, ctx):
        view = ModelView()
        msg = await ctx.respond(embed=build_embed(), view=view)
        view.message = await msg.original_response() if hasattr(msg, "original_response") else msg

    @bridge.bridge_command(name="usage", description="Estimated OpenAI spend: today, 7 and 30 days")
    async def usage_cmd(self, ctx):
        await ctx.respond(embed=build_usage_embed())


def _money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.995 else f"{x * 100:.1f}¢"


def _breakdown(costs: dict, limit: int = 8) -> str:
    rows = sorted(costs.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return "\n".join(f"`{name}` — {_money(cost)}" for name, cost in rows if cost > 0) or "—"


def build_usage_embed() -> discord.Embed:
    today, week, month = usage.summarize(1), usage.summarize(7), usage.summarize(30)
    embed = discord.Embed(title="💸 OpenAI usage", color=0xF1C40F)
    for label, s in (("Today", today), ("Last 7 days", week), ("Last 30 days", month)):
        embed.add_field(name=label, value=f"**{_money(s['cost'])}**\n{s['calls']} calls · {s['images']} images",
                        inline=True)
    embed.add_field(name="30 days by feature", value=_breakdown(month["by_feature"]), inline=True)
    embed.add_field(name="30 days by model", value=_breakdown(month["by_model"]), inline=True)
    footer = "Estimates from list prices; token counts are exact."
    if month["unpriced"]:
        footer += f" {month['unpriced']} calls used a model with no price set."
    embed.set_footer(text=footer)
    return embed


def setup(bot):
    bot.add_cog(ModelsCog(bot))
