from dataclasses import dataclass, field


@dataclass
class Room:
    id: str
    name: str
    description: str
    art: str
    exits: dict   # {"north": room_id, ...}
    items: list = field(default_factory=list)


ROOMS: dict[str, "Room"] = {
    "cell": Room(
        id="cell",
        name="Prison Cell",
        description="Stone walls weep with moisture. The iron door hangs open — someone left in a hurry.",
        art=(
            "╔════════════════════╗\n"
            "║ ||| ||| ||| ||| | ║\n"
            "║                   ║\n"
            "║   [ You ]         ║\n"
            "║                   ║\n"
            "╚════════════════════╝"
        ),
        exits={"north": "corridor"},
        items=["Broken Shackle"],
    ),
    "corridor": Room(
        id="corridor",
        name="Dark Corridor",
        description="A long passage of rough-cut stone. Torchlight flickers from somewhere ahead.",
        art=(
            "╔════════════════════╗\n"
            "║  . . . . . . . .  ║\n"
            "║                   ║\n"
            "║     [ You ]       ║\n"
            "║                   ║\n"
            "╚════════════════════╝"
        ),
        exits={"south": "cell", "north": "guardroom", "east": "armory"},
        items=["Torch"],
    ),
    "armory": Room(
        id="armory",
        name="Armory",
        description="Weapon racks line the walls, mostly empty. A few useful things remain.",
        art=(
            "╔════════════════════╗\n"
            "║ /\\ /\\ /\\ /\\ /\\  ║\n"
            "║ || || || || ||    ║\n"
            "║                   ║\n"
            "║     [ You ]       ║\n"
            "╚════════════════════╝"
        ),
        exits={"west": "corridor"},
        items=["Old Sword", "Dented Shield"],
    ),
    "guardroom": Room(
        id="guardroom",
        name="Guard Room",
        description="A table covered in empty mugs and a half-eaten meal. The guards have vanished.",
        art=(
            "╔════════════════════╗\n"
            "║  _______________  ║\n"
            "║ |     TABLE     | ║\n"
            "║ |_______________| ║\n"
            "║     [ You ]       ║\n"
            "╚════════════════════╝"
        ),
        exits={"south": "corridor", "north": "hall"},
        items=["Iron Key", "Mug of Ale"],
    ),
    "hall": Room(
        id="hall",
        name="Great Hall",
        description="Vaulted ceilings disappear into shadow. A tattered banner hangs limp from the rafters.",
        art=(
            "╔════════════════════╗\n"
            "║ |              |  ║\n"
            "║ |   [ You ]    |  ║\n"
            "║ |              |  ║\n"
            "║ |              |  ║\n"
            "╚════════════════════╝"
        ),
        exits={"south": "guardroom", "north": "throneroom", "east": "chapel", "west": "kitchen"},
        items=[],
    ),
    "kitchen": Room(
        id="kitchen",
        name="Kitchen",
        description="The hearth is still warm. Pots and pans hang everywhere. Someone fled mid-meal.",
        art=(
            "╔════════════════════╗\n"
            "║ (o) (o) (o) (o)   ║\n"
            "║  ~   ~   ~   ~    ║\n"
            "║  ===============  ║\n"
            "║     [ You ]       ║\n"
            "╚════════════════════╝"
        ),
        exits={"east": "hall"},
        items=["Bread Loaf", "Iron Ladle"],
    ),
    "chapel": Room(
        id="chapel",
        name="Chapel",
        description="Rows of pews before a cracked stone altar. Candles still burn, dripping wax.",
        art=(
            "╔════════════════════╗\n"
            "║        /\\         ║\n"
            "║       /  \\        ║\n"
            "║  ====ALTAR====    ║\n"
            "║     [ You ]       ║\n"
            "╚════════════════════╝"
        ),
        exits={"west": "hall"},
        items=["Holy Symbol"],
    ),
    "throneroom": Room(
        id="throneroom",
        name="Throne Room",
        description=(
            "The seat of power stands before you. A golden crown rests upon the throne, "
            "glittering in the torchlight. It has been waiting for someone."
        ),
        art=(
            "╔════════════════════╗\n"
            "║   /\\/\\  /\\/\\  /\\ ║\n"
            "║  ( THRONE ROOM  ) ║\n"
            "║   \\/\\/  \\/\\/  \\/ ║\n"
            "║     [ You ]       ║\n"
            "╚════════════════════╝"
        ),
        exits={"south": "hall"},
        items=["Golden Crown"],
    ),
}

WIN_ITEM = "Golden Crown"
WIN_ROOM = "throneroom"


class AdventureGame:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.current_room_id = "cell"
        self.inventory: list[str] = []
        self.visited: set[str] = {"cell"}
        self.log = "You awaken in a cold, damp cell. The door is open. Which way?"
        self.won = False

    @property
    def room(self) -> Room:
        return ROOMS[self.current_room_id]

    def move(self, direction: str) -> str:
        if direction not in self.room.exits:
            return f"There is no exit to the {direction}."
        self.current_room_id = self.room.exits[direction]
        self.visited.add(self.current_room_id)
        return f"You head {direction} into the {self.room.name}."

    def pick_up(self) -> str:
        if not self.room.items:
            return "There is nothing here to pick up."
        item = self.room.items.pop(0)
        self.inventory.append(item)
        if item == WIN_ITEM:
            self.won = True
            return f"You pick up the {item}. The weight of it feels like destiny."
        return f"You pick up the {item}."

    def look(self) -> str:
        room = self.room
        exits = ", ".join(room.exits.keys()) or "none"
        items = ", ".join(room.items) if room.items else "nothing of note"
        return f"{room.description} Exits lead {exits}. You see: {items}."

    def show_inventory(self) -> str:
        if not self.inventory:
            return "Your pack is empty."
        return "You are carrying: " + ", ".join(self.inventory) + "."
