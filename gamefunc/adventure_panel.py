import discord
from gamefunc.adventure import AdventureGame


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
        exits = self.game.room.exits
        has_items = bool(self.game.room.items)
        won = self.game.won

        # Row 0: [·] [North] [·]
        self.add_item(_Placeholder(row=0))
        self.add_item(_DirButton("north", exits, row=0, lock=won))
        self.add_item(_Placeholder(row=0))

        # Row 1: [West] [Look] [East]
        self.add_item(_DirButton("west", exits, row=1, lock=won))
        self.add_item(_ActionButton("👁 Look", "look", row=1, lock=won))
        self.add_item(_DirButton("east", exits, row=1, lock=won))

        # Row 2: [·] [South] [·]
        self.add_item(_Placeholder(row=2))
        self.add_item(_DirButton("south", exits, row=2, lock=won))
        self.add_item(_Placeholder(row=2))

        # Row 3: [Pick Up] [Inventory] [Quit]
        self.add_item(_PickUpButton(row=3, enabled=has_items and not won))
        self.add_item(_ActionButton("🎒 Inventory", "inventory", row=3, lock=False))
        self.add_item(_QuitButton(row=3))

    def build_embed(self) -> discord.Embed:
        game = self.game
        room = game.room

        if game.won:
            color = discord.Color.gold()
            title = f"👑  {room.name}"
        else:
            color = discord.Color.dark_gray()
            title = f"🗺️  {room.name}"

        embed = discord.Embed(title=title, color=color)
        embed.description = f"```\n{room.art}\n```"
        embed.add_field(name="", value=room.description, inline=False)

        exits_str = "  ".join(f"`{d.upper()}`" for d in room.exits) or "*none*"
        embed.add_field(name="🚪 Exits", value=exits_str, inline=True)

        ground_str = "\n".join(f"· {i}" for i in room.items) or "*nothing*"
        embed.add_field(name="📦 On Ground", value=ground_str, inline=True)

        inv_str = "\n".join(f"· {i}" for i in game.inventory) or "*empty*"
        embed.add_field(name="🎒 Carrying", value=inv_str, inline=True)

        embed.add_field(name="📜 Log", value=f"*{game.log}*", inline=False)

        if game.won:
            embed.add_field(
                name="✨ Victory!",
                value=(
                    "You raise the Golden Crown above your head. "
                    "The throne room echoes with silence — and then, somehow, applause. "
                    "Your adventure is complete."
                ),
                inline=False,
            )

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
                await self.message.edit(content="*Adventure session timed out.*", view=self)
            except Exception:
                pass


def _check_author(interaction: discord.Interaction, game: AdventureGame) -> bool:
    return interaction.user.id == game.user_id


class _Placeholder(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(label="·", style=discord.ButtonStyle.secondary, disabled=True, row=row)


class _DirButton(discord.ui.Button):
    _LABELS = {"north": "⬆", "south": "⬇", "west": "⬅", "east": "➡"}

    def __init__(self, direction: str, exits: dict, row: int, lock: bool):
        available = direction in exits and not lock
        super().__init__(
            label=self._LABELS[direction],
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
        view.game.log = view.game.move(self.direction)
        await view._update(interaction)


class _ActionButton(discord.ui.Button):
    def __init__(self, label: str, action: str, row: int, lock: bool):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            disabled=lock,
            row=row,
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: AdventureView = self.view
        if not _check_author(interaction, view.game):
            await interaction.response.send_message("This isn't your adventure!", ephemeral=True)
            return
        if self.action == "look":
            view.game.log = view.game.look()
        elif self.action == "inventory":
            view.game.log = view.game.show_inventory()
        await view._update(interaction)


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


class _QuitButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(label="🚪 Quit", style=discord.ButtonStyle.danger, row=row)

    async def callback(self, interaction: discord.Interaction):
        view: AdventureView = self.view
        if not _check_author(interaction, view.game):
            await interaction.response.send_message("This isn't your adventure!", ephemeral=True)
            return
        await view._end_game(interaction, "Adventure ended.")
