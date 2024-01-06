import asyncio
import random

# Function to play Tic Tac Toe
async def play_tic_tac_toe(ctx, bot, player_symbol):
    # Initialize the game board
    game_board = [[' ' for _ in range(3)] for _ in range(3)]
    player_turn = True if player_symbol.upper() == 'X' else False
    bot_symbol = 'O' if player_symbol.upper() == 'X' else 'X'

    # Function to check for a winner
    def check_winner(board, symbol):
        for i in range(3):
            if all(board[i][j] == symbol for j in range(3)) or all(board[j][i] == symbol for j in range(3)):
                return True
        if board[0][0] == board[1][1] == board[2][2] == symbol or board[0][2] == board[1][1] == board[2][0] == symbol:
            return True
        return False

    # Function to check if the board is full
    def board_full(board):
        return all(all(cell != ' ' for cell in row) for row in board)

    # Function to print the game board
    def print_board(board):
        emoji_board = []
        for row in board:
            emoji_row = []
            for cell in row:
                if cell == ' ':
                    emoji_row.append(':white_large_square:')
                elif cell == 'X':
                    emoji_row.append(':regional_indicator_x:')
                else:
                    emoji_row.append(':o2:')
            emoji_board.append(' | '.join(emoji_row))
        return '\n'.join(emoji_board)

    # Function for the bot to make a move
    async def bot_move(board, player_symbol, bot_symbol):
        # Check if the player is about to win and block them
        for i in range(3):
            for j in range(3):
                if board[i][j] == ' ':
                    board[i][j] = player_symbol
                    if check_winner(board, player_symbol):
                        board[i][j] = bot_symbol
                        return (i, j)
                    board[i][j] = ' '

        # Choose a strategic move (e.g., center, corners)
        strategic_positions = [(0, 0), (0, 2), (2, 0), (2, 2), (1, 1)]
        available_strategic_positions = [pos for pos in strategic_positions if board[pos[0]][pos[1]] == ' ']
        if available_strategic_positions:
            return random.choice(available_strategic_positions)

        # Choose a random move as a fallback
        available_positions = [(i, j) for i in range(3) for j in range(3) if board[i][j] == ' ']
        if not available_positions:
            return None
        return random.choice(available_positions)

    # Main game loop
    while True:
        if player_turn:
            await ctx.send(f"Your turn ({player_symbol.upper()}):\n{print_board(game_board)}\nChoose a position (e.g., 'top left', 'middle').")
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                response = await bot.wait_for('message', check=check, timeout=60.0)
            except asyncio.TimeoutError:
                await ctx.send("Game timed out due to inactivity.")
                break

            position_map = {
                "top left": (0, 0), "top middle": (0, 1), "top right": (0, 2),
                "middle left": (1, 0), "middle": (1, 1), "middle right": (1, 2),
                "bottom left": (2, 0), "bottom middle": (2, 1), "bottom right": (2, 2)
            }

            position = position_map.get(response.content.lower())
            if position and game_board[position[0]][position[1]] == ' ':
                game_board[position[0]][position[1]] = player_symbol.upper()
                if check_winner(game_board, player_symbol.upper()):
                    await ctx.send(f"Congratulations, you won!\n{print_board(game_board)}")
                    break
                if board_full(game_board):
                    await ctx.send(f"It's a draw!\n{print_board(game_board)}")
                    break
                player_turn = False
            else:
                await ctx.send("Invalid move. Please try again.")
        else:
            # Pass the correct arguments to the bot_move function
            result = await bot_move(game_board, player_symbol.upper(), bot_symbol)
            if result:
                i, j = result
                game_board[i][j] = bot_symbol
                if check_winner(game_board, bot_symbol):
                    await ctx.send(f"Bot wins!\n{print_board(game_board)}")
                    break
                if board_full(game_board):
                    await ctx.send(f"It's a draw!\n{print_board(game_board)}")
                    break
                player_turn = True
            else:
                await ctx.send("Bot failed to make a move.")
                break
