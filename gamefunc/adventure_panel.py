import discord
from gamefunc.adventure import AdventureGame, DIRECTION_VECTORS

_DIR_LABELS = {
    "nw": "↖", "n": "⬆", "ne": "↗",
    "w":  "⬅",            "e":  "➡",
    "sw": "↙", "s": "⬇", "se": "↘",
}

LEGEND = "@ you  ! torch  / weapon  [ armor  * key  ; relic  ^ crown"


class AdventureView(discord.ui.View):
    def __init__(self, game: AdventureGame, bot, channel_id: int):
        super().__init__(timeout=600)
        self.game = game
        self.bot = bot
        self.channel_id = channel_id
        self.message: discord.Message | None = None
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        game = self.game
        won = game.won

        def can_move(d: str) -> bool:
            if won:
                return False
            dx, dy = DIRECTION_VECTORS[d]
            return game.is_passable(game.px + dx, game.py + dy)

        # Row 0: NW  N  NE
        for d in ("nw", "n", "ne"):
            self.add_item(_DirButton(d, can_move(d), row=0))

        # Row 1: W  [·]  E
        self.add_item(_DirButton("w", can_move("w"), row=1))
        self.add_item(_Placeholder(row=1))
        self.add_item(_DirButton("e", can_move("e"), row=1))

        # Row 2: SW  S  SE
        for d in ("sw", "s", "se"):
            self.add_item(_DirButton(d, can_move(d), row=2))

        # Row 3: Pick Up  Inventory  Look  Quit
        has_item = bool(game._item_at(game.px, game.py)) and not won
        self.add_item(_PickUpButton(row=3, enabled=has_item))
        self.add_item(_ActionButton("🎒 Inv", "inventory", row=3))
        self.add_item(_ActionButton("🔍 Look", "look", row=3))
        self.add_item(_QuitButton(row=3))

    def build_embed(self) -> discord.Embed:
        game = self.game
        color = discord.Color.gold() if game.won else discord.Color.dark_gray()
        title = "👑  Victory!" if game.won else "⚔  Dungeon"

        embed = discord.Embed(title=title, color=color)
        embed.description = f"```\n{game.render_viewport()}\n```"

        inv_str = "  ".join(f"`{i}`" for i in game.inventory) or "*empty*"
        embed.add_field(name="🎒 Inventory", value=inv_str, inline=True)

        item_here = game._item_at(game.px, game.py)
        ground_str = f"`{item_here.symbol}` {item_here.name}" if item_here else "*nothing*"
        embed.add_field(name="📦 At Feet", value=ground_str, inline=True)

        embed.add_field(name="📜 Log", value=f"*{game.log}*", inline=False)

        if game.won:
            embed.add_field(
                name="",
                value="The dungeon falls silent as you claim the crown. Your legend is written.",
                inline=False,
            )

        embed.set_footer(text=f"({game.px},{game.py})  ·  {game.steps} steps  ·  {LEGEND}")
        return embed

    async def _update(self, interaction: discord.Interaction):
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _end_game(self, interaction: discord.Interaction, reason: str):
        self.bot.active_games[self.channel_id] = False
        self.stop()
        for child in self.children:
            child.disabled = True
        embed = self.build_embed()
        embed.set_footer(text=reason)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        self.bot.active_games[self.channel_id] = False
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(content="*Session timed out.*", view=self)
            except Exception:
                pass


def _check_author(interaction: discord.Interaction, game: AdventureGame) -> bool:
    return interaction.user.id == game.user_id


class _DirButton(discord.ui.Button):
    def __init__(self, direction: str, available: bool, row: int):
        super().__init__(
            label=_DIR_LABELS[direction],
            style=discord.ButtonStyle.primary if available else discord.ButtonStyle.secondary,
            disabled=not available,
            row=row,
        )
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: AdventureView = self.view
        if not _check_author(interaction, view.game):
            await interaction.response.send_message("This isn't your adventure!", ephemeral=True)
            return
        result = view.game.move(self.direction)
        if result:
            view.game.log = result
        await view._update(interaction)


class _Placeholder(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(label="·", style=discord.ButtonStyle.secondary, disabled=True, row=row)


class _PickUpButton(discord.ui.Button):
    def __init__(self, row: int, enabled: bool):
        super().__init__(
            label="📦 Pick Up",
            style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
            disabled=not enabled,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        view: AdventureView = self.view
        if not _check_author(interaction, view.game):
            await interaction.response.send_message("This isn't your adventure!", ephemeral=True)
            return
        view.game.log = view.game.pick_up()
        await view._update(interaction)


class _ActionButton(discord.ui.Button):
    def __init__(self, label: str, action: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: AdventureView = self.view
        if not _check_author(interaction, view.game):
            await interaction.response.send_message("This isn't your adventure!", ephemeral=True)
            return
        if self.action == "inventory":
            view.game.log = view.game.show_inventory()
        elif self.action == "look":
            view.game.log = view.game.look()
        await view._update(interaction)


class _QuitButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(label="🚪 Quit", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction: discord.Interaction):
        view: AdventureView = self.view
        if not _check_author(interaction, view.game):
            await interaction.response.send_message("This isn't your adventure!", ephemeral=True)
            return
        await view._end_game(interaction, "Adventure ended.")
