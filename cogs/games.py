import discord
from discord.ext import commands, bridge
import asyncio
import gamefunc.tictactoe as tictactoe
from gamefunc.snake import SnakeGame
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

    @bridge.bridge_command(description="Play Snake (use w/a/s/d to move)")
    async def snake(self, ctx):
        if self.bot.active_games.get(ctx.channel.id, False):
            await ctx.respond("A game is already in progress in this channel.")
            return
        game = SnakeGame()
        self.bot.active_games[ctx.channel.id] = True

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        game_over = False
        first = True
        while not game_over:
            board = "```" + game.render() + "```"
            if first:
                await ctx.respond(board)
                first = False
            else:
                await ctx.channel.send(board)
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            except asyncio.TimeoutError:
                await ctx.channel.send("Game Timed Out")
                break
            content = msg.content.lower()
            if content == 'w':
                game.direction = (0, -1)
            elif content == 's':
                game.direction = (0, 1)
            elif content == 'a':
                game.direction = (-1, 0)
            elif content == 'd':
                game.direction = (1, 0)
            game_over = not game.move()

        await ctx.channel.send("Game Over!")
        self.bot.active_games[ctx.channel.id] = False


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
