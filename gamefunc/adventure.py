import copy
from dataclasses import dataclass, field

MAP_W = 55
MAP_H = 23
VIEWPORT_W = 33
VIEWPORT_H = 15
WIN_ITEM = "Golden Crown"

DIRECTION_VECTORS = {
    "n":  ( 0, -1),
    "s":  ( 0,  1),
    "w":  (-1,  0),
    "e":  ( 1,  0),
    "nw": (-1, -1),
    "ne": ( 1, -1),
    "sw": (-1,  1),
    "se": ( 1,  1),
}


@dataclass
class Item:
    x: int
    y: int
    symbol: str
    name: str


def _build_map() -> list[list[str]]:
    grid = [['#'] * MAP_W for _ in range(MAP_H)]

    rooms = [
        ( 1,  1, 10,  5),   # A — start
        (15,  1, 35,  5),   # B
        (40,  1, 53,  5),   # C
        ( 1, 10, 25, 16),   # D
        (29, 10, 53, 16),   # E
        (10, 19, 44, 21),   # F — end
    ]
    corridors = [
        (11,  3, 14,  3),   # A → B
        (36,  3, 39,  3),   # B → C
        ( 5,  6,  5,  9),   # A → D
        (20,  6, 20,  9),   # B → D
        (45,  6, 45,  9),   # C → E
        (26, 13, 28, 13),   # D → E
        (12, 17, 12, 18),   # D → F
        (40, 17, 40, 18),   # E → F
    ]

    for x1, y1, x2, y2 in rooms + corridors:
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                grid[y][x] = '.'

    return grid


_BASE_MAP: list[list[str]] = _build_map()

_INITIAL_ITEMS: list[Item] = [
    Item( 3,  3, '!', 'Torch'),
    Item(25,  2, '/', 'Old Sword'),
    Item(48,  3, '*', 'Iron Key'),
    Item(10, 13, '[', 'Dented Shield'),
    Item(42, 12, ';', 'Holy Symbol'),
    Item(27, 20, '^', 'Golden Crown'),
]


class AdventureGame:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.px = 5
        self.py = 3
        self.inventory: list[str] = []
        self.items: list[Item] = copy.deepcopy(_INITIAL_ITEMS)
        self.map: list[list[str]] = [row[:] for row in _BASE_MAP]
        self.log = "You descend into the dungeon. The Golden Crown awaits somewhere in the depths."
        self.won = False
        self.steps = 0

    def is_passable(self, x: int, y: int) -> bool:
        return 0 <= y < MAP_H and 0 <= x < MAP_W and self.map[y][x] == '.'

    def move(self, direction: str) -> str:
        dx, dy = DIRECTION_VECTORS[direction]
        nx, ny = self.px + dx, self.py + dy
        if not self.is_passable(nx, ny):
            return "Your way is blocked."
        self.px, self.py = nx, ny
        self.steps += 1
        item = self._item_at(nx, ny)
        if item:
            return f"You see {item.name} [{item.symbol}] here."
        return ""

    def pick_up(self) -> str:
        item = self._item_at(self.px, self.py)
        if not item:
            return "There is nothing here to pick up."
        self.items.remove(item)
        self.inventory.append(item.name)
        if item.name == WIN_ITEM:
            self.won = True
            return "You raise the Golden Crown. The dungeon shudders. Victory is yours."
        return f"You pick up the {item.name}."

    def look(self) -> str:
        item = self._item_at(self.px, self.py)
        nearby = [
            i.name for i in self.items
            if abs(i.x - self.px) <= 3 and abs(i.y - self.py) <= 3 and i is not item
        ]
        parts = []
        if item:
            parts.append(f"At your feet: {item.name} [{item.symbol}].")
        if nearby:
            parts.append(f"Nearby: {', '.join(nearby)}.")
        parts.append(f"Steps taken: {self.steps}.")
        return " ".join(parts)

    def show_inventory(self) -> str:
        if not self.inventory:
            return "Your pack is empty."
        return "Carrying: " + ", ".join(self.inventory) + "."

    def _item_at(self, x: int, y: int) -> Item | None:
        return next((i for i in self.items if i.x == x and i.y == y), None)

    def render_viewport(self) -> str:
        vx = max(0, min(self.px - VIEWPORT_W // 2, MAP_W - VIEWPORT_W))
        vy = max(0, min(self.py - VIEWPORT_H // 2, MAP_H - VIEWPORT_H))
        lines = []
        for row in range(vy, vy + VIEWPORT_H):
            line = []
            for col in range(vx, vx + VIEWPORT_W):
                if row == self.py and col == self.px:
                    line.append('@')
                else:
                    item = self._item_at(col, row)
                    line.append(item.symbol if item else self.map[row][col])
            lines.append(''.join(line))
        return '\n'.join(lines)
