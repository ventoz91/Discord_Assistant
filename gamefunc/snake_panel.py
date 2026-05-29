import discord
from gamefunc.snake import SnakeGame

_DIR_VECTORS: dict[str, tuple[int, int]] = {
    "⬆": (0, -1),
    "⬅": (-1, 0),
    "➡": (1, 0),
    "⬇": (0, 1),
}


class SnakeView(discord.ui.View):
    def __init__(self, game: SnakeGame, bot, channel_id: int, user_id: int):
        super().__init__(timeout=300)
        self.game = game
        self.bot = bot
        self.channel_id = channel_id
        self.user_id = user_id
        self.message: discord.Message | None = None
        self.score = 0
        self._over = False
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        d = self._over
        self.add_item(_Spacer(row=0))
        self.add_item(_DirButton("⬆", d, row=0))
        self.add_item(_Spacer(row=0))
        self.add_item(_DirButton("⬅", d, row=1))
        self.add_item(_Spacer(row=1))
        self.add_item(_DirButton("➡", d, row=1))
        self.add_item(_Spacer(row=2))
        self.add_item(_DirButton("⬇", d, row=2))
        self.add_item(_Spacer(row=2))
        self.add_item(_QuitButton(row=3, disabled=d))

    def build_embed(self) -> discord.Embed:
        if self._over:
            title = f"🐍 Game Over  ·  Score: {self.score}"
            color = discord.Color.red()
            footer = "Better luck next time"
        else:
            title = f"🐍 Snake  ·  Score: {self.score}"
            color = discord.Color.green()
            footer = "▣ head  █ body  ◆ apple  · empty"
        embed = discord.Embed(title=title, color=color)
        embed.description = f"```\n{self.game.render()}\n```"
        embed.set_footer(text=footer)
        return embed

    async def _move(self, interaction: discord.Interaction, direction: tuple):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        self.game.direction = direction
        alive = self.game.move()
        if not alive:
            self._over = True
            self.bot.active_games[self.channel_id] = False
            self.stop()
        else:
            self.score = len(self.game.snake) - 1
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        self.bot.active_games[self.channel_id] = False
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(content="*Session timed out.*", view=self)
            except Exception:
                pass


class _DirButton(discord.ui.Button):
    def __init__(self, label: str, disabled: bool, row: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary if not disabled else discord.ButtonStyle.secondary,
            disabled=disabled,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view._move(interaction, _DIR_VECTORS[self.label])


class _Spacer(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(label="·", style=discord.ButtonStyle.secondary, disabled=True, row=row)


class _QuitButton(discord.ui.Button):
    def __init__(self, row: int, disabled: bool = False):
        super().__init__(label="🚪 Quit", style=discord.ButtonStyle.danger, row=row, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        view: SnakeView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        view._over = True
        view.bot.active_games[view.channel_id] = False
        view.stop()
        view._rebuild()
        embed = view.build_embed()
        embed.set_footer(text="Game quit.")
        await interaction.response.edit_message(embed=embed, view=view)
