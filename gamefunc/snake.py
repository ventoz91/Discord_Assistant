import random

class SnakeGame:
    def __init__(self, width=8, height=8):
        self.width = width
        self.height = height
        self.snake = [(width // 2, height // 2)]
        self.apple = self._place_apple()
        self.direction = (0, 0)

    def _place_apple(self):
        while True:
            apple = (random.randint(0, self.width - 1), random.randint(0, self.height - 1))
            if apple not in self.snake:
                return apple

    def move(self):
        head = self.snake[0]
        new_head = (head[0] + self.direction[0], head[1] + self.direction[1])

        # Check for game over conditions
        if new_head in self.snake or new_head[0] < 0 or new_head[0] >= self.width or new_head[1] < 0 or new_head[1] >= self.height:
            return False

        self.snake.insert(0, new_head)

        # Check if apple is eaten
        if new_head == self.apple:
            self.apple = self._place_apple()
        else:
            self.snake.pop()

        return True

    def render(self) -> str:
        grid = [['·'] * self.width for _ in range(self.height)]
        for i, (x, y) in enumerate(self.snake):
            grid[y][x] = '▣' if i == 0 else '█'
        grid[self.apple[1]][self.apple[0]] = '◆'
        return '\n'.join(''.join(row) for row in grid)