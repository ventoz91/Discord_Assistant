import discord
from discord.ext import commands, bridge
import gamefunc.tictactoe as tictactoe
from gamefunc.snake import SnakeGame
from gamefunc.snake_panel import SnakeView
from gamefunc.adventure import AdventureGame
from gamefunc.adventure_panel import AdventureView


class GamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @bridge.bridge_command(description="Play Tic-Tac-Toe")
    async def game(self, ctx,
        player_symbol: bridge.BridgeOption(str, "Your symbol (X or O)", choices=["X", "O"], required=False) = None):
        if self.bot.active_games.get(ctx.channel.id, False):
            await ctx.respond("A game is already in progress in this channel.")
            return
        if player_symbol is None or player_symbol.upper() not in ['X', 'O']:
            await ctx.respond("Please enter 'X' or 'O' to start the game. For example, `!game X`.")
            return
        self.bot.active_games[ctx.channel.id] = True
        await ctx.defer()
        try:
            await tictactoe.play_tic_tac_toe(ctx, self.bot, player_symbol)
        finally:
            self.bot.active_games[ctx.channel.id] = False

    @bridge.bridge_command(description="Play Snake (use buttons to move)")
    async def snake(self, ctx):
        if self.bot.active_games.get(ctx.channel.id, False):
            await ctx.respond("A game is already in progress in this channel.")
            return
        self.bot.active_games[ctx.channel.id] = True
        try:
            game = SnakeGame()
            view = SnakeView(game, self.bot, ctx.channel.id, ctx.author.id)
            await ctx.defer()
            msg = await ctx.respond(embed=view.build_embed(), view=view)
            view.message = await msg.original_response() if hasattr(msg, "original_response") else msg
        except Exception:
            self.bot.active_games[ctx.channel.id] = False
            raise


    @bridge.bridge_command(description="Start an ASCII adventure game")
    async def adventure(self, ctx):
        if self.bot.active_games.get(ctx.channel.id, False):
            await ctx.respond("A game is already in progress in this channel.")
            return
        self.bot.active_games[ctx.channel.id] = True
        game = AdventureGame(user_id=ctx.author.id)
        view = AdventureView(game, self.bot, ctx.channel.id)
        await ctx.defer()
        msg = await ctx.respond(embed=view.build_embed(), view=view)
        view.message = await msg.original_response() if hasattr(msg, "original_response") else msg


def setup(bot):
    bot.add_cog(GamesCog(bot))
