"""Verdant Crown: a small, code-only medieval RTS powered by pygame-ce."""
from __future__ import annotations

import math
import random
import heapq
import json
from array import array
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

import pygame

pygame.init()
pygame.display.set_caption("Verdant Crown")

WIDTH, HEIGHT = 1280, 720
MAP_SIZE, HUD_H = 120, 126
MAP_CENTER = MAP_SIZE / 2
WORLD_MIN = .5
WORLD_MAX = MAP_SIZE - .5
FPS = 60
GREEN = (67, 139, 79)
RED = (164, 61, 55)
GOLD = (234, 191, 78)
CREAM = (239, 228, 194)
INK = (39, 35, 31)
FOG_COLOR = (15, 20, 18)
FOG_VISIBLE_ALPHA = 0
FOG_EXPLORED_ALPHA = 145
FOG_UNEXPLORED_ALPHA = 255
FOG_TEXTURE_STRENGTH = 3
FOG_TEXTURE_SCALE = .16
TERRAIN_SEED = 4729
TERRAIN_DETAIL_MIN_ZOOM = 7
TERRAIN_KINDS = ("mountain", "forest", "path", "plains")
TERRAIN_METADATA = {
    "mountain": {
        "movement_multiplier": 0.5,
        "vision_cost": 0.75,
        "archer_range_bonus": 1.0,
        "ranged_damage_taken_multiplier": 1.0,
        "damage_taken_multiplier": 1.0,
        "base_color": (105, 105, 96),
    },
    "forest": {
        "movement_multiplier": 0.75,
        "vision_cost": 5.0,
        "archer_range_bonus": 0.0,
        "ranged_damage_taken_multiplier": 0.7,
        "damage_taken_multiplier": 1.0,
        "base_color": (42, 83, 49),
    },
    "path": {
        "movement_multiplier": 2.0,
        "vision_cost": 1.0,
        "archer_range_bonus": 0.0,
        "ranged_damage_taken_multiplier": 1.0,
        "damage_taken_multiplier": 1.2,
        "base_color": (161, 132, 79),
    },
    "plains": {
        "movement_multiplier": 1.0,
        "vision_cost": 1.0,
        "archer_range_bonus": 0.0,
        "ranged_damage_taken_multiplier": 1.0,
        "damage_taken_multiplier": 1.0,
        "base_color": (91, 132, 65),
    },
}
UNIT_KINDS = ("swordsman", "archer", "shield")
NATIVE_UNIT_KINDS = (
    "dwarf_guard", "dwarf_arbalist",
    "elf_bladedancer", "elf_ranger",
    "orc_cleaver", "orc_spear_thrower",
    "demon_reaver", "infernal_warlock",
    "frost_colossus", "ice_hurler",
)
NATIVE_FACTIONS = ("dwarf", "elf", "orc", "demon", "frost_giant")
CHECKPOINT_FACTION_BY_TERRAIN = {
    "mountain": "dwarf",
    "forest": "elf",
    "plains": "orc",
}
CHECKPOINT_UNITS = {
    "dwarf": ("dwarf_guard", "dwarf_arbalist"),
    "elf": ("elf_bladedancer", "elf_ranger"),
    "orc": ("orc_cleaver", "orc_spear_thrower"),
    "demon": ("demon_reaver", "infernal_warlock"),
    "frost_giant": ("frost_colossus", "ice_hurler"),
}
NATIVE_FACTION_COLORS = {
    "dwarf": (132, 119, 92),
    "elf": (70, 151, 125),
    "orc": (132, 112, 48),
    "demon": (184, 73, 45),
    "frost_giant": (93, 169, 205),
}
NATIVE_FACTION_LABELS = {
    "dwarf": "DWARF",
    "elf": "ELF",
    "orc": "ORC",
    "demon": "DEMON",
    "frost_giant": "FROST GIANT",
}
PURCHASABLE_UNIT_KINDS = UNIT_KINDS
OBJECTIVE_UNIT_KINDS = ("king",)
AUTONOMOUS_GUARD_KINDS = ("knight",)
ALL_UNIT_KINDS = (
    *PURCHASABLE_UNIT_KINDS,
    *NATIVE_UNIT_KINDS,
    *OBJECTIVE_UNIT_KINDS,
    *AUTONOMOUS_GUARD_KINDS,
)
COMBAT_UNIT_KINDS = (*PURCHASABLE_UNIT_KINDS, *NATIVE_UNIT_KINDS)
RANGED_UNIT_KINDS = (
    "archer", "dwarf_arbalist", "elf_ranger", "orc_spear_thrower",
    "infernal_warlock", "ice_hurler",
)
ENEMY_PRODUCTION_KINDS = PURCHASABLE_UNIT_KINDS
MELEE_UNIT_KINDS = ("swordsman", "shield")
SWORDSMAN_BASE_SPEED = 1
SWORDSMAN_ATTACK_RANGE = 1.02
UNIT_VISION_RADIUS = 8.0
PLAYER_RECRUIT_ENGAGE_RADIUS = UNIT_VISION_RADIUS
PLAYER_AUTO_ATTACK_RADIUS = 5.0
PLAYER_AUTO_ATTACK_LEASH_RADIUS = 6.0
# Shared movement geometry, steering, and path-cache timing. Units are treated
# as soft discs: UNIT_SOFT_OVERLAP is intentional visual/physical compression,
# so separation begins only inside the remaining minimum center distance.
UNIT_SEPARATION_RADIUS = 1.15
UNIT_SOFT_OVERLAP = .15
UNIT_SEPARATION_GAIN = 4.0
UNIT_MAX_SEPARATION_SPEED_MULTIPLIER = 2.0
UNIT_TINY_SEPARATION = .02
UNIT_NEIGHBOR_QUERY_RADIUS = 2.3
UNIT_PHYSICAL_RADIUS = UNIT_SEPARATION_RADIUS / 2
UNIT_SPATIAL_HASH_CELL_SIZE = UNIT_NEIGHBOR_QUERY_RADIUS
UNIT_BLOCKED_TIME_THRESHOLD = .75
UNIT_PATHFINDING_CELL_SIZE = 1.0
UNIT_WAYPOINT_ARRIVAL_TOLERANCE = .12
UNIT_PATH_RECALCULATION_INTERVAL = .5
UNIT_PATH_CLEAR_HYSTERESIS = .35
# A clear direct order is allowed to trigger one terrain search when non-plains
# cells occur in this bounded corridor. The result then stays cached exactly as
# an obstacle detour does; static terrain never causes per-frame searches.
UNIT_TERRAIN_ROUTE_SCAN_RADIUS = 8
UNIT_TERRAIN_ROUTE_MAX_DISTANCE = 10.0
UNIT_SLOT_SETTLE_RADIUS = .12
# A failed route must have a predictable upper bound.  This is deliberately
# below a full-map flood while still allowing long routes around ordinary
# formations.
UNIT_ASTAR_MAX_EXPANSIONS = 4096
UNIT_ASTAR_SEARCHES_PER_UPDATE = 2
# Kings and knights defend a fixed area around their starting post. They may
# acquire enemies inside this radius, but movement is clamped to the same
# circle so neither special unit can turn into a roaming army unit.
DEFENDER_CHASE_RADIUS = 20.0
GUARD_LEASH_DISTANCE = DEFENDER_CHASE_RADIUS
KING_RECOVERY_HEALTH_RATIO = .5
KING_RECOVERY_ENGAGEMENT_RADIUS = 7.0
KING_HOME_HEAL_RATE = 1.5
UNIT_STATS = {
    "swordsman": {
        "max_health": 100,
        "speed": SWORDSMAN_BASE_SPEED,
        "damage": 5,
        "cooldown": .5,
        "attack_range": SWORDSMAN_ATTACK_RANGE,
    },
    "archer": {
        "max_health": 20,
        "speed": .7,
        "damage": 50,
        "cooldown": 2.0,
        "attack_range": 5,
    },
    "shield": {
        "max_health": 200,
        "speed": .8,
        "damage": 5,
        "cooldown": 1,
        "attack_range": SWORDSMAN_ATTACK_RANGE,
    },
    "king": {
        "max_health": 700,
        "speed": SWORDSMAN_BASE_SPEED,
        "damage": 20,
        "cooldown": .4,
        "attack_range": 1.5,
    },
    "knight": {
        "max_health": 400,
        "speed": SWORDSMAN_BASE_SPEED,
        "damage": 10,
        "cooldown": .5,
        "attack_range": SWORDSMAN_ATTACK_RANGE,
    },
    "dwarf_guard": {
        "max_health": 260,
        "speed": .65,
        "damage": 6,
        "cooldown": .8,
        "attack_range": SWORDSMAN_ATTACK_RANGE,
    },
    "dwarf_arbalist": {
        "max_health": 100,
        "speed": .6,
        "damage": 30,
        "cooldown": 2.0,
        "attack_range": 4.5,
    },
    "elf_bladedancer": {
        "max_health": 50,
        "speed": 1.2,
        "damage": 5,
        "cooldown": .5,
        "attack_range": SWORDSMAN_ATTACK_RANGE,
    },
    "elf_ranger": {
        "max_health": 15,
        "speed": 1.0,
        "damage": 35,
        "cooldown": 1.6,
        "attack_range": 6.5,
    },
    "orc_cleaver": {
        "max_health": 130,
        "speed": .95,
        "damage": 14,
        "cooldown": .5,
        "attack_range": SWORDSMAN_ATTACK_RANGE,
    },
    "orc_spear_thrower": {
        "max_health": 50,
        "speed": .8,
        "damage": 45,
        "cooldown": 1.25,
        "attack_range": 4.0,
    },
    "demon_reaver": {
        "max_health": 500,
        "speed": 1.0,
        "damage": 30,
        "cooldown": .5,
        "attack_range": 1.1,
    },
    "infernal_warlock": {
        "max_health": 180,
        "speed": .75,
        "damage": 90,
        "cooldown": 1.8,
        "attack_range": 6.0,
    },
    "frost_colossus": {
        "max_health": 650,
        "speed": .45,
        "damage": 50,
        "cooldown": 1.2,
        "attack_range": 1.4,
    },
    "ice_hurler": {
        "max_health": 250,
        "speed": .5,
        "damage": 85,
        "cooldown": 2.5,
        "attack_range": 7.0,
    },
}
ARCHER_DAMAGE_VS_SHIELD_MULTIPLIER = .3
ARCHER_DAMAGE_VS_KING_MULTIPLIER = .5
ARCHER_DAMAGE_VS_KNIGHT_MULTIPLIER = .7
UNIT_COSTS = {"swordsman": 200, "archer": 500, "shield": 300}
UNIT_RENDER_SCALES = {
    "swordsman": 1.55,
    "archer": 1.55,
    "shield": 1.55 * 1.15,
    "king": 2.2,
    "knight": 2.0,
    "dwarf_guard": 1.8,
    "dwarf_arbalist": 1.65,
    "elf_bladedancer": 1.5,
    "elf_ranger": 1.5,
    "orc_cleaver": 1.75,
    "orc_spear_thrower": 1.6,
    "demon_reaver": 2.05,
    "infernal_warlock": 1.8,
    "frost_colossus": 2.5,
    "ice_hurler": 2.15,
}
CHECKPOINT_CAPTURE_RADIUS = 2.5
CHECKPOINT_CAPTURE_SECONDS = 5.0
CHECKPOINT_DEFENDER_LEASH = 12.0
CHECKPOINT_SPAWN_SECONDS = 30.0
CHECKPOINT_MAX_DEFENDERS = 15
CHECKPOINT_RAID_SIZE = 10
CAPTURED_CHECKPOINT_SPAWN_SECONDS = 45.0
CAPTURED_CHECKPOINT_MAX_UNITS = 5
CHECKPOINT_INCOME = 5.0
CHECKPOINT_VISION_RADIUS = 12.0
CHECKPOINT_HEAL_RADIUS = 4.0
CHECKPOINT_HEAL_RATE = 1.0
CHECKPOINT_OBJECTIVE_BAR_HEIGHT = 66
DEMON_LIFESTEAL_RATIO = .5
NATIVE_SPLASH_DAMAGE_RATIO = .5
NATIVE_SPLASH_TARGET_LIMIT = 3
WARLOCK_SPLASH_RADIUS = 1.5
FROST_COLOSSUS_SLOW_MULTIPLIER = .6
ICE_HURLER_SLOW_MULTIPLIER = .7
FROST_SLOW_SECONDS = 2.0
ICE_HURLER_SPLASH_RADIUS = 1.75
ELF_RANGER_PREFERRED_RANGE = 5.5
ELF_RANGER_KITE_LEASH = 6.0
DWARF_ARBALIST_BRACE_SECONDS = 1.0
MIN_UNIT_RENDER_SIZE = 8
KING_SLASH_LIFETIME = .20
RECRUIT_SHORTCUTS = {
    pygame.K_s: "swordsman",
    pygame.K_a: "archer",
    pygame.K_q: "shield",
}
SELECTION_SHORTCUTS = {
    pygame.K_1: "swordsman",
    pygame.K_2: "archer",
    pygame.K_4: "shield",
    pygame.K_3: None,
}

GREEN_KING_POSITION = (round(MAP_SIZE * .09), MAP_CENTER)
RED_KING_POSITION = (round(MAP_SIZE * .885), MAP_CENTER)
CAMERA_START = (GREEN_KING_POSITION[0] + 2.5, MAP_CENTER + .5)
KING_GUARD_POST_ABOVE_OFFSET = (0, -3.0)
KING_GUARD_POST_BELOW_OFFSET = (0, 3.0)
KING_GUARD_POST_OFFSETS = (
    KING_GUARD_POST_ABOVE_OFFSET,
    KING_GUARD_POST_BELOW_OFFSET,
)
RECRUIT_FORWARD_OFFSET = 4.0
RECRUIT_FIRST_LATERAL_OFFSET = 1.5
RECRUIT_LATERAL_SPACING = 1.25
RECRUIT_SLOTS_PER_COLUMN = 4
PLAYER_STARTING_UNITS = (
    ("swordsman", 5, -1),
    ("swordsman", 5, 2),
    ("archer", 6.5, .5),
)
ENEMY_STARTING_UNITS = (
    ("swordsman", -5, -2),
    ("swordsman", -5, 0),
    ("swordsman", -5, 2),
    ("archer", -6.5, 0),
)
LEVEL_ONE_ENEMY_STARTING_UNITS = (
    ("swordsman", -4, -4.5),
    ("swordsman", -4, -3.5),
    ("swordsman", -4, -2.5),
    ("swordsman", -4, -1.5),
    ("swordsman", -4, -.5),
    ("swordsman", -4, .5),
    ("swordsman", -4, 1.5),
    ("swordsman", -4, 2.5),
    ("swordsman", -4, 3.5),
    ("swordsman", -4, 4.5),
    ("archer", -5.5, -1.5),
    ("archer", -5.5, 1.5),
)


@dataclass(frozen=True)
class CheckpointProfile:
    """Per-hold production, territory, and presentation rules."""

    initial_melee: int
    initial_ranged: int
    spawn_seconds: float
    max_defenders: int
    raid_threshold: int
    raid_size: int
    capture_radius: float
    defender_leash: float
    vision_radius: float
    heal_radius: float
    income: float
    render_scale: float = 1.0
    opposite_large_target: bool = False


STANDARD_CHECKPOINT_PROFILE = CheckpointProfile(
    3, 2, CHECKPOINT_SPAWN_SECONDS, CHECKPOINT_MAX_DEFENDERS,
    CHECKPOINT_MAX_DEFENDERS, CHECKPOINT_RAID_SIZE,
    CHECKPOINT_CAPTURE_RADIUS, CHECKPOINT_DEFENDER_LEASH,
    CHECKPOINT_VISION_RADIUS, CHECKPOINT_HEAL_RADIUS, CHECKPOINT_INCOME,
)
EDITOR_CHECKPOINT_PROFILE = CheckpointProfile(
    3, 2, CHECKPOINT_SPAWN_SECONDS, CHECKPOINT_MAX_DEFENDERS,
    CHECKPOINT_MAX_DEFENDERS, CHECKPOINT_RAID_SIZE,
    CHECKPOINT_CAPTURE_RADIUS, CHECKPOINT_DEFENDER_LEASH,
    CHECKPOINT_VISION_RADIUS, CHECKPOINT_HEAL_RADIUS, 10.0,
)
LEVEL_FIVE_STANDARD_CHECKPOINT_PROFILE = CheckpointProfile(
    3, 2, CHECKPOINT_SPAWN_SECONDS, CHECKPOINT_MAX_DEFENDERS,
    CHECKPOINT_MAX_DEFENDERS, CHECKPOINT_RAID_SIZE,
    CHECKPOINT_CAPTURE_RADIUS, CHECKPOINT_DEFENDER_LEASH,
    CHECKPOINT_VISION_RADIUS, CHECKPOINT_HEAL_RADIUS, 10.0,
)
LARGE_CHECKPOINT_PROFILE = CheckpointProfile(
    6, 4, 10.0, 100, 70, 50, 5.0, 24.0, 24.0, 8.0, 20.0, 2.0, True,
)

CUSTOM_LEVEL_FILE = Path(__file__).with_name("custom_level.json")
EDITOR_MAP_SIZES = (60, 120, 160, 200, 240)
EDITOR_TERRAIN_CODES = {
    "plains": "p", "forest": "f", "mountain": "m", "path": "r",
}
EDITOR_CODE_TERRAIN = {
    code: kind for kind, code in EDITOR_TERRAIN_CODES.items()
}


@dataclass(frozen=True)
class LevelConfig:
    number: int
    name: str
    map_size: int
    description: str
    player_units: tuple[str, ...]
    player_starting_units: tuple[tuple[str, float, float], ...]
    enemy_starting_units: tuple[tuple[str, float, float], ...]
    enemy_ai: str
    starting_essence: float
    enemy_starting_essence: float
    player_income: float
    enemy_income: float
    has_checkpoints: bool = False
    display_title: str = ""
    story_text: str = ""
    difficulty_label: str = ""
    mechanic_tags: tuple[str, ...] = ()
    preview_type: str = "siege"


@dataclass
class EditorHold:
    """A checkpoint placed on the custom-level overview."""

    x: int
    y: int


@dataclass
class EditorLevelDraft:
    """Mutable, serializable source of truth for the level editor."""

    map_size: int
    terrain: dict[tuple[int, int], TerrainCell]
    holds: list[EditorHold]
    green_start: tuple[float, float]
    red_start: tuple[float, float]
    available_units: set[str]
    green_starting_counts: dict[str, int]
    red_starting_counts: dict[str, int]
    green_income: float
    red_income: float
    fog_of_war: bool
    hard_mode: bool = False

    def resize(self, new_size):
        """Resize without throwing away the terrain the player already made."""
        if new_size == self.map_size:
            return
        old_size, old_terrain = self.map_size, self.terrain
        scale = new_size / old_size
        self.terrain = {
            (x, y): old_terrain[
                (min(old_size - 1, int(x / scale)),
                 min(old_size - 1, int(y / scale)))
            ]
            for x in range(new_size) for y in range(new_size)
        }
        self.holds = [
            EditorHold(
                int(clamp(round(hold.x * scale), 1, new_size - 2)),
                int(clamp(round(hold.y * scale), 1, new_size - 2)),
            )
            for hold in self.holds
        ]
        self.green_start = tuple(
            clamp(value * scale, 2.5, new_size - 2.5)
            for value in self.green_start
        )
        self.red_start = tuple(
            clamp(value * scale, 2.5, new_size - 2.5)
            for value in self.red_start
        )
        self.map_size = new_size

    def starting_units(self, team):
        counts = (
            self.green_starting_counts
            if team == "green" else self.red_starting_counts
        )
        direction = 1 if team == "green" else -1
        placed = []
        index = 0
        for kind in UNIT_KINDS:
            for _ in range(counts.get(kind, 0)):
                column, row = divmod(index, 7)
                placed.append((
                    kind,
                    direction * (5.0 + column * 1.5),
                    (row - 3) * 1.25,
                ))
                index += 1
        return tuple(placed)

    def to_level_config(self):
        return LevelConfig(
            0, "CUSTOM BATTLEFIELD", self.map_size,
            "A battlefield shaped in the level editor.",
            tuple(kind for kind in UNIT_KINDS if kind in self.available_units),
            self.starting_units("green"), self.starting_units("red"),
            "full", 600.0, 600.0, self.green_income, self.red_income,
            bool(self.holds), "Custom Battlefield",
            "Your terrain, armies, economy, and objectives.",
            "CUSTOM", ("Player made",), "three_checkpoints",
        )

    def to_dict(self):
        rows = []
        for y in range(self.map_size):
            rows.append("".join(
                EDITOR_TERRAIN_CODES[self.terrain[(x, y)].kind]
                for x in range(self.map_size)
            ))
        return {
            "version": 1,
            "map_size": self.map_size,
            "terrain": rows,
            "holds": [[hold.x, hold.y] for hold in self.holds],
            "green_start": list(self.green_start),
            "red_start": list(self.red_start),
            "available_units": sorted(self.available_units),
            "green_starting_counts": self.green_starting_counts,
            "red_starting_counts": self.red_starting_counts,
            "green_income": self.green_income,
            "red_income": self.red_income,
            "fog_of_war": self.fog_of_war,
            "hard_mode": self.hard_mode,
        }

    @classmethod
    def from_dict(cls, data):
        size = int(data["map_size"])
        if size not in EDITOR_MAP_SIZES:
            raise ValueError("Unsupported custom map size")
        rows = data["terrain"]
        if len(rows) != size or any(len(row) != size for row in rows):
            raise ValueError("Custom terrain dimensions do not match map size")
        terrain = {}
        for y, row in enumerate(rows):
            for x, code in enumerate(row):
                kind = EDITOR_CODE_TERRAIN.get(code)
                if kind is None:
                    raise ValueError("Unknown custom terrain code")
                terrain[(x, y)] = TerrainCell(kind, (x * 3 + y * 5) % 4)
        available = set(data.get("available_units", UNIT_KINDS))
        if not available or not available.issubset(UNIT_KINDS):
            raise ValueError("Custom level must have valid available units")
        starts = []
        for key in ("green_start", "red_start"):
            values = tuple(float(value) for value in data[key])
            if len(values) != 2 or not all(2.5 <= value <= size - 2.5 for value in values):
                raise ValueError("Custom starting position is outside the map")
            starts.append(values)
        def counts(key):
            source = data.get(key, {})
            return {
                kind: int(clamp(int(source.get(kind, 0)), 0, 30))
                for kind in UNIT_KINDS
            }
        holds = [
            EditorHold(
                int(clamp(int(position[0]), 1, size - 2)),
                int(clamp(int(position[1]), 1, size - 2)),
            )
            for position in data.get("holds", [])[:12]
        ]
        return cls(
            size, terrain, holds, starts[0], starts[1], available,
            counts("green_starting_counts"),
            counts("red_starting_counts"),
            float(clamp(float(data.get("green_income", 20)), 0, 100)),
            float(clamp(float(data.get("red_income", 20)), 0, 100)),
            bool(data.get("fog_of_war", True)),
            bool(data.get("hard_mode", False)),
        )


@dataclass
class Checkpoint:
    """A terrain-themed strategic income landmark."""

    uid: int
    x: float
    y: float
    terrain_kind: str
    native_faction: str
    owner: str
    profile: CheckpointProfile = STANDARD_CHECKPOINT_PROFILE
    defender_uids: set[int] = field(default_factory=set)
    spawn_timer: float = CHECKPOINT_SPAWN_SECONDS
    spawn_count: int = 0
    captured_spawn_timer: float = CAPTURED_CHECKPOINT_SPAWN_SECONDS
    captured_spawn_count: int = 0
    captured_unit_uids: dict[str, set[int]] = field(
        default_factory=lambda: {"green": set(), "red": set()}
    )
    capturing_team: Optional[str] = None
    capture_progress: float = 0.0
    discovered: bool = False
    under_attack: bool = False
    contested: bool = False
    ever_captured: bool = False

    @property
    def cell(self):
        return int(self.x), int(self.y)

    @property
    def income_active(self):
        return self.owner in ("green", "red") and not self.under_attack


@dataclass(frozen=True)
class TerrainCell:
    """Gameplay terrain and its independent, cosmetic variation."""

    kind: str
    variation: int

    def __post_init__(self):
        if self.kind not in TERRAIN_KINDS:
            raise ValueError(f"Invalid terrain kind: {self.kind!r}")
        if type(self.variation) is not int or not 0 <= self.variation <= 3:
            raise ValueError("Terrain variation must be an integer from 0 to 3")


def terrain_movement_multiplier(kind):
    """Return gameplay speed metadata without consulting visual variation."""
    return TERRAIN_METADATA[kind]["movement_multiplier"]


def terrain_vision_cost(kind):
    """Return the sight-budget cost of crossing one tile of terrain."""
    return TERRAIN_METADATA[kind]["vision_cost"]


LEVELS = {
    1: LevelConfig(
        1, "THE FIRST MARCH", 20,
        "Face ten swordsmen and two archers. Recruit swordsmen only.",
        ("swordsman",), (), LEVEL_ONE_ENEMY_STARTING_UNITS,
        "none", 2000.0, 0.0, 20.0, 20.0, False,
        "Survive the Ambush!",
        "Crimson raiders strike at dawn. Hold the line and survive.",
        "EASY", ("Fixed battlefield", "Swordsmen only"), "ambush",
    ),
    2: LevelConfig(
        2, "THE LONG ROAD", 60,
        "Swordsmen and archers. The enemy sends one swordsman at 200 gold.",
        ("swordsman", "archer"), (), (), "simple", 400.0, 0.0,
        20.0, 20.0, False,
        "Punish Your Enemies!",
        "March the long road and break every force sent against you.",
        "MEDIUM", ("Road warfare", "Enemy waves"), "road_waves",
    ),
    3: LevelConfig(
        3, "THE VERDANT WAR", 120,
        "The complete battle with every troop and the adaptive enemy army.",
        UNIT_KINDS, PLAYER_STARTING_UNITS, ENEMY_STARTING_UNITS,
        "full", 400.0, 500.0, 20.0, 20.0, False,
        "Kill the Crimson King!",
        "Command every troop, storm the stronghold, and end the tyrant's reign.",
        "CONQUERER", ("Full roster", "Adaptive enemy"), "full_siege",
    ),
    4: LevelConfig(
        4, "THE THREE HOLDS", 160,
        "Seize three ancient holds to fund the final conquest.",
        UNIT_KINDS, PLAYER_STARTING_UNITS,
        ENEMY_STARTING_UNITS + (("archer", -6.5, 2.0),),
        "full", 400.0, 500.0, 10.0, 15.0, True,
        "Claim the Three Holds!",
        "Seize dwarven, elven, and orc holds before the final conquest.",
        "WARLORD", ("Three checkpoints", "Native factions", "Healing holds"),
        "three_checkpoints",
    ),
    5: LevelConfig(
        5, "LAST STAND", 160,
        "Break the five holds and survive fire and frost.",
        UNIT_KINDS, PLAYER_STARTING_UNITS,
        ENEMY_STARTING_UNITS + (("archer", -6.5, 2.0),),
        "full", 400.0, 500.0, 10.0, 30.0, True,
        "Last Stand", "", "APOCALYPSE", (), "last_stand",
    ),
}


def configure_map(size, green_start=None, red_start=None):
    """Update the shared world geometry before constructing a level."""
    global MAP_SIZE, MAP_CENTER, WORLD_MAX
    global GREEN_KING_POSITION, RED_KING_POSITION, CAMERA_START
    MAP_SIZE = size
    MAP_CENTER = MAP_SIZE / 2
    WORLD_MAX = MAP_SIZE - .5
    GREEN_KING_POSITION = green_start or (round(MAP_SIZE * .09), MAP_CENTER)
    RED_KING_POSITION = red_start or (round(MAP_SIZE * .885), MAP_CENTER)
    CAMERA_START = (GREEN_KING_POSITION[0] + 2.5, MAP_CENTER + .5)


def clamp(value, low, high):
    return max(low, min(high, value))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def clamp_to_map(position):
    return (
        clamp(position[0], WORLD_MIN, WORLD_MAX),
        clamp(position[1], WORLD_MIN, WORLD_MAX),
    )


def offset_from(position, offset):
    return position[0] + offset[0], position[1] + offset[1]


def make_default_editor_draft(size=200):
    """Create a roomy, immediately playable canvas for a custom scenario."""
    cache = getattr(make_default_editor_draft, "_terrain_cache", {})
    if size in cache:
        terrain = dict(cache[size])
    else:
        rng = random.Random("verdant-crown:level-editor")
        region_kinds = ("plains", "forest", "mountain") * 16
        regions = [
            (
                rng.uniform(0, size), rng.uniform(0, size), kind,
                rng.uniform(.75, 1.3),
            )
            for kind in region_kinds
        ]
        terrain = {}
        for x in range(size):
            for y in range(size):
                kind = min(
                    regions,
                    key=lambda region: (
                        (x + .5 - region[0]) ** 2
                        + (y + .5 - region[1]) ** 2
                    ) / region[3] ** 2,
                )[2]
                terrain[(x, y)] = TerrainCell(kind, rng.randrange(4))
        for x in range(round(size * .09), round(size * .89) + 1):
            progress = x / size
            y = round(size * (.50 + .10 * math.sin(progress * math.tau * 1.4)))
            for path_y in range(max(0, y - 1), min(size, y + 2)):
                cell = terrain[(x, path_y)]
                terrain[(x, path_y)] = TerrainCell("path", cell.variation)
        cache[size] = dict(terrain)
        make_default_editor_draft._terrain_cache = cache
    green_start = (round(size * .09), size / 2)
    red_start = (round(size * .885), size / 2)
    for start in (green_start, red_start):
        for x in range(max(0, int(start[0]) - 5), min(size, int(start[0]) + 6)):
            for y in range(max(0, int(start[1]) - 5), min(size, int(start[1]) + 6)):
                if dist((x + .5, y + .5), start) <= 5:
                    terrain[(x, y)] = TerrainCell(
                        "plains", terrain[(x, y)].variation
                    )
    holds = [
        EditorHold(round(size * .34), round(size * .31)),
        EditorHold(round(size * .51), round(size * .68)),
        EditorHold(round(size * .68), round(size * .29)),
    ]
    return EditorLevelDraft(
        size, terrain, holds, green_start, red_start, set(UNIT_KINDS),
        {"swordsman": 2, "archer": 1, "shield": 1},
        {"swordsman": 3, "archer": 1, "shield": 1},
        20.0, 20.0, True, False,
    )


def make_random_editor_draft(
    draft,
    rng=None,
    hold_count=3,
    hold_connection_ratio=1.0,
    path_amount=.25,
    terrain_weights=None,
):
    """Randomize map geography while preserving scenario and army settings."""
    rng = rng or random.SystemRandom()
    size = draft.map_size
    hold_count = int(clamp(int(hold_count), 0, 12))
    hold_connection_ratio = clamp(float(hold_connection_ratio), 0.0, 1.0)
    path_amount = clamp(float(path_amount), 0.0, 1.0)
    terrain_weights = terrain_weights or {
        "plains": 1.0, "forest": 1.0, "mountain": 1.0,
    }
    biome_names = ("plains", "forest", "mountain")
    weights = [max(0.0, float(terrain_weights.get(kind, 0))) for kind in biome_names]
    if not any(weights):
        weights = [1.0, 1.0, 1.0]
    region_count = max(18, round(size / 4))
    biome_kinds = rng.choices(biome_names, weights=weights, k=region_count)
    enabled_biomes = [
        kind for kind, weight in zip(biome_names, weights) if weight > 0
    ]
    for index, kind in enumerate(enabled_biomes):
        biome_kinds[index] = kind
    rng.shuffle(biome_kinds)
    regions = [
        (
            rng.uniform(0, size),
            rng.uniform(0, size),
            kind,
            rng.uniform(.72, 1.35),
        )
        for kind in biome_kinds
    ]
    terrain = {}
    for x in range(size):
        for y in range(size):
            kind = min(
                regions,
                key=lambda region: (
                    (x + .5 - region[0]) ** 2
                    + (y + .5 - region[1]) ** 2
                ) / region[3] ** 2,
            )[2]
            terrain[(x, y)] = TerrainCell(kind, rng.randrange(4))

    green_start = (
        round(size * .09),
        round(rng.uniform(size * .32, size * .68), 1),
    )
    red_start = (
        round(size * .89),
        round(rng.uniform(size * .32, size * .68), 1),
    )

    holds = []
    hold_biomes = enabled_biomes[:hold_count]
    hold_biomes.extend(rng.choices(
        biome_names, weights=weights, k=hold_count - len(hold_biomes)
    ))
    rng.shuffle(hold_biomes)
    minimum_hold_spacing = size * max(.055, .16 - hold_count * .008)
    for terrain_kind in hold_biomes:
        candidates = [
            (x, y)
            for (x, y), cell in terrain.items()
            if cell.kind == terrain_kind
            and size * .20 <= x <= size * .80
            and size * .10 <= y <= size * .90
            and dist((x + .5, y + .5), green_start) >= size * .18
            and dist((x + .5, y + .5), red_start) >= size * .18
            and all(
                dist((x, y), (hold.x, hold.y)) >= minimum_hold_spacing
                for hold in holds
            )
        ]
        if not candidates:
            candidates = [
                (x, y)
                for (x, y), cell in terrain.items()
                if cell.kind == terrain_kind
                and 2 <= x < size - 2 and 2 <= y < size - 2
                and all((x, y) != (hold.x, hold.y) for hold in holds)
            ]
        if not candidates:
            fallback_cells = [
                (x, y)
                for x in range(round(size * .25), round(size * .75))
                for y in range(round(size * .20), round(size * .80))
                if all((x, y) != (hold.x, hold.y) for hold in holds)
            ]
            x, y = rng.choice(fallback_cells)
            terrain[(x, y)] = TerrainCell(terrain_kind, rng.randrange(4))
            candidates = [(x, y)]
        x, y = rng.choice(candidates)
        holds.append(EditorHold(x, y))

    path_cells = set()
    route_count = 0 if path_amount <= 0 else max(1, round(path_amount * 4))
    for route_index in range(route_count):
        if route_index == 0:
            start, end = green_start, red_start
        else:
            start = (0, rng.uniform(size * .08, size * .92))
            end = (size - 1, rng.uniform(size * .08, size * .92))
        anchors = [
            start,
            (size * .30, rng.uniform(size * .12, size * .88)),
            (size * .52, rng.uniform(size * .12, size * .88)),
            (size * .72, rng.uniform(size * .12, size * .88)),
            end,
        ]
        for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
            steps = max(1, round(max(abs(x1 - x0), abs(y1 - y0))))
            for step in range(steps + 1):
                progress = step / steps
                eased = progress * progress * (3.0 - 2.0 * progress)
                x = round(x0 + (x1 - x0) * progress)
                y = round(y0 + (y1 - y0) * eased)
                for path_y in range(max(0, y - 1), min(size, y + 2)):
                    path_cells.add((int(clamp(x, 0, size - 1)), path_y))

    for hold in holds:
        if not path_cells or rng.random() > hold_connection_ratio:
            continue
        nearest = min(
            path_cells,
            key=lambda cell: abs(cell[0] - hold.x) + abs(cell[1] - hold.y),
        )
        dx, dy = nearest[0] - hold.x, nearest[1] - hold.y
        steps = max(1, abs(dx), abs(dy))
        for step in range(1, steps + 1):
            progress = step / steps
            path_cells.add((
                round(hold.x + dx * progress),
                round(hold.y + dy * progress),
            ))
    hold_cells = {(hold.x, hold.y) for hold in holds}
    for cell in path_cells - hold_cells:
        old = terrain[cell]
        terrain[cell] = TerrainCell("path", old.variation)

    for start in (green_start, red_start):
        for x in range(max(0, int(start[0]) - 5), min(size, int(start[0]) + 6)):
            for y in range(max(0, int(start[1]) - 5), min(size, int(start[1]) + 6)):
                if dist((x + .5, y + .5), start) <= 5:
                    terrain[(x, y)] = TerrainCell(
                        "plains", terrain[(x, y)].variation
                    )

    return EditorLevelDraft(
        size,
        terrain,
        holds,
        green_start,
        red_start,
        set(draft.available_units),
        dict(draft.green_starting_counts),
        dict(draft.red_starting_counts),
        draft.green_income,
        draft.red_income,
        draft.fog_of_war,
        draft.hard_mode,
    )


class UnitSpatialHash:
    """Deterministic uniform grid containing every living unit."""

    def __init__(self, cell_size=UNIT_SPATIAL_HASH_CELL_SIZE):
        if not math.isfinite(cell_size) or cell_size <= 0:
            raise ValueError("cell_size must be finite and positive")
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int], list[Unit]] = {}
        self.positions: dict[int, tuple[float, float]] = {}
        self.candidate_checks = 0
        self.candidate_queries = 0
        self.maximum_query_candidates = 0

    def _cell(self, x, y):
        return math.floor(x / self.cell_size), math.floor(y / self.cell_size)

    def rebuild(self, units):
        """Replace the index with living units, ordered by stable UID."""
        self.cells.clear()
        self.positions.clear()
        self.candidate_checks = 0
        self.candidate_queries = 0
        self.maximum_query_candidates = 0
        for unit in sorted(
            (unit for unit in units if unit.health > 0),
            key=lambda unit: unit.uid,
        ):
            self.positions[unit.uid] = (unit.x, unit.y)
            self.cells.setdefault(self._cell(unit.x, unit.y), []).append(unit)

    def neighbors(self, position, radius, exclude=None):
        """Return living units within radius in UID order."""
        if not math.isfinite(radius) or radius < 0:
            raise ValueError("radius must be finite and non-negative")
        x, y = position
        if not (math.isfinite(x) and math.isfinite(y)):
            return []
        min_cell = self._cell(x - radius, y - radius)
        max_cell = self._cell(x + radius, y + radius)
        radius_squared = radius * radius
        nearby = []
        query_candidates = 0
        for cell_x in range(min_cell[0], max_cell[0] + 1):
            for cell_y in range(min_cell[1], max_cell[1] + 1):
                for unit in self.cells.get((cell_x, cell_y), ()):
                    self.candidate_checks += 1
                    query_candidates += 1
                    if unit is exclude or unit.health <= 0:
                        continue
                    unit_x, unit_y = self.positions[unit.uid]
                    dx, dy = unit_x - x, unit_y - y
                    if dx * dx + dy * dy <= radius_squared:
                        nearby.append(unit)
        self.candidate_queries += 1
        self.maximum_query_candidates = max(
            self.maximum_query_candidates, query_candidates
        )
        return sorted(nearby, key=lambda unit: unit.uid)

    def segment_candidates(self, start, end, radius):
        """Return units in grid cells along a padded segment.

        Exact geometry remains the caller's responsibility.  Sampling at half
        a cell prevents long corridor checks from degenerating into a scan of
        every unit while covering every cell the padded segment can touch.
        """
        length = dist(start, end)
        samples = max(1, math.ceil(length / (self.cell_size * .5)))
        padding = max(1, math.ceil(radius / self.cell_size))
        candidates = {}
        for sample in range(samples + 1):
            amount = sample / samples
            x = start[0] + (end[0] - start[0]) * amount
            y = start[1] + (end[1] - start[1]) * amount
            center_x, center_y = self._cell(x, y)
            for cell_x in range(center_x - padding, center_x + padding + 1):
                for cell_y in range(center_y - padding, center_y + padding + 1):
                    for unit in self.cells.get((cell_x, cell_y), ()):
                        candidates[unit.uid] = unit
        return [candidates[uid] for uid in sorted(candidates)]


@dataclass
class Unit:
    kind: str
    team: str
    x: float
    y: float
    health: float = field(init=False)
    max_health: float = field(init=False)
    speed: float = field(init=False)
    damage: float = field(init=False)
    cooldown: float = field(init=False)
    attack_range: float = field(init=False)
    target_pos: Optional[tuple[float, float]] = None
    # Player ground orders survive temporary automatic combat. ``target_pos``
    # remains the immediate navigation destination used by both armies.
    order_pos: Optional[tuple[float, float]] = None
    target: object = None
    target_auto_acquired: bool = False
    attack_timer: float = 0
    movement_lock_timer: float = 0
    flash: float = 0
    selected: bool = False
    uid: int = 0
    tactical_pos: Optional[tuple[float, float]] = None
    tactical_timer: float = 0
    moved_this_update: bool = False
    home_position: Optional[tuple[float, float]] = None
    king_recovering: bool = False
    king_recovery_home_reached: bool = False
    nav_destination: Optional[tuple[float, float]] = None
    nav_waypoints: list[tuple[float, float]] = field(default_factory=list)
    nav_waypoint_index: int = 0
    nav_blocked_time: float = 0.0
    nav_last_path_time: float = -math.inf
    nav_destination_key: object = None
    nav_last_progress_position: Optional[tuple[float, float]] = None
    nav_clear_time: float = 0.0
    nav_side_preference: int = 0
    nav_terrain_revision: int = -1
    nav_terrain_route: bool = False
    nav_direct_check_timer: float = 0.0
    checkpoint_uid: Optional[int] = None
    raid_target_checkpoint_uid: Optional[int] = None
    raid_target_king_team: Optional[str] = None
    stationary_time: float = 0.0
    braced: bool = False
    slow_timer: float = 0.0
    slow_multiplier: float = 1.0

    def __post_init__(self):
        try:
            stats = UNIT_STATS[self.kind]
        except (KeyError, TypeError):
            raise ValueError(f"Invalid unit kind: {self.kind!r}") from None
        self.max_health = stats["max_health"]
        self.speed = stats["speed"]
        self.damage = stats["damage"]
        self.cooldown = stats["cooldown"]
        self.attack_range = stats["attack_range"]
        self.health = self.max_health

    @property
    def is_purchasable_army_unit(self):
        return self.kind in PURCHASABLE_UNIT_KINDS

    @property
    def is_king_objective(self):
        return self.kind in OBJECTIVE_UNIT_KINDS

    @property
    def is_autonomous_guard(self):
        return self.kind in AUTONOMOUS_GUARD_KINDS

    @property
    def is_player_commandable(self):
        return self.team == "green" and self.kind in COMBAT_UNIT_KINDS

    @property
    def is_enemy_ai_commandable(self):
        return self.team == "red" and self.kind in COMBAT_UNIT_KINDS

    @property
    def is_native_defender(self):
        return self.kind in NATIVE_UNIT_KINDS and self.team in NATIVE_FACTIONS

    @property
    def is_ranged(self):
        return self.kind in RANGED_UNIT_KINDS


class AIState(Enum):
    BUILDING = auto()
    RALLYING = auto()
    ATTACKING = auto()
    DEFENDING = auto()
    RECOVERING = auto()


@dataclass
class SlashEffect:
    """One deterministic king swipe, stored in world coordinates."""

    x: float
    y: float
    dx: float
    dy: float
    life: float
    team: str


class CombatAdvantage(Enum):
    STRONGER = auto()
    UNCERTAIN = auto()
    WEAKER = auto()


@dataclass(frozen=True)
class ObservedCombatUnit:
    """The combat facts available at one legitimate red-team sighting."""

    uid: int
    kind: str
    x: float
    y: float
    health: float
    observed_at: float
    observation_revision: int


@dataclass(frozen=True)
class LastSeenPlayerUnit:
    """Persistent strategic facts captured at a legitimate red-team sighting."""

    uid: int
    kind: str
    x: float
    y: float
    health: float
    observed_at: float


@dataclass(frozen=True)
class CombatAssessment:
    group_uids: tuple[int, ...]
    opponent_uids: tuple[int, ...]
    own_strength: float
    opponent_strength: float
    advantage_ratio: float
    classification: CombatAdvantage
    evaluated_at: float
    observation_revision: int
    oldest_opponent_observation: float
    stale: bool


class CombatStrengthEvaluator:
    """Deterministic, fog-safe comparison of a red group and observed opponents."""

    # All balance controls live here. Unit combat values themselves come from
    # UNIT_STATS; these only describe positional value and known matchups.
    RANGE_REFERENCE = 5.0
    MAX_RANGE_BONUS = .35
    REINFORCEMENT_RADIUS = 8.0
    REINFORCEMENT_WEIGHT = .5
    STRONGER_RATIO = 1.25
    WEAKER_RATIO = .8
    STALE_AFTER = 6.0
    PERIODIC_REFRESH = 1.0
    MIN_STRENGTH = 1e-9
    MATCHUP_MULTIPLIER = {
        "swordsman": {"swordsman": 1.0, "archer": 1.3, "shield": .9},
        "archer": {"swordsman": 1.2, "archer": 1.0, "shield": 1.15},
        "shield": {"swordsman": 1.0, "archer": 1.25, "shield": 1.0},
    }

    def __init__(self):
        self.latest: dict[tuple[int, ...], CombatAssessment] = {}
        self._signatures: dict[tuple[int, ...], tuple] = {}

    @classmethod
    def _range_multiplier(cls, kind):
        attack_range = UNIT_STATS[kind]["attack_range"]
        return 1.0 + min(
            cls.MAX_RANGE_BONUS,
            attack_range / cls.RANGE_REFERENCE * cls.MAX_RANGE_BONUS,
        )

    @classmethod
    def _unit_strength(cls, kind, health, opposing_kinds):
        stats = UNIT_STATS[kind]
        dps = stats["damage"] / stats["cooldown"]
        matchup = 1.0
        if opposing_kinds:
            kind_matchups = cls.MATCHUP_MULTIPLIER.get(kind, {})
            matchup = sum(
                kind_matchups.get(opponent, 1.0)
                for opponent in opposing_kinds
            ) / len(opposing_kinds)
        return health * dps * cls._range_multiplier(kind) * matchup

    @staticmethod
    def _near_group(unit, group):
        return min(
            dist((unit.x, unit.y), (member.x, member.y)) for member in group
        )

    def assess(
        self,
        group,
        opponents,
        now,
        observation_revision,
        own_reinforcements=(),
        opponent_reinforcements=(),
    ):
        """Return an assessment; opponents must be observation snapshots."""
        group = tuple(sorted(group, key=lambda unit: unit.uid))
        opponents = tuple(sorted(opponents, key=lambda unit: unit.uid))
        own_reinforcements = tuple(own_reinforcements)
        opponent_reinforcements = tuple(opponent_reinforcements)
        evaluated_units = (
            *group,
            *opponents,
            *own_reinforcements,
            *opponent_reinforcements,
        )
        unsupported = sorted({
            unit.kind for unit in evaluated_units
            if unit.kind not in COMBAT_UNIT_KINDS
        })
        if unsupported:
            raise ValueError(
                "Combat strength supports purchasable army units only; "
                f"unsupported kinds: {', '.join(unsupported)}"
            )
        if not group:
            raise ValueError("A combat group must contain at least one unit")
        key = tuple(unit.uid for unit in group)
        nearby_own = tuple(sorted(
            (
                unit for unit in own_reinforcements
                if unit.uid not in key
                and self._near_group(unit, group) <= self.REINFORCEMENT_RADIUS
            ),
            key=lambda unit: unit.uid,
        ))
        nearby_opponents = tuple(sorted(
            (
                unit for unit in opponent_reinforcements
                if unit.uid not in {opponent.uid for opponent in opponents}
                and self._near_group(unit, opponents or group)
                <= self.REINFORCEMENT_RADIUS
            ),
            key=lambda unit: unit.uid,
        ))
        all_opponents = opponents + nearby_opponents
        signature = (
            tuple((u.uid, u.kind, round(u.health, 6)) for u in group),
            tuple((u.uid, u.kind, round(u.health, 6), u.observation_revision)
                  for u in all_opponents),
            tuple((u.uid, u.kind, round(u.health, 6)) for u in nearby_own),
            observation_revision,
        )
        previous = self.latest.get(key)
        if (
            previous is not None
            and self._signatures.get(key) == signature
            and now - previous.evaluated_at < self.PERIODIC_REFRESH
        ):
            return previous

        own_kinds = [unit.kind for unit in group]
        opponent_kinds = [unit.kind for unit in all_opponents]
        own_strength = sum(
            self._unit_strength(unit.kind, unit.health, opponent_kinds)
            for unit in group
        )
        own_strength += self.REINFORCEMENT_WEIGHT * sum(
            self._unit_strength(unit.kind, unit.health, opponent_kinds)
            for unit in nearby_own
        )
        opponent_strength = sum(
            self._unit_strength(unit.kind, unit.health, own_kinds)
            for unit in opponents
        )
        opponent_strength += self.REINFORCEMENT_WEIGHT * sum(
            self._unit_strength(unit.kind, unit.health, own_kinds)
            for unit in nearby_opponents
        )
        oldest = min(
            (unit.observed_at for unit in all_opponents),
            default=float("-inf"),
        )
        stale = not all_opponents or now - oldest > self.STALE_AFTER
        ratio = (
            own_strength / max(opponent_strength, self.MIN_STRENGTH)
            if all_opponents else 1.0
        )
        if stale or self.WEAKER_RATIO < ratio < self.STRONGER_RATIO:
            classification = CombatAdvantage.UNCERTAIN
        elif ratio >= self.STRONGER_RATIO:
            classification = CombatAdvantage.STRONGER
        else:
            classification = CombatAdvantage.WEAKER
        result = CombatAssessment(
            key,
            tuple(unit.uid for unit in all_opponents),
            own_strength,
            opponent_strength,
            ratio,
            classification,
            now,
            observation_revision,
            oldest,
            stale,
        )
        self.latest[key] = result
        self._signatures[key] = signature
        return result


class EnemyAI:
    """Owns red-team strategy without changing per-unit combat or movement."""

    AWARENESS_RADIUS = 10.0
    PASSIVE_ENGAGEMENT_RADIUS = 5.0
    ARCHER_PROTECTION_RADIUS = 4.0
    KING_DEFENSE_RADIUS = 14.0
    SWITCH_MARGIN = 18.0
    ARCHER_DANGER_RADIUS = 3.25
    ARCHER_SAFE_RADIUS = 4.25
    TACTICAL_RECHECK = .45
    RALLY_LEASH = 5.0
    RALLY_DISTANCE = 8.0
    TARGET_GROUP_ESSENCE = 6000
    MAX_RALLY_WAIT = 18.0
    FORMATION_TOLERANCE = 3.0
    FORMATION_READY_FRACTION = .6
    FRONT_SPACING = 1.45
    LINE_SPACING = 2.25
    FORMATION_ROLE_BY_KIND = {
        "shield": "shield_rank",
        "swordsman": "swordsman_rank",
        "archer": "archer_rank",
        "dwarf_guard": "shield_rank",
        "dwarf_arbalist": "archer_rank",
        "elf_bladedancer": "swordsman_rank",
        "elf_ranger": "archer_rank",
        "orc_cleaver": "swordsman_rank",
        "orc_spear_thrower": "archer_rank",
        "demon_reaver": "shield_rank",
        "infernal_warlock": "archer_rank",
        "frost_colossus": "shield_rank",
        "ice_hurler": "archer_rank",
    }
    FORMATION_FORWARD_OFFSETS = {
        "shield_rank": 0.0,
        "swordsman_rank": LINE_SPACING,
        "archer_rank": LINE_SPACING * 2,
    }
    WAVE_COHESION_TOLERANCE = 5.0
    RECOVERY_LOSS_FRACTION = .5
    RECOVERY_DURATION = 7.0
    DEFENSE_ZONE_RADIUS = 14.0
    DEFENSE_EXIT_RADIUS = 16.0
    DEFENSE_APPROACH_RADIUS = 22.0
    DEFENSE_THREAT_THRESHOLD = 1.5
    RECALL_THREAT_THRESHOLD = 5.0
    DEFENSE_CLEAR_COOLDOWN = 4.0
    DEFENSIVE_RESERVE_SIZE = 2
    CUSTOM_KING_GARRISON_SIZE = 10
    CUSTOM_CHECKPOINT_GARRISON_SIZE = 15
    DEFENDER_ASSIGN_RADIUS = 22.0
    ARCHER_DEFENSE_OFFSET = 3.0
    EMERGENCY_MELEE_THREAT = 4.0
    PRODUCTION_INTERVAL = 6.5
    PLAYER_KNOWLEDGE_TTL = 18.0
    SCOUTING_RADIUS = UNIT_VISION_RADIUS
    KING_VISION_RADIUS = 16.0
    MIN_FRONTLINE = 2
    MISSING_BACKLINE_MIN_ARMY_SIZE = 4
    FRONTLINE_RATIO = .5
    SCORE_HYSTERESIS = 8.0
    LOSS_MEMORY_DURATION = 24.0
    COMBAT_ENGAGEMENT_RADIUS = 10.0
    # Field-combat decision controls. A fresh ratio at or below the retreat
    # margin retreats; a recovering group needs the wider re-engage margin to
    # attack again. This gap is the hysteresis band. Stale sightings are treated
    # conservatively: an attacker retreats, while a recovering group stays at
    # the rally point. No sighting means no strength decision.
    COMBAT_RETREAT_RATIO = .8
    COMBAT_REENGAGE_RATIO = 1.25
    COMBAT_DECISION_INTERVAL = 1.0
    COMBAT_URGENT_RETREAT_RATIO = .5
    COMBAT_URGENT_REENGAGE_RATIO = 1.75
    OBJECTIVE_FINISH_SECONDS = 4.0
    OBJECTIVE_COMMITMENT_RADIUS = 20.0
    # Casualties normally end a wave.  They may be ignored only when a new,
    # non-stale assessment measures an advantage strictly above this margin.
    # This deliberately sits above the ordinary "stronger" threshold.
    CASUALTY_ADVANTAGE_MARGIN = 1.5
    CHECKPOINT_ATTACK_RATIO = 1.35
    CHECKPOINT_MAX_RALLY_WAIT = 8.0
    CHECKPOINT_MIN_ATTACK_UNITS = 15
    LEVEL_FIVE_MIN_ATTACK_UNITS = 20
    CHECKPOINT_COHESION_FRACTION = .75
    RANGED_GROUP_RADIUS = 4.0
    RANGED_GROUP_BONUS_PER_ALLY = .10
    CHECKPOINT_PRODUCTION_SHARES = {
        "dwarf": {"archer": .50, "swordsman": .30, "shield": .20},
        "elf": {"shield": .55, "swordsman": .30, "archer": .15},
        "orc": {"archer": .70, "shield": .20, "swordsman": .10},
        "demon": {"archer": .60, "shield": .30, "swordsman": .10},
        "frost_giant": {"archer": .55, "shield": .40, "swordsman": .05},
    }
    STANDARD_PRODUCTION_SHARES = {
        "swordsman": .20,
        "archer": .50,
        "shield": .30,
    }

    # Production score weights. Keeping these named makes balance changes explicit.
    ARCHER_THREAT_LOW_THRESHOLD = 0
    ARCHER_THREAT_MODERATE_THRESHOLD = 3
    ARCHER_THREAT_HIGH_THRESHOLD = 6
    ARCHER_THREAT_HYSTERESIS = 1
    ARCHER_THREAT_SHIELD_BONUS = {
        "low": 0.0,
        "moderate": 46.0,
        "high": 92.0,
    }
    ARCHER_THREAT_SWORD_PENALTY = {
        "low": 0.0,
        "moderate": 24.0,
        "high": 54.0,
    }
    # Swords remain the cheap emergency melee option, but ordinary production
    # aims to keep them near one third of the army instead of defaulting to them.
    BASE_SWORD_SCORE = 30.0
    BASE_ARCHER_SCORE = 38.0
    BASE_SHIELD_SCORE = 34.0
    SWORD_TARGET_RATIO = .34
    SWORD_OVER_TARGET_PENALTY = 36.0
    EXPOSED_ARCHER_SWORD_BONUS = 18.0
    PLAYER_SWORD_ARCHER_BONUS = 15.0
    PLAYER_MELEE_SHIELD_BONUS = 12.0
    FRONTLINE_SHORTAGE_SWORD_BONUS = 24.0
    FRONTLINE_SHORTAGE_SHIELD_BONUS = 40.0
    DURABLE_FRONTLINE_BONUS = 18.0
    SQUAD_SHIELD_SHORTAGE_BONUS = 26.0
    KING_DEFENSE_SHIELD_BONUS = 28.0
    PROTECTED_ARCHER_BONUS = 14.0
    MISSING_BACKLINE_BONUS = 20.0
    UNPROTECTED_ARCHER_PENALTY = 34.0
    EMERGENCY_SWORD_BONUS = 65.0
    URGENT_SHIELD_PENALTY = 24.0
    RECENT_SWORD_LOSS_BONUS = 5.0
    RECENT_ARCHER_LOSS_BONUS = 7.0
    RECENT_SHIELD_LOSS_BONUS = 6.0
    FAILED_WAVE_FRONTLINE_BONUS = 6.0
    FAILED_WAVE_SHIELD_BONUS = 9.0
    SHIELD_ONLY_PENALTY = 80.0
    SHIELD_ONLY_SWORD_BONUS = 45.0
    SAVE_FOR_PREFERRED_MARGIN = 6.0
    SERIOUS_THREAT_SCORE = 4.0
    # Counter production is apportioned by essence. Projecting the next
    # purchase and minimizing total share error prevents ties near a target
    # boundary from oscillating; ENEMY_PRODUCTION_KINDS breaks exact ties.
    PRODUCTION_SHARE_ROUNDING_TOLERANCE = .03
    PRODUCTION_COUNTERS = {
        "swordsman": "archer",
        "archer": "shield",
        "shield": "swordsman",
    }
    STATE_PRODUCTION_WEIGHTS = {
        AIState.BUILDING: {"swordsman": 8.0, "archer": 4.0, "shield": 2.0},
        AIState.RALLYING: {"swordsman": 5.0, "archer": 8.0, "shield": 6.0},
        AIState.ATTACKING: {"swordsman": 8.0, "archer": 3.0, "shield": 5.0},
        AIState.DEFENDING: {"swordsman": 16.0, "archer": -4.0, "shield": 24.0},
        AIState.RECOVERING: {"swordsman": 12.0, "archer": 2.0, "shield": 10.0},
    }

    VALID_TRANSITIONS = {
        AIState.BUILDING: {AIState.RALLYING, AIState.ATTACKING, AIState.DEFENDING},
        AIState.RALLYING: {AIState.BUILDING, AIState.ATTACKING, AIState.DEFENDING},
        AIState.ATTACKING: {AIState.RALLYING, AIState.DEFENDING, AIState.RECOVERING},
        AIState.DEFENDING: {
            AIState.BUILDING, AIState.RALLYING, AIState.ATTACKING, AIState.RECOVERING
        },
        AIState.RECOVERING: {
            AIState.BUILDING, AIState.RALLYING, AIState.ATTACKING, AIState.DEFENDING
        },
    }

    def __init__(self, game, rng=None, decision_interval=.25):
        self.game = game
        self.rng = rng if rng is not None else random.Random()
        self.decision_interval = decision_interval
        self.decision_timer = 0.0
        self.recruitment_timer = 2.0
        self.state = AIState.BUILDING
        self.decision_count = 0
        self.squad: set[int] = set()
        self.recovery_guards: set[int] = set()
        self.formation_roles: dict[int, str] = {}
        self.rally_elapsed = 0.0
        self.recovery_elapsed = 0.0
        self.wave_start_strength = 0
        self.wave_number = 0
        self.wave_history: list[dict] = []
        self.launch_gate_history: list[dict] = []
        self.last_launch_gate: Optional[dict] = None
        self._launch_gate_signature: Optional[tuple] = None
        self.reserve: set[int] = set()
        self.defenders: set[int] = set()
        self.pre_defense_state = AIState.BUILDING
        self.defense_clear_elapsed = 0.0
        self.emergency_recruited = False
        self.last_threat_score = 0.0
        self.state_history = [(0.0, self.state)]
        self.elapsed = 0.0
        self.player_knowledge: dict[int, tuple[str, float]] = {}
        self.combat_observations: dict[int, ObservedCombatUnit] = {}
        self.last_seen_player_army: dict[int, LastSeenPlayerUnit] = {}
        # Tactical sightings remain independent from the strategic composition
        # learned only when a player army defeats an attack wave.
        self.learned_counter_essence: Optional[dict[str, int]] = None
        self.combat_observation_revision = 0
        self._currently_observed_player_uids: set[int] = set()
        self.combat_evaluator = CombatStrengthEvaluator()
        self.latest_combat_assessments = self.combat_evaluator.latest
        self.combat_opponent_uids: set[int] = set()
        self.last_combat_decision_at = float("-inf")
        self.last_combat_decision: Optional[str] = None
        self.archer_threat_level = "low"
        self.recent_losses: list[tuple[float, str]] = []
        self._known_red_uids: dict[int, str] = {
            unit.uid: unit.kind for unit in self._living_red_units()
        }
        self.failed_waves = 0
        self.last_production_choice: Optional[str] = None
        self.unavailable_production_kinds: set[str] = set()
        self.checkpoint_target_uid: Optional[int] = None
        self.checkpoint_guards: dict[int, set[int]] = {}
        self.checkpoint_route_cache: dict[tuple, tuple[tuple[float, float], ...]] = {}
        self.checkpoint_route: tuple[tuple[float, float], ...] = ()
        self.checkpoint_route_index = 0
        self.formation_checkpoint_uid: Optional[int] = None
        self.formation_anchor: Optional[tuple[float, float]] = None
        self.projected_arrival_eta: Optional[float] = None
        self.projected_defender_count = 0
        self.projected_defender_strength = 0.0
        self.projected_defender_composition: dict[str, int] = {}
        self.production_history: list[dict] = []
        self.last_production_scores = {
            kind: 0.0 for kind in ENEMY_PRODUCTION_KINDS
        }

    def transition_to(self, state):
        if state == self.state:
            return
        if state not in self.VALID_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid enemy AI transition: {self.state.name} -> {state.name}")
        self.state = state
        self.state_history.append((self.elapsed, state))

    @property
    def rally_point(self):
        """A fixed staging point between the Crimson King and the battlefield."""
        direction_x, direction_y = self._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            (self.game.team_king("green").x, self.game.team_king("green").y),
        )
        return (
            self.game.team_king("red").x + direction_x * self.RALLY_DISTANCE,
            self.game.team_king("red").y + direction_y * self.RALLY_DISTANCE,
        )

    def _terrain_route_to_checkpoint(self, checkpoint):
        """Return a cached fastest-terrain route from the rally point."""
        start = self.game._nav_cell(self.rally_point)
        goal = checkpoint.cell
        key = (self.game.terrain_revision, start, checkpoint.uid, goal)
        cached = self.checkpoint_route_cache.get(key)
        if cached is not None:
            return cached
        directions = (
            (-1, 0), (0, -1), (0, 1), (1, 0),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        )
        frontier = [(0.0, 0.0, start)]
        costs = {start: 0.0}
        came_from = {}
        while frontier:
            _, current_cost, current = heapq.heappop(frontier)
            if current_cost != costs.get(current):
                continue
            if current == goal:
                break
            for dx, dy in directions:
                neighbor = current[0] + dx, current[1] + dy
                if not (0 <= neighbor[0] < MAP_SIZE and 0 <= neighbor[1] < MAP_SIZE):
                    continue
                new_cost = current_cost + self.game._terrain_step_cost(
                    current, neighbor
                )
                if new_cost + 1e-12 >= costs.get(neighbor, math.inf):
                    continue
                costs[neighbor] = new_cost
                came_from[neighbor] = current
                heuristic = dist(neighbor, goal) / 2.0
                heapq.heappush(frontier, (new_cost + heuristic, new_cost, neighbor))
        if goal not in costs:
            route = (self.rally_point, (checkpoint.x, checkpoint.y))
        else:
            cells = [goal]
            current = goal
            while current != start:
                current = came_from[current]
                cells.append(current)
            cells.reverse()
            route = (
                self.rally_point,
                *(self.game._nav_world(cell) for cell in cells[1:]),
            )
            if route[-1] != (checkpoint.x, checkpoint.y):
                route = (*route, (checkpoint.x, checkpoint.y))
        self.checkpoint_route_cache[key] = tuple(route)
        return self.checkpoint_route_cache[key]

    def _checkpoint_route_eta(self, checkpoint, members):
        route = self._terrain_route_to_checkpoint(checkpoint)
        slowest_speed = min((unit.speed for unit in members), default=0.0)
        if slowest_speed <= 0:
            return route, math.inf
        travel_time = 0.0
        for start, end in zip(route, route[1:]):
            terrain_kind = self.game.terrain_kind_at(end)
            travel_time += dist(start, end) / (
                slowest_speed * terrain_movement_multiplier(terrain_kind)
            )
        return route, travel_time

    @staticmethod
    def _future_native_kind(checkpoint, spawn_index):
        melee, ranged = CHECKPOINT_UNITS[checkpoint.native_faction]
        initial_count = (
            checkpoint.profile.initial_melee
            + checkpoint.profile.initial_ranged
        )
        return ranged if (spawn_index - initial_count) % 2 == 0 else melee

    def projected_checkpoint_defenders(self, checkpoint, members):
        """Project the defenders present when the slowest attacker arrives."""
        route, eta = self._checkpoint_route_eta(checkpoint, members)
        defenders = list(self._checkpoint_defenders(checkpoint))
        if checkpoint.owner == checkpoint.native_faction and math.isfinite(eta):
            next_spawn = max(0.0, checkpoint.spawn_timer)
            scheduled = 0
            if next_spawn < eta - 1e-9:
                scheduled = 1 + int(
                    max(0.0, eta - next_spawn - 1e-9)
                    // checkpoint.profile.spawn_seconds
                )
            if not checkpoint.profile.opposite_large_target:
                scheduled = min(
                    max(0, checkpoint.profile.max_defenders - len(defenders)),
                    scheduled,
                )
            for offset in range(scheduled):
                if len(defenders) >= checkpoint.profile.max_defenders:
                    break
                kind = self._future_native_kind(
                    checkpoint, checkpoint.spawn_count + offset
                )
                projected = Unit(kind, checkpoint.native_faction, checkpoint.x, checkpoint.y)
                projected.uid = -(checkpoint.uid * 100 + offset + 1)
                defenders.append(projected)
                if (
                    checkpoint.profile.opposite_large_target
                    and
                    len(defenders) >= checkpoint.profile.raid_threshold
                    and self.game.native_raid_objective(checkpoint) is not None
                ):
                    defenders = defenders[checkpoint.profile.raid_size:]
        composition = {
            kind: sum(unit.kind == kind for unit in defenders)
            for kind in NATIVE_UNIT_KINDS + UNIT_KINDS
            if any(unit.kind == kind for unit in defenders)
        }
        return tuple(defenders), tuple(route), eta, composition

    def _checkpoint_defenders(self, checkpoint):
        if checkpoint.owner in NATIVE_FACTIONS:
            return [
                unit for unit in self.game.units
                if unit.uid in checkpoint.defender_uids and unit.health > 0
            ]
        if checkpoint.owner == "green":
            # Strategic checkpoint estimates may use only positions red has
            # legitimately observed. Hidden live unit positions never enter
            # objective selection or launch authorization.
            return [
                sighting for sighting in self.last_seen_player_army.values()
                if sighting.health > 0
                and dist((sighting.x, sighting.y), (checkpoint.x, checkpoint.y))
                <= checkpoint.profile.vision_radius
            ]
        return []

    @classmethod
    def _raw_group_strength(cls, group, opponents):
        """Return checkpoint strength, including nearby ranged-unit support."""
        living_group = tuple(unit for unit in group if unit.health > 0)
        opponent_kinds = [unit.kind for unit in opponents]
        return sum(
            CombatStrengthEvaluator._unit_strength(
                unit.kind, unit.health, opponent_kinds
            ) * (
                1.0 + cls.RANGED_GROUP_BONUS_PER_ALLY * sum(
                    other is not unit
                    and other.kind in RANGED_UNIT_KINDS
                    and dist((unit.x, unit.y), (other.x, other.y))
                    <= cls.RANGED_GROUP_RADIUS
                    for other in living_group
                )
                if unit.kind in RANGED_UNIT_KINDS else 1.0
            ) * {
                "dwarf_guard": 1.15,
                "dwarf_arbalist": 1.20,
                "elf_bladedancer": 1.10,
                "elf_ranger": 2.0,
                "orc_cleaver": 1.30,
                "orc_spear_thrower": (
                    1.35
                    if unit.health < UNIT_STATS[unit.kind]["max_health"] * .5
                    else 1.0
                ),
                "demon_reaver": 1.5,
                "infernal_warlock": 1.8,
                "frost_colossus": 1.35,
                "ice_hurler": 1.6,
            }.get(unit.kind, 1.0)
            for unit in living_group
        )

    def checkpoint_attack_ratio(self, members, checkpoint):
        defenders, _, _, _ = self.projected_checkpoint_defenders(
            checkpoint, members
        )
        if not defenders:
            return math.inf
        own = self._raw_group_strength(members, defenders)
        opposing = self._raw_group_strength(defenders, members)
        return own / max(opposing, CombatStrengthEvaluator.MIN_STRENGTH)

    def _select_checkpoint_objective(self, members=()):
        candidates = [
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.owner != "red"
        ]
        if not candidates:
            return None
        red_king = self.game.team_king("red")
        origin = (red_king.x, red_king.y)
        if self.game.custom_level_active:
            # Editor battles expand from the Crimson King one foothold at a
            # time, irrespective of native or Verdant ownership.
            return min(
                candidates,
                key=lambda checkpoint: (
                    dist(origin, (checkpoint.x, checkpoint.y)),
                    checkpoint.uid,
                ),
            )
        return min(
            candidates,
            key=lambda checkpoint: (
                0 if checkpoint.owner == "green" else 1,
                -self.checkpoint_attack_ratio(members, checkpoint)
                if members else 0,
                dist(origin, (checkpoint.x, checkpoint.y)),
                checkpoint.uid,
            ),
        )

    def strategic_objective(self, members=()):
        if self.game.level.has_checkpoints:
            current = self.game.checkpoint_by_uid(self.checkpoint_target_uid)
            if current is not None and current.owner != "red":
                return current
            checkpoint = self._select_checkpoint_objective(members)
            if checkpoint is not None:
                self.checkpoint_target_uid = checkpoint.uid
                return checkpoint
            self.checkpoint_target_uid = None
        return self.game.team_king("green")

    def _living_red_units(self):
        return [
            unit for unit in self.game.units
            if unit.is_enemy_ai_commandable and unit.health > 0
        ]

    def _squad_units(self):
        by_uid = {unit.uid: unit for unit in self._living_red_units()}
        return [by_uid[uid] for uid in sorted(self.squad) if uid in by_uid]

    def _checkpoint_guard_uids(self):
        return {
            uid
            for guards in self.checkpoint_guards.values()
            for uid in guards
        }

    def _checkpoint_guard_for(self, unit):
        return next(
            (
                self.game.checkpoint_by_uid(checkpoint_uid)
                for checkpoint_uid, guards in sorted(
                    self.checkpoint_guards.items()
                )
                if unit.uid in guards
            ),
            None,
        )

    def _checkpoint_guard_destination(self, checkpoint, unit):
        living = {member.uid for member in self._living_red_units()}
        guards = sorted(self.checkpoint_guards.get(checkpoint.uid, set()) & living)
        index = guards.index(unit.uid)
        angle = math.tau * index / max(1, len(guards))
        return (
            checkpoint.x + math.cos(angle) * 1.25,
            checkpoint.y + math.sin(angle) * 1.25,
        )

    def _group_essence(self, units):
        """Return recruitment cost of living, purchasable units in a group."""
        return sum(
            UNIT_COSTS[unit.kind]
            for unit in units
            if unit.health > 0 and unit.kind in PURCHASABLE_UNIT_KINDS
        )

    def _cleanup_squad(self):
        living = {unit.uid for unit in self._living_red_units()}
        self.squad.intersection_update(living)
        self.recovery_guards.intersection_update(living)
        self.reserve.intersection_update(living)
        self.defenders.intersection_update(living)
        self.checkpoint_guards = {
            checkpoint_uid: guards & living
            for checkpoint_uid, guards in self.checkpoint_guards.items()
            if guards & living or (
                (checkpoint := self.game.checkpoint_by_uid(checkpoint_uid))
                is not None and checkpoint.owner == "red"
            )
        }
        self.formation_roles = {
            uid: role for uid, role in self.formation_roles.items()
            if uid in living and uid in self.squad
        }
        for unit in self._squad_units():
            self.formation_roles[unit.uid] = self.FORMATION_ROLE_BY_KIND[unit.kind]

    def _formation_role(self, unit):
        """Return and repair the explicit rank role belonging to a squad unit."""
        role = self.FORMATION_ROLE_BY_KIND[unit.kind]
        if unit.uid in self.squad:
            self.formation_roles[unit.uid] = role
        return role

    def _formation_destination(self, unit, ordered_units=None, anchor=None):
        ordered_units = ordered_units or self._squad_units()
        ordered_units = sorted(ordered_units, key=lambda member: member.uid)
        role = self._formation_role(unit)
        role_units = [
            member for member in ordered_units
            if self._formation_role(member) == role
        ]
        index = role_units.index(unit)
        lateral = (index - (len(role_units) - 1) / 2) * self.FRONT_SPACING
        direction_target = anchor or (
            self.game.team_king("green").x,
            self.game.team_king("green").y,
        )
        advance_x, advance_y = self._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            direction_target,
        )
        side_x, side_y = -advance_y, advance_x
        forward_offset = self.FORMATION_FORWARD_OFFSETS[role]
        anchor_x, anchor_y = anchor or self.rally_point
        return clamp_to_map((
            anchor_x - advance_x * forward_offset + side_x * lateral,
            anchor_y - advance_y * forward_offset + side_y * lateral,
        ))

    def _assign_custom_available_units(self):
        """Fill editor garrisons first, then assign every surplus unit to attack."""
        living_units = self._living_red_units()
        by_uid = {unit.uid: unit for unit in living_units}
        king_pos = (self.game.team_king("red").x, self.game.team_king("red").y)

        self.reserve.intersection_update(by_uid)
        while len(self.reserve) < self.CUSTOM_KING_GARRISON_SIZE:
            hold_guards = self._checkpoint_guard_uids()
            candidate = min(
                (
                    unit for unit in living_units
                    if unit.uid not in self.reserve
                    and unit.uid not in hold_guards
                    and unit.uid not in self.defenders
                ),
                key=lambda unit: (
                    unit.kind != "shield",
                    dist((unit.x, unit.y), king_pos),
                    unit.uid,
                ),
                default=None,
            )
            if candidate is None:
                break
            self.squad.discard(candidate.uid)
            self.formation_roles.pop(candidate.uid, None)
            self.reserve.add(candidate.uid)
            candidate.target = None

        for checkpoint_uid in sorted(self.checkpoint_guards):
            checkpoint = self.game.checkpoint_by_uid(checkpoint_uid)
            if checkpoint is None:
                continue
            guards = self.checkpoint_guards[checkpoint_uid]
            while len(guards) < self.CUSTOM_CHECKPOINT_GARRISON_SIZE:
                hold_guards = self._checkpoint_guard_uids()
                candidate = min(
                    (
                        unit for unit in living_units
                        if unit.uid not in self.reserve
                        and unit.uid not in hold_guards
                        and unit.uid not in self.defenders
                    ),
                    key=lambda unit: (
                        dist((unit.x, unit.y), (checkpoint.x, checkpoint.y)),
                        unit.uid,
                    ),
                    default=None,
                )
                if candidate is None:
                    break
                self.squad.discard(candidate.uid)
                self.formation_roles.pop(candidate.uid, None)
                guards.add(candidate.uid)
                candidate.target = None
                candidate.target_pos = self._checkpoint_guard_destination(
                    checkpoint, candidate
                )

        hold_guards = self._checkpoint_guard_uids()
        available = [
            unit for unit in living_units
            if unit.uid not in self.reserve
            and unit.uid not in hold_guards
            and unit.uid not in self.defenders
        ]
        for unit in sorted(available, key=lambda member: member.uid):
            self.squad.add(unit.uid)
            self.formation_roles[unit.uid] = self.FORMATION_ROLE_BY_KIND[unit.kind]
            unit.target = None
        for unit in living_units:
            if unit.uid in self.reserve:
                unit.target = None
                unit.target_pos = self._reserve_position(unit)
        squad_units = self._squad_units()
        for unit in squad_units:
            unit.target_pos = self._formation_destination(unit, squad_units)

    def _assign_available_units(self):
        if self.game.custom_level_active:
            self._assign_custom_available_units()
            return
        hold_guards = self._checkpoint_guard_uids()
        living_units = [
            unit for unit in self._living_red_units()
            if unit.uid not in hold_guards
        ]
        # A home reserve may never strand enough purchasable essence to form a
        # normal attack wave. Release reserved units until the proposed squad
        # can reach the target.
        while (
            self.reserve
            and self._group_essence(
                unit for unit in living_units if unit.uid not in self.reserve
            ) < self.TARGET_GROUP_ESSENCE
        ):
            self.reserve.remove(min(self.reserve))
        available = [
            unit for unit in living_units
            if unit.uid not in self.squad and unit.uid not in self.reserve
        ]
        proposed = [
            unit for unit in living_units
            if unit.uid in self.squad or unit.uid not in self.reserve
        ]
        # Keep a small home guard only when its cost cannot prevent a full wave.
        desired_reserve = self.DEFENSIVE_RESERVE_SIZE
        reserve_needed = max(0, desired_reserve - len(self.reserve))
        king_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        reserve_candidates = list(available)
        reserve_has_shield = any(
            unit.kind == "shield" and unit.uid in self.reserve
            for unit in self._living_red_units()
        )
        for _ in range(reserve_needed):
            if not reserve_candidates:
                break
            unit = min(
                (
                    candidate for candidate in reserve_candidates
                    if self._group_essence(
                        member for member in proposed
                        if member.uid != candidate.uid
                    ) >= self.TARGET_GROUP_ESSENCE
                ),
                key=lambda member: (
                    member.kind == "shield" if reserve_has_shield
                    else member.kind != "shield",
                    dist((member.x, member.y), king_pos),
                    member.uid,
                ),
                default=None,
            )
            if unit is None:
                break
            reserve_candidates.remove(unit)
            proposed.remove(unit)
            self.reserve.add(unit.uid)
            reserve_has_shield |= unit.kind == "shield"
            unit.target = None
            unit.target_pos = self._reserve_position(unit)
        available = [unit for unit in available if unit.uid not in self.reserve]
        for unit in sorted(available, key=lambda member: member.uid):
            self.squad.add(unit.uid)
            self.formation_roles[unit.uid] = self.FORMATION_ROLE_BY_KIND[unit.kind]
            unit.target = None
        squad_units = self._squad_units()
        for unit in squad_units:
            if self.state in (AIState.BUILDING, AIState.RALLYING):
                unit.target_pos = self._formation_destination(unit, squad_units)

    def _assign_checkpoint_reinforcements(self):
        """Feed fresh recruits into an active hold assault as one formation."""
        if self.state != AIState.ATTACKING:
            return
        checkpoint = self.game.checkpoint_by_uid(self.checkpoint_target_uid)
        if checkpoint is None or checkpoint.owner == "red":
            return
        if not any(
            dist((unit.x, unit.y), (checkpoint.x, checkpoint.y))
            <= checkpoint.profile.defender_leash + self.FORMATION_TOLERANCE
            for unit in self._squad_units()
        ):
            return
        assigned = (
            self.squad | self.reserve | self.defenders
            | self._checkpoint_guard_uids()
        )
        for unit in self._living_red_units():
            if unit.uid in assigned:
                continue
            self.squad.add(unit.uid)
            self.formation_roles[unit.uid] = self.FORMATION_ROLE_BY_KIND[unit.kind]
            unit.target = None

    def _reinforce_custom_garrisons_from_unassigned(self):
        """Give fresh editor recruits to depleted garrisons before an assault."""
        if not self.game.custom_level_active:
            return
        living_units = self._living_red_units()
        assigned = (
            self.squad | self.reserve | self.defenders
            | self._checkpoint_guard_uids()
        )
        available = [unit for unit in living_units if unit.uid not in assigned]
        king_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        while (
            available
            and len(self.reserve) < self.CUSTOM_KING_GARRISON_SIZE
        ):
            unit = min(
                available,
                key=lambda candidate: (
                    candidate.kind != "shield",
                    dist((candidate.x, candidate.y), king_pos),
                    candidate.uid,
                ),
            )
            available.remove(unit)
            self.reserve.add(unit.uid)
            unit.target = None
            unit.target_pos = self._reserve_position(unit)
        for checkpoint_uid in sorted(self.checkpoint_guards):
            checkpoint = self.game.checkpoint_by_uid(checkpoint_uid)
            if checkpoint is None:
                continue
            guards = self.checkpoint_guards[checkpoint_uid]
            while (
                available
                and len(guards) < self.CUSTOM_CHECKPOINT_GARRISON_SIZE
            ):
                unit = min(
                    available,
                    key=lambda candidate: (
                        dist(
                            (candidate.x, candidate.y),
                            (checkpoint.x, checkpoint.y),
                        ),
                        candidate.uid,
                    ),
                )
                available.remove(unit)
                guards.add(unit.uid)
                unit.target = None
                unit.target_pos = self._checkpoint_guard_destination(
                    checkpoint, unit
                )

    def _secure_captured_editor_checkpoint(self):
        """Garrison a captured editor hold and begin assembling the next wave."""
        if not self.game.custom_level_active or self.state != AIState.ATTACKING:
            return False
        checkpoint = self.game.checkpoint_by_uid(self.checkpoint_target_uid)
        if checkpoint is None or checkpoint.owner != "red":
            return False
        guards = self.checkpoint_guards.setdefault(checkpoint.uid, set())
        members = self._squad_units()
        guard_slots = max(
            0, self.CUSTOM_CHECKPOINT_GARRISON_SIZE - len(guards)
        )
        new_guards = sorted(
            members,
            key=lambda unit: (
                dist((unit.x, unit.y), (checkpoint.x, checkpoint.y)),
                unit.uid,
            ),
        )[:guard_slots]
        guards.update(unit.uid for unit in new_guards)
        for unit in new_guards:
            unit.target = None
            unit.target_pos = self._checkpoint_guard_destination(
                checkpoint, unit
            )
        self.squad.difference_update(guards)
        self.recovery_guards.clear()
        self.formation_roles = {
            uid: role for uid, role in self.formation_roles.items()
            if uid in self.squad
        }
        self.wave_start_strength = 0
        self.rally_elapsed = 0.0
        self.checkpoint_target_uid = None
        self.checkpoint_route = ()
        self.checkpoint_route_index = 0
        self.formation_checkpoint_uid = None
        self.formation_anchor = None
        self.transition_to(AIState.RALLYING)
        return True

    def _position_checkpoint_guards(self):
        """Return idle editor garrisons to a tight ring around their hold."""
        living = {unit.uid: unit for unit in self._living_red_units()}
        for checkpoint_uid, guard_uids in sorted(self.checkpoint_guards.items()):
            checkpoint = self.game.checkpoint_by_uid(checkpoint_uid)
            if checkpoint is None:
                continue
            for uid in sorted(guard_uids):
                unit = living.get(uid)
                if unit is not None and unit.target is None:
                    unit.target_pos = self._checkpoint_guard_destination(
                        checkpoint, unit
                    )

    def _custom_garrisons_ready(self):
        if not self.game.custom_level_active:
            return True
        if len(self.reserve) < self.CUSTOM_KING_GARRISON_SIZE:
            return False
        return all(
            len(guards) >= self.CUSTOM_CHECKPOINT_GARRISON_SIZE
            for checkpoint_uid, guards in self.checkpoint_guards.items()
            if self.game.checkpoint_by_uid(checkpoint_uid) is not None
        )

    def _position_custom_king_garrison(self):
        if not self.game.custom_level_active:
            return
        living = {unit.uid: unit for unit in self._living_red_units()}
        for uid in sorted(self.reserve):
            unit = living.get(uid)
            if unit is not None and unit.target is None:
                unit.target_pos = self._reserve_position(unit)

    def _reserve_position(self, unit):
        index = sorted(self.reserve).index(unit.uid) if unit.uid in self.reserve else 0
        return (
            self.game.team_king("red").x - 3.0,
            self.game.team_king("red").y + (index - (len(self.reserve) - 1) / 2) * 1.8,
        )

    def _player_threats(self):
        king_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        radius = (
            self.DEFENSE_EXIT_RADIUS
            if self.state == AIState.DEFENDING else self.DEFENSE_ZONE_RADIUS
        )
        threats = []
        for unit in self.game.units:
            if not unit.is_player_commandable or unit.health <= 0:
                continue
            distance = dist((unit.x, unit.y), king_pos)
            attacking_king = unit.target is self.game.team_king("red")
            destination_near_king = (
                unit.target_pos is not None
                and dist(unit.target_pos, king_pos) <= self.DEFENSE_ZONE_RADIUS
            )
            approaching = (
                distance <= self.DEFENSE_APPROACH_RADIUS
                and (attacking_king or destination_near_king)
            )
            if distance <= radius or approaching:
                danger = {
                    "swordsman": 2.0,
                    "archer": 1.5,
                    "shield": 2.4,
                }.get(unit.kind, 1.5 if unit.is_ranged else 2.0)
                danger *= max(.25, unit.health / unit.max_health)
                if attacking_king:
                    danger += 2.5
                elif destination_near_king:
                    danger += .75
                # Units in the hysteresis band count only if they are still advancing.
                if distance > self.DEFENSE_ZONE_RADIUS and not (
                    attacking_king or destination_near_king
                ):
                    danger *= .35
                threats.append((unit, danger))
        return threats

    def _player_unit_is_visible(self, unit, observers=None):
        """Return whether current red-team vision legitimately reveals a unit."""
        if observers is None:
            return self.game.is_team_visible("red", unit.x, unit.y)
        position = (unit.x, unit.y)
        red_objective = self.game.objective_position("red")
        if (
            red_objective is not None
            and self.game.has_terrain_line_of_sight(
                red_objective, position, self.KING_VISION_RADIUS
            )
        ):
            return True
        return any(
            self.game.has_terrain_line_of_sight(
                (observer.x, observer.y), position, self.SCOUTING_RADIUS
            )
            for observer in observers
        )

    def _update_strategic_knowledge(self):
        """Remember only player units actually observed by red scouts or the king."""
        self.game.update_team_visibility("red")
        currently_observed = set()
        for unit in sorted(self.game.units, key=lambda candidate: candidate.uid):
            if not unit.is_player_commandable:
                continue
            if self._player_unit_is_visible(unit):
                if unit.health <= 0:
                    if (
                        unit.uid in self.player_knowledge
                        or unit.uid in self.combat_observations
                    ):
                        self.combat_observation_revision += 1
                    self.player_knowledge.pop(unit.uid, None)
                    self.combat_observations.pop(unit.uid, None)
                    self.last_seen_player_army.pop(unit.uid, None)
                    continue
                currently_observed.add(unit.uid)
                self.player_knowledge[unit.uid] = (unit.kind, self.elapsed)
                self.last_seen_player_army[unit.uid] = LastSeenPlayerUnit(
                    unit.uid,
                    unit.kind,
                    unit.x,
                    unit.y,
                    unit.health,
                    self.elapsed,
                )
                previous = self.combat_observations.get(unit.uid)
                facts = (unit.kind, unit.x, unit.y, unit.health)
                old_facts = (
                    (previous.kind, previous.x, previous.y, previous.health)
                    if previous else None
                )
                if facts != old_facts:
                    self.combat_observation_revision += 1
                self.combat_observations[unit.uid] = ObservedCombatUnit(
                    unit.uid,
                    unit.kind,
                    unit.x,
                    unit.y,
                    unit.health,
                    self.elapsed,
                    self.combat_observation_revision,
                )
        if currently_observed != self._currently_observed_player_uids:
            self.combat_observation_revision += 1
        self._currently_observed_player_uids = currently_observed
        self.player_knowledge = {
            uid: sighting for uid, sighting in self.player_knowledge.items()
            if self.elapsed - sighting[1] <= self.PLAYER_KNOWLEDGE_TTL
        }
        known_uids = set(self.player_knowledge)
        self.combat_observations = {
            uid: sighting for uid, sighting in self.combat_observations.items()
            if uid in known_uids
        }
        self.last_seen_player_army = dict(sorted(
            self.last_seen_player_army.items()
        ))

    def assess_combat_group(self, group, opponent_uids=None):
        """Compare a red group with only the opponents in established memory."""
        group = tuple(
            unit for unit in group
            if unit.is_enemy_ai_commandable and unit.health > 0
        )
        if not group:
            raise ValueError("A combat group must contain living red units")
        observations = tuple(self.combat_observations.values())
        if opponent_uids is None:
            opponents = tuple(
                sighting for sighting in observations
                if min(
                    dist((sighting.x, sighting.y), (unit.x, unit.y))
                    for unit in group
                ) <= self.COMBAT_ENGAGEMENT_RADIUS
            )
        else:
            requested = set(opponent_uids)
            opponents = tuple(
                sighting for sighting in observations if sighting.uid in requested
            )
        own_reinforcements = tuple(
            unit for unit in self._living_red_units()
            if unit.uid not in {member.uid for member in group}
        )
        opponent_ids = {opponent.uid for opponent in opponents}
        opponent_reinforcements = tuple(
            sighting for sighting in observations
            if sighting.uid not in opponent_ids
        )
        return self.combat_evaluator.assess(
            group,
            opponents,
            self.elapsed,
            self.combat_observation_revision,
            own_reinforcements,
            opponent_reinforcements,
        )

    def evaluate_engaged_combat_groups(self):
        """Refresh assessments for the AI's existing strategic combat groups."""
        groups = []
        for uids in (
            self.squad, self.defenders, self.reserve,
            *self.checkpoint_guards.values(),
        ):
            units = [
                unit for unit in self._living_red_units() if unit.uid in uids
            ]
            if units:
                groups.append(units)
        return [
            self.assess_combat_group(group)
            for group in groups
            if any(
                min(dist((seen.x, seen.y), (unit.x, unit.y)) for unit in group)
                <= self.COMBAT_ENGAGEMENT_RADIUS
                for seen in self.combat_observations.values()
            )
        ]

    def _field_combat_assessment(self):
        """Reassess the wave against current or recently engaged opponents."""
        if self.state not in (AIState.ATTACKING, AIState.RECOVERING):
            return None
        group = self._squad_units()
        if not group:
            return None
        nearby = {
            seen.uid
            for seen in self.combat_observations.values()
            if min(
                dist((seen.x, seen.y), (unit.x, unit.y)) for unit in group
            ) <= self.COMBAT_ENGAGEMENT_RADIUS
        }
        currently_seen = nearby & self._currently_observed_player_uids
        if currently_seen:
            self.combat_opponent_uids.update(nearby)
        remembered = self.combat_opponent_uids & set(self.combat_observations)
        if not remembered:
            return None
        return self.assess_combat_group(group, remembered)

    def _strength_decision(self, assessment):
        """Return retreat/re-engage after hysteresis and decision throttling."""
        if assessment is None:
            return None
        ratio = assessment.advantage_ratio
        if assessment.stale:
            proposed = "retreat" if self.state == AIState.ATTACKING else "hold"
        elif self.state == AIState.ATTACKING:
            proposed = "retreat" if ratio <= self.COMBAT_RETREAT_RATIO else "hold"
        else:
            proposed = (
                "reengage" if ratio >= self.COMBAT_REENGAGE_RATIO else "hold"
            )

        urgent = (
            proposed == "retreat"
            and (assessment.stale or ratio <= self.COMBAT_URGENT_RETREAT_RATIO)
        ) or (
            proposed == "reengage"
            and ratio >= self.COMBAT_URGENT_REENGAGE_RATIO
        )
        interval_elapsed = (
            self.elapsed - self.last_combat_decision_at
            >= self.COMBAT_DECISION_INTERVAL
        )
        if not urgent and not interval_elapsed:
            return None
        self.last_combat_decision_at = self.elapsed
        self.last_combat_decision = proposed
        return proposed

    def _attack_objective_is_reachable(self):
        """Return whether the open battlefield has a usable attack objective."""
        objective = self.strategic_objective(self._squad_units())
        if objective is None or getattr(objective, "health", 1) <= 0:
            return False
        return (
            math.isfinite(objective.x)
            and math.isfinite(objective.y)
            and WORLD_MIN <= objective.x <= WORLD_MAX
            and WORLD_MIN <= objective.y <= WORLD_MAX
        )

    def _attack_hard_safety_reason(self):
        """Critical rules that always outrank casualty and strength decisions."""
        if not self._squad_units():
            return "no_viable_combat_units"
        if not self._attack_objective_is_reachable():
            return "no_valid_or_reachable_objective"
        return None

    def _king_within_commitment_radius(self):
        """Keep a wave committed once any member reaches its strategic objective."""
        objective = self.strategic_objective(self._squad_units())
        if objective is None or getattr(objective, "health", 1) <= 0:
            return False
        return any(
            dist((unit.x, unit.y), (objective.x, objective.y))
            <= self.OBJECTIVE_COMMITMENT_RADIUS
            for unit in self._squad_units()
        )

    def _checkpoint_within_commitment_radius(self):
        if not self.game.level.has_checkpoints:
            return False
        checkpoint = self.game.checkpoint_by_uid(self.checkpoint_target_uid)
        if checkpoint is None or checkpoint.owner == "red":
            return False
        return any(
            dist((unit.x, unit.y), (checkpoint.x, checkpoint.y))
            <= checkpoint.profile.defender_leash + self.FORMATION_TOLERANCE
            for unit in self._squad_units()
        )

    def _casualty_retreat_is_overridden(self, assessment):
        """Allow casualty-hit attackers to continue only on fresh strong evidence."""
        if assessment is None or assessment.stale:
            return False
        return (
            assessment.classification == CombatAdvantage.STRONGER
            and self.elapsed - assessment.evaluated_at
            <= self.combat_evaluator.PERIODIC_REFRESH
            and assessment.advantage_ratio > self.CASUALTY_ADVANTAGE_MARGIN
        )

    def _can_finish_objective(self, assessment):
        """Keep firing on a nearly defeated king unless defenders dominate."""
        objective = self.strategic_objective(self._squad_units())
        if isinstance(objective, Checkpoint):
            return False
        if objective is None or objective.health <= 0:
            return False
        attackers = [
            unit for unit in self._squad_units()
            if dist((unit.x, unit.y), (objective.x, objective.y))
            <= self.game.effective_attack_range(unit)
        ]
        if not attackers:
            return False
        if (
            assessment is not None
            and not assessment.stale
            and assessment.advantage_ratio <= self.COMBAT_URGENT_RETREAT_RATIO
        ):
            return False
        damage_per_second = sum(
            unit.damage / unit.cooldown for unit in attackers
        )
        return (
            objective.health / max(damage_per_second, 1e-9)
            <= self.OBJECTIVE_FINISH_SECONDS
        )

    def forget_player_unit(self, uid):
        """Forget a dead player unit only when red vision confirms its death."""
        unit = next(
            (candidate for candidate in self.game.units if candidate.uid == uid),
            None,
        )
        visibly_confirmed = (
            unit is not None and self._player_unit_is_visible(unit)
        )
        if not visibly_confirmed:
            return
        known = (
            uid in self.player_knowledge
            or uid in self.combat_observations
            or uid in self._currently_observed_player_uids
            or uid in self.combat_opponent_uids
        )
        self.player_knowledge.pop(uid, None)
        self.combat_observations.pop(uid, None)
        self._currently_observed_player_uids.discard(uid)
        self.combat_opponent_uids.discard(uid)
        self.last_seen_player_army.pop(uid, None)
        if known:
            self.combat_observation_revision += 1

    def _record_losses(self):
        living = {unit.uid: unit.kind for unit in self._living_red_units()}
        for uid, kind in self._known_red_uids.items():
            if uid not in living:
                self.recent_losses.append((self.elapsed, kind))
        self._known_red_uids = living
        self.recent_losses = [
            loss for loss in self.recent_losses
            if self.elapsed - loss[0] <= self.LOSS_MEMORY_DURATION
        ]

    def known_player_composition(self):
        counts = {kind: 0 for kind in UNIT_KINDS}
        for kind, _ in self.player_knowledge.values():
            if kind in counts:
                counts[kind] += 1
        return counts

    def last_seen_player_composition(self):
        """Return deterministic per-kind unit counts and invested essence."""
        counts = {kind: 0 for kind in UNIT_KINDS}
        essence = {kind: 0 for kind in UNIT_KINDS}
        for sighting in self.last_seen_player_army.values():
            if sighting.kind in counts:
                counts[sighting.kind] += 1
                essence[sighting.kind] += UNIT_COSTS[sighting.kind]
        return counts, essence

    def _update_archer_threat_level(self):
        """Update the remembered archer tier with a one-unit hysteresis band."""
        count = self.known_player_composition()["archer"]
        level = self.archer_threat_level
        if level == "low":
            if count >= self.ARCHER_THREAT_HIGH_THRESHOLD:
                level = "high"
            elif count >= self.ARCHER_THREAT_MODERATE_THRESHOLD:
                level = "moderate"
        elif level == "moderate":
            if count >= self.ARCHER_THREAT_HIGH_THRESHOLD:
                level = "high"
            elif count < (
                self.ARCHER_THREAT_MODERATE_THRESHOLD
                - self.ARCHER_THREAT_HYSTERESIS
            ):
                level = "low"
        elif count < (
            self.ARCHER_THREAT_HIGH_THRESHOLD
            - self.ARCHER_THREAT_HYSTERESIS
        ):
            level = (
                "moderate"
                if count >= self.ARCHER_THREAT_MODERATE_THRESHOLD
                else "low"
            )
        self.archer_threat_level = level
        return level

    def production_scores(self, threat_score=None):
        """Return deterministic weighted utility for each recruitable unit."""
        threat_score = self.last_threat_score if threat_score is None else threat_score
        own = {kind: 0 for kind in UNIT_KINDS}
        assigned = {kind: 0 for kind in UNIT_KINDS}
        squad_counts = {kind: 0 for kind in UNIT_KINDS}
        assigned_uids = (
            self.squad | self.reserve | self.defenders
            | self._checkpoint_guard_uids()
        )
        for unit in self._living_red_units():
            if unit.kind in own:
                own[unit.kind] += 1
                if unit.uid in assigned_uids:
                    assigned[unit.kind] += 1
                if unit.uid in self.squad:
                    squad_counts[unit.kind] += 1
        known = self.known_player_composition()
        known_total = sum(known.values())
        scores = {
            "swordsman": self.BASE_SWORD_SCORE,
            "archer": self.BASE_ARCHER_SCORE,
            "shield": self.BASE_SHIELD_SCORE,
        }
        for kind in scores:
            scores[kind] += self.STATE_PRODUCTION_WEIGHTS[self.state][kind]

        # Unknown armies use the neutral baseline weights; sightings add soft counters.
        if known_total:
            scores["swordsman"] += (
                known["archer"] / known_total * self.EXPOSED_ARCHER_SWORD_BONUS
            )
            scores["archer"] += (
                (known["swordsman"] + known["shield"]) / known_total
                * self.PLAYER_SWORD_ARCHER_BONUS
            )
            scores["shield"] += (
                known["swordsman"] / known_total * self.PLAYER_MELEE_SHIELD_BONUS
            )
        archer_threat_level = self._update_archer_threat_level()
        scores["shield"] += self.ARCHER_THREAT_SHIELD_BONUS[archer_threat_level]
        scores["swordsman"] -= self.ARCHER_THREAT_SWORD_PENALTY[archer_threat_level]

        total = sum(own.values())
        projected_sword_ratio = (own["swordsman"] + 1) / (total + 1)
        if projected_sword_ratio > self.SWORD_TARGET_RATIO:
            scores["swordsman"] -= (
                (projected_sword_ratio - self.SWORD_TARGET_RATIO)
                * self.SWORD_OVER_TARGET_PENALTY
            )
        frontline = own["swordsman"] + own["shield"]
        required_frontline = max(
            self.MIN_FRONTLINE,
            math.ceil((total + 1) * self.FRONTLINE_RATIO),
        )
        frontline_shortage = max(0, required_frontline - frontline)
        scores["swordsman"] += (
            frontline_shortage * self.FRONTLINE_SHORTAGE_SWORD_BONUS
        )
        scores["shield"] += (
            frontline_shortage * self.FRONTLINE_SHORTAGE_SHIELD_BONUS
        )
        if frontline >= required_frontline:
            scores["archer"] += self.PROTECTED_ARCHER_BONUS
            if total >= self.MISSING_BACKLINE_MIN_ARMY_SIZE and own["archer"] == 0:
                scores["archer"] += self.MISSING_BACKLINE_BONUS
        else:
            scores["archer"] -= self.UNPROTECTED_ARCHER_PENALTY
        if own["archer"] and own["shield"] == 0:
            scores["shield"] += self.DURABLE_FRONTLINE_BONUS
        if squad_counts["archer"] and squad_counts["shield"] == 0:
            scores["shield"] += self.SQUAD_SHIELD_SHORTAGE_BONUS
        if self.state == AIState.DEFENDING:
            scores["shield"] += self.KING_DEFENSE_SHIELD_BONUS

        if threat_score >= self.SERIOUS_THREAT_SCORE:
            scores["swordsman"] += self.EMERGENCY_SWORD_BONUS
            scores["shield"] -= self.URGENT_SHIELD_PENALTY
        loss_counts = {
            kind: sum(loss_kind == kind for _, loss_kind in self.recent_losses)
            for kind in ENEMY_PRODUCTION_KINDS
        }
        scores["swordsman"] += loss_counts["swordsman"] * self.RECENT_SWORD_LOSS_BONUS
        scores["archer"] += loss_counts["archer"] * self.RECENT_ARCHER_LOSS_BONUS
        scores["shield"] += loss_counts["shield"] * self.RECENT_SHIELD_LOSS_BONUS
        scores["swordsman"] += self.failed_waves * self.FAILED_WAVE_FRONTLINE_BONUS
        scores["shield"] += self.failed_waves * self.FAILED_WAVE_SHIELD_BONUS

        # Assigned composition matters explicitly: an attack with no assigned screen
        # should replenish melee even if unassigned archers are waiting at home.
        if assigned["archer"] and not (assigned["swordsman"] + assigned["shield"]):
            scores["swordsman"] += self.FRONTLINE_SHORTAGE_SWORD_BONUS
            scores["shield"] += self.FRONTLINE_SHORTAGE_SHIELD_BONUS
        if own["shield"] and not (own["swordsman"] + own["archer"]):
            scores["shield"] -= self.SHIELD_ONLY_PENALTY
            scores["swordsman"] += self.SHIELD_ONLY_SWORD_BONUS
        if self.last_production_choice:
            scores[self.last_production_choice] += self.SCORE_HYSTERESIS
        self.last_production_scores = scores
        return scores

    def production_essence_investment(self):
        """Return current red-army essence invested in each unit kind."""
        invested = {kind: 0 for kind in ENEMY_PRODUCTION_KINDS}
        for unit in self._living_red_units():
            if unit.kind in invested:
                invested[unit.kind] += UNIT_COSTS[unit.kind]
        return invested

    def production_target_shares(self):
        """Return strategic counter shares, always measured by essence cost."""
        if self.game.level.has_checkpoints and self.state in (
            AIState.BUILDING, AIState.RALLYING, AIState.ATTACKING
        ):
            checkpoint = self.game.checkpoint_by_uid(self.checkpoint_target_uid)
            if checkpoint is None or checkpoint.owner == "red":
                checkpoint = self._select_checkpoint_objective(
                    self._squad_units()
                )
            if checkpoint is not None:
                self.checkpoint_target_uid = checkpoint.uid
                if checkpoint.owner == checkpoint.native_faction:
                    return self.CHECKPOINT_PRODUCTION_SHARES[
                        checkpoint.native_faction
                    ].copy()
        if not self.learned_counter_essence:
            return self.STANDARD_PRODUCTION_SHARES.copy()
        total = sum(self.learned_counter_essence.values())
        if total <= 0:
            return self.STANDARD_PRODUCTION_SHARES.copy()
        return {
            kind: self.learned_counter_essence.get(kind, 0) / total
            for kind in ENEMY_PRODUCTION_KINDS
        }

    def _production_balance(self):
        """Describe current spending against the strategic essence target."""
        invested = self.production_essence_investment()
        shares = self.production_target_shares()
        total = sum(invested.values())
        return {
            "target_shares": shares,
            "spent_essence": invested,
            "target_essence": {
                kind: total * shares[kind] for kind in ENEMY_PRODUCTION_KINDS
            },
            "deficits": {
                kind: total * shares[kind] - invested[kind]
                for kind in ENEMY_PRODUCTION_KINDS
            },
        }

    def _target_essence_choice(self, available):
        """Choose the purchase that most reduces projected target-share error."""
        invested = self.production_essence_investment()
        target_shares = self.production_target_shares()

        def projected_error(kind):
            projected = invested.copy()
            projected[kind] += UNIT_COSTS[kind]
            total = sum(projected.values())
            return sum(
                abs(projected[other] / total - target_shares[other])
                for other in ENEMY_PRODUCTION_KINDS
            )

        order = {kind: index for index, kind in enumerate(ENEMY_PRODUCTION_KINDS)}
        return min(
            available,
            key=lambda kind: (projected_error(kind), order[kind]),
        )

    def choose_production(self, threat_score=None):
        scores = self.production_scores(threat_score)
        essence = self.game.enemy_essence
        available = [
            kind for kind in ENEMY_PRODUCTION_KINDS
            if kind not in self.unavailable_production_kinds
        ]
        affordable = [
            kind for kind in available if essence >= UNIT_COSTS[kind]
        ]
        if not affordable:
            return None
        best = self._target_essence_choice(available)
        if best not in affordable:
            serious = (
                threat_score
                if threat_score is not None
                else self.last_threat_score
            )
            if serious < self.SERIOUS_THREAT_SCORE:
                return None
            best = self._target_essence_choice(affordable)
        return best

    def _run_production(self, threat_score):
        if self.recruitment_timer > 0:
            return None
        kind = self.choose_production(threat_score)
        if kind is None:
            # Reconsider savings frequently without allowing per-frame oscillation.
            self.recruitment_timer = self.PRODUCTION_INTERVAL / 3
            return None
        balance_before = self._production_balance()
        if self.game.recruit(kind, "red"):
            self.last_production_choice = kind
            balance_after = self._production_balance()
            self.production_history.append({
                "time": self.elapsed,
                "state": self.state.name,
                "kind": kind,
                "scores": self.last_production_scores.copy(),
                "target_shares": balance_before["target_shares"],
                "spent_essence": balance_after["spent_essence"],
                "selected_deficit": balance_before["deficits"][kind],
            })
            self._known_red_uids[self.game.units[-1].uid] = kind
            self.recruitment_timer = self.PRODUCTION_INTERVAL
            return kind
        self.recruitment_timer = self.PRODUCTION_INTERVAL / 3
        return None

    def _defensive_target_score(self, target):
        king_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        distance = dist((target.x, target.y), king_pos)
        score = 120.0 - distance * 6.0
        if target.target is self.game.team_king("red"):
            score += 90.0
        if target.target_pos is not None:
            score += max(0.0, 30.0 - dist(target.target_pos, king_pos) * 2.0)
        score += (1.0 - target.health / target.max_health) * 12.0
        if target.kind == "archer":
            score += 8.0
        return score

    def _enter_defense(self, threats, threat_score):
        self.pre_defense_state = self.state
        self.transition_to(AIState.DEFENDING)
        self.defense_clear_elapsed = 0.0
        self.emergency_recruited = False
        self._assign_defenders(threats, threat_score)

    def _assign_defenders(self, threats, threat_score):
        red_units = self._living_red_units()
        by_uid = {unit.uid: unit for unit in red_units}
        selected = [by_uid[uid] for uid in sorted(self.reserve) if uid in by_uid]
        king_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        nearby = [
            unit for unit in red_units
            if unit.uid not in self.defenders and unit.uid not in self.reserve
            and unit.uid not in self.squad
            and unit.uid not in self._checkpoint_guard_uids()
            and dist((unit.x, unit.y), king_pos) <= self.DEFENDER_ASSIGN_RADIUS
        ]
        selected.extend(sorted(
            nearby, key=lambda unit: (dist((unit.x, unit.y), king_pos), unit.uid)
        ))
        if threat_score >= self.RECALL_THREAT_THRESHOLD:
            attackers = [
                unit for unit in red_units
                if unit.uid in self.squad and unit.uid not in self.defenders
            ]
            needed = max(1, math.ceil(threat_score / 2) - len(selected))
            selected.extend(sorted(
                attackers,
                key=lambda unit: (dist((unit.x, unit.y), king_pos), unit.uid),
            )[:needed])
        self.defenders.update(unit.uid for unit in selected)

        ordered_threats = sorted(
            (entry[0] for entry in threats),
            key=lambda target: (-self._defensive_target_score(target), target.uid),
        )
        advance = self._unit_vector(
            king_pos, (self.game.team_king("green").x, self.game.team_king("green").y)
        )
        for index, unit in enumerate(selected):
            unit.target = None
            if unit.kind == "archer":
                # Fire from the far side of the king, away from the incoming line.
                side = (index % 3 - 1) * 1.8
                unit.target_pos = (
                    self.game.team_king("red").x - advance[0] * self.ARCHER_DEFENSE_OFFSET,
                    self.game.team_king("red").y - advance[1] * self.ARCHER_DEFENSE_OFFSET + side,
                )
            elif ordered_threats:
                target = ordered_threats[index % len(ordered_threats)]
                unit.target_pos = (target.x, target.y)
            else:
                unit.target_pos = self._reserve_position(unit)

    def _finish_defense(self):
        living = {unit.uid for unit in self._living_red_units()}
        survivors = self.defenders & living
        reserve_size = (
            self.CUSTOM_KING_GARRISON_SIZE
            if self.game.custom_level_active
            else self.DEFENSIVE_RESERVE_SIZE
        )
        self.reserve = set(sorted(
            (self.reserve | survivors) & living
        )[:reserve_size])
        for uid in survivors:
            self.squad.discard(uid)
            self.formation_roles.pop(uid, None)
        self.defenders.clear()
        if self.pre_defense_state == AIState.ATTACKING and self._squad_units():
            next_state = AIState.ATTACKING
        elif self.pre_defense_state == AIState.RECOVERING:
            next_state = AIState.RECOVERING
        elif self._living_red_units():
            next_state = AIState.RALLYING
        else:
            next_state = AIState.BUILDING
        self.transition_to(next_state)
        for unit in self._living_red_units():
            if unit.uid in self.reserve:
                unit.target = None
                unit.target_pos = self._reserve_position(unit)
        if next_state == AIState.ATTACKING:
            self._advance_wave()

    def _formation_ready(self):
        members = self._squad_units()
        if not members:
            return False
        in_position = sum(
            dist((unit.x, unit.y), self._formation_destination(unit, members))
            <= self.FORMATION_TOLERANCE
            for unit in members
        )
        return in_position / len(members) >= self.FORMATION_READY_FRACTION

    def _launch_strength_gate(self):
        """Require the complete proposed wave to beat the last-seen player army.

        Strategic sightings persist after tactical observations become stale, so
        launch authorization uses CombatStrengthEvaluator's numeric ratio rather
        than its freshness-sensitive classification.  The safety margin is the
        evaluator's documented STRONGER_RATIO (currently 1.25).
        """
        members = tuple(self._squad_units())
        if not members:
            return False
        if not self._custom_garrisons_ready():
            self.last_launch_gate = {
                "time": self.elapsed,
                "squad_essence": self._group_essence(members),
                "decision": "garrison_wait",
                "target": (
                    f"checkpoint:{self.checkpoint_target_uid}"
                    if self.checkpoint_target_uid is not None else "king"
                ),
                "observation_revision": self.combat_observation_revision,
            }
            return False
        minimum_units = (
            self.LEVEL_FIVE_MIN_ATTACK_UNITS
            if self.game.level_number == 5
            else self.CHECKPOINT_MIN_ATTACK_UNITS
            if self.game.level.has_checkpoints
            else 0
        )
        squad_essence = self._group_essence(members)
        if self.game.level.has_checkpoints:
            checkpoint = self._select_checkpoint_objective(members)
            if checkpoint is not None:
                self.checkpoint_target_uid = checkpoint.uid
                defenders, route, eta, defender_composition = (
                    self.projected_checkpoint_defenders(checkpoint, members)
                )
                own_strength = self._raw_group_strength(members, defenders)
                opponent_strength = self._raw_group_strength(defenders, members)
                ratio = (
                    math.inf if not defenders
                    else own_strength / max(
                        opponent_strength,
                        CombatStrengthEvaluator.MIN_STRENGTH,
                    )
                )
                passed = (
                    ratio >= self.CHECKPOINT_ATTACK_RATIO
                    and len(members) >= minimum_units
                )
                attacker_composition = {
                    kind: sum(unit.kind == kind for unit in members)
                    for kind in ENEMY_PRODUCTION_KINDS
                }
                self.projected_arrival_eta = eta
                self.projected_defender_count = len(defenders)
                self.projected_defender_strength = opponent_strength
                self.projected_defender_composition = defender_composition.copy()
                diagnostic = {
                    "time": self.elapsed,
                    "own_strength": own_strength,
                    "opponent_strength": opponent_strength,
                    "ratio": ratio,
                    "squad_essence": squad_essence,
                    "decision": (
                        "checkpoint_strength_pass" if passed
                        else "checkpoint_force_wait"
                        if len(members) < minimum_units
                        else "checkpoint_strength_hold"
                    ),
                    "checkpoint_uid": checkpoint.uid,
                    "target": f"checkpoint:{checkpoint.uid}",
                    "eta": eta,
                    "projected_defender_count": len(defenders),
                    "projected_defender_strength": opponent_strength,
                    "projected_defender_composition": defender_composition,
                    "projected_attacker_composition": attacker_composition,
                    "route": route,
                    "observation_revision": self.combat_observation_revision,
                }
                signature = (
                    tuple((unit.uid, unit.kind, round(unit.health, 6)) for unit in members),
                    tuple((unit.uid, unit.kind, round(unit.health, 6)) for unit in defenders),
                    diagnostic["decision"], checkpoint.uid,
                )
                self.last_launch_gate = diagnostic
                if signature != self._launch_gate_signature:
                    self.launch_gate_history.append(diagnostic.copy())
                    self._launch_gate_signature = signature
                return passed
        cost_ready = squad_essence >= self.TARGET_GROUP_ESSENCE
        force_ready = len(members) >= minimum_units
        if not self.last_seen_player_army:
            assessment = self.combat_evaluator.assess(
                members,
                (),
                self.elapsed,
                self.combat_observation_revision,
            )
            diagnostic = {
                "time": self.elapsed,
                "own_strength": assessment.own_strength,
                "opponent_strength": assessment.opponent_strength,
                "ratio": assessment.advantage_ratio,
                "squad_essence": squad_essence,
                "decision": (
                    "bootstrap_ready" if cost_ready and force_ready
                    else "force_wait" if not force_ready
                    else "bootstrap_wait"
                ),
                "observation_revision": self.combat_observation_revision,
            }
            passed = cost_ready and force_ready
        else:
            opponents = tuple(
                ObservedCombatUnit(
                    seen.uid,
                    seen.kind,
                    seen.x,
                    seen.y,
                    seen.health,
                    seen.observed_at,
                    self.combat_observation_revision,
                )
                for seen in self.last_seen_player_army.values()
            )
            assessment = self.combat_evaluator.assess(
                members,
                opponents,
                self.elapsed,
                self.combat_observation_revision,
            )
            passed = cost_ready and force_ready and (
                assessment.advantage_ratio
                >= self.combat_evaluator.STRONGER_RATIO
            )
            diagnostic = {
                "time": self.elapsed,
                "own_strength": assessment.own_strength,
                "opponent_strength": assessment.opponent_strength,
                "ratio": assessment.advantage_ratio,
                "squad_essence": squad_essence,
                "decision": (
                    "force_wait" if not force_ready
                    else "essence_wait" if not cost_ready
                    else "strength_pass" if passed
                    else "strength_hold"
                ),
                "observation_revision": self.combat_observation_revision,
            }
        signature = (
            tuple((unit.uid, unit.kind, round(unit.health, 6))
                  for unit in members),
            tuple((seen.uid, seen.kind, round(seen.health, 6))
                  for seen in self.last_seen_player_army.values()),
            diagnostic["decision"],
            self.combat_observation_revision,
        )
        self.last_launch_gate = diagnostic
        if signature != self._launch_gate_signature:
            self.launch_gate_history.append(diagnostic.copy())
            self._launch_gate_signature = signature
        return passed

    def _launch_wave(self):
        members = self._squad_units()
        if not members:
            return
        self.wave_number += 1
        self.wave_start_strength = len(members)
        composition = {
            kind: sum(unit.kind == kind for unit in members)
            for kind in UNIT_KINDS
        }
        self.wave_history.append({
            "wave": self.wave_number,
            "launched_at": self.elapsed,
            "wait": self.rally_elapsed,
            "composition": composition,
            "squad_essence": self._group_essence(members),
            "objective": (
                f"checkpoint:{self.checkpoint_target_uid}"
                if self.checkpoint_target_uid is not None else "king"
            ),
            "launch_gate": self.last_launch_gate.copy()
            if self.last_launch_gate else None,
        })
        self.transition_to(AIState.ATTACKING)
        self.combat_opponent_uids.clear()
        self.last_combat_decision_at = float("-inf")
        self.last_combat_decision = None
        for unit in members:
            unit.target = None
        checkpoint = self.game.checkpoint_by_uid(self.checkpoint_target_uid)
        if checkpoint is not None and checkpoint.owner != "red":
            self.checkpoint_route = self._terrain_route_to_checkpoint(checkpoint)
            self.checkpoint_route_index = min(1, len(self.checkpoint_route) - 1)
            self.formation_checkpoint_uid = checkpoint.uid
            self.formation_anchor = self.checkpoint_route[0]
        else:
            self.checkpoint_route = ()
            self.checkpoint_route_index = 0
            self.formation_checkpoint_uid = None
            self.formation_anchor = None
        self._advance_wave()

    def _advance_checkpoint_formation(self, checkpoint, members):
        """Move one shared route anchor only when three quarters stay formed."""
        if (
            checkpoint.owner == checkpoint.native_faction
            and not checkpoint.defender_uids
        ):
            ordered = sorted(members, key=lambda unit: unit.uid)
            for index, unit in enumerate(ordered):
                angle = math.tau * index / max(1, len(ordered))
                unit.target_pos = (
                    checkpoint.x + math.cos(angle) * 1.25,
                    checkpoint.y + math.sin(angle) * 1.25,
                )
            return
        if (
            self.formation_checkpoint_uid != checkpoint.uid
            or not self.checkpoint_route
            or self.formation_anchor is None
        ):
            self.checkpoint_route = self._terrain_route_to_checkpoint(checkpoint)
            self.checkpoint_route_index = min(1, len(self.checkpoint_route) - 1)
            self.formation_checkpoint_uid = checkpoint.uid
            self.formation_anchor = self.checkpoint_route[0]
        destinations = {
            unit.uid: self._formation_destination(
                unit, members, anchor=self.formation_anchor
            )
            for unit in members
        }
        cohesive = sum(
            dist((unit.x, unit.y), destinations[unit.uid])
            <= self.FORMATION_TOLERANCE
            for unit in members
        ) / len(members)
        if cohesive >= self.CHECKPOINT_COHESION_FRACTION:
            remaining = (
                min(unit.speed for unit in members) * self.decision_interval
                * terrain_movement_multiplier(
                    self.game.terrain_kind_at(self.formation_anchor)
                )
            )
            anchor_x, anchor_y = self.formation_anchor
            while remaining > 1e-9 and self.checkpoint_route_index < len(
                self.checkpoint_route
            ):
                waypoint = self.checkpoint_route[self.checkpoint_route_index]
                segment = dist((anchor_x, anchor_y), waypoint)
                if segment <= remaining + 1e-9:
                    anchor_x, anchor_y = waypoint
                    remaining -= segment
                    self.checkpoint_route_index += 1
                else:
                    anchor_x += (waypoint[0] - anchor_x) / segment * remaining
                    anchor_y += (waypoint[1] - anchor_y) / segment * remaining
                    remaining = 0.0
            self.formation_anchor = clamp_to_map((anchor_x, anchor_y))
        for unit in members:
            if unit.target is None:
                unit.target_pos = self._formation_destination(
                    unit, members, anchor=self.formation_anchor
                )

    def _advance_wave(self):
        """Advance toward the objective while allowing local combat to take priority."""
        self.recovery_guards.clear()
        members = self._squad_units()
        if not members:
            return
        strategic_objective = self.strategic_objective(members)
        if strategic_objective is None:
            return
        if isinstance(strategic_objective, Checkpoint):
            self._advance_checkpoint_formation(strategic_objective, members)
            return
        objective = (strategic_objective.x, strategic_objective.y)
        direction_target = (
            objective
            if isinstance(strategic_objective, Checkpoint)
            else (self.game.team_king("green").x, self.game.team_king("green").y)
        )
        advance_x, advance_y = self._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            direction_target,
        )
        formation_progress = {
            unit.uid: (
                unit.x * advance_x + unit.y * advance_y
                + self.FORMATION_FORWARD_OFFSETS[self._formation_role(unit)]
            )
            for unit in members
        }
        front = min(formation_progress.values())
        anchor_tolerance = max(
            0.0,
            self.WAVE_COHESION_TOLERANCE
            - max(self.FORMATION_FORWARD_OFFSETS.values()),
        )
        for unit in members:
            if unit.target is not None:
                continue
            progress = formation_progress[unit.uid]
            # Any rank that outruns the common formation anchor waits for the
            # rest; otherwise idle movement restores its centered rank slot.
            if progress > front + anchor_tolerance:
                unit.target_pos = (unit.x, unit.y)
            else:
                unit.target_pos = self._formation_destination(
                    unit, members, anchor=objective
                )

    def _victorious_player_composition(self, opponent_uids):
        """Snapshot the currently observed, living encounter army by cost."""
        opponent_uids = set(opponent_uids)
        if not opponent_uids or not opponent_uids <= self._currently_observed_player_uids:
            return None
        living_players = {
            unit.uid: unit
            for unit in self.game.units
            if unit.is_player_commandable and unit.health > 0
        }
        if not opponent_uids <= set(living_players):
            return None
        essence = {kind: 0 for kind in ENEMY_PRODUCTION_KINDS}
        for uid in sorted(opponent_uids):
            unit = living_players[uid]
            if unit.kind not in essence:
                return None
            essence[unit.kind] += UNIT_COSTS[unit.kind]
        return essence if sum(essence.values()) > 0 else None

    def _fresh_victorious_player_composition(self, assessment):
        """Return a snapshot only when fresh evidence identifies the victor."""
        if (
            assessment is None
            or assessment.stale
            or assessment.advantage_ratio > self.COMBAT_RETREAT_RATIO
            or self.elapsed - assessment.evaluated_at
            > self.combat_evaluator.PERIODIC_REFRESH
        ):
            return None
        return self._victorious_player_composition(assessment.opponent_uids)

    def _learn_victorious_player_composition(self, player_essence):
        """Replace the strategic counter target from one confirmed AI defeat."""
        if not player_essence:
            return False
        total = sum(
            amount for kind, amount in player_essence.items()
            if kind in self.PRODUCTION_COUNTERS and amount > 0
        )
        if total <= 0:
            return False
        learned = {kind: 0 for kind in ENEMY_PRODUCTION_KINDS}
        for player_kind, contribution in player_essence.items():
            if player_kind in self.PRODUCTION_COUNTERS and contribution > 0:
                learned[self.PRODUCTION_COUNTERS[player_kind]] += contribution
        self.learned_counter_essence = learned
        return True

    def _begin_recovery(self, victorious_player_composition=None):
        if self._king_within_commitment_radius():
            self._advance_wave()
            return
        self._cleanup_squad()
        self._learn_victorious_player_composition(
            victorious_player_composition
        )
        if self.wave_start_strength and len(self._squad_units()) < self.wave_start_strength:
            self.failed_waves += 1
        self.transition_to(AIState.RECOVERING)
        self.recovery_elapsed = 0.0
        members = self._squad_units()
        player_king_pos = (self.game.team_king("green").x, self.game.team_king("green").y)
        guards = sorted(
            (unit for unit in members if unit.kind == "shield"),
            key=lambda unit: (dist((unit.x, unit.y), player_king_pos), unit.uid),
        )[:2]
        self.recovery_guards = {unit.uid for unit in guards}
        for unit in members:
            unit.target = None
            unit.target_pos = (
                (unit.x, unit.y)
                if unit.uid in self.recovery_guards
                else self.rally_point
            )

    def _finish_recovery(self):
        self.squad.clear()
        self.recovery_guards.clear()
        self.formation_roles.clear()
        self.wave_start_strength = 0
        self.rally_elapsed = 0.0
        self.combat_opponent_uids.clear()
        self.last_combat_decision_at = float("-inf")
        self.last_combat_decision = None
        next_state = AIState.RALLYING if self._living_red_units() else AIState.BUILDING
        self.transition_to(next_state)

    def _is_valid_target(self, unit, target):
        if target is None or getattr(target, "health", 0) <= 0:
            return False
        if getattr(target, "team", unit.team) == unit.team:
            return False
        if not self.game.is_team_visible(unit.team, target.x, target.y):
            return False
        return dist((unit.x, unit.y), (target.x, target.y)) <= max(
            self.auto_engagement_radius(), self.game.effective_attack_range(unit)
        )

    def retreat_ordered(self, unit):
        """Return whether this unit must disengage instead of auto-attacking."""
        return (
            self.state == AIState.RECOVERING
            and unit.uid in self.squad
            and unit.uid not in self.recovery_guards
        )

    def auto_engagement_radius(self):
        """Limit idle armies without reducing active attack or defense awareness."""
        if self.state in (AIState.ATTACKING, AIState.DEFENDING):
            return self.AWARENESS_RADIUS
        return self.PASSIVE_ENGAGEMENT_RADIUS

    def _threatens(self, target, protected):
        if target.target is protected:
            return True
        if target.target_pos is None:
            return False
        return (
            dist(target.target_pos, (protected.x, protected.y))
            <= self.game.effective_attack_range(protected) + 1.0
        )

    def target_score(self, unit, target):
        """Score only locally observable targets; larger values are more desirable."""
        distance = dist((unit.x, unit.y), (target.x, target.y))
        score = 100.0 - distance * 5.0

        # Active attackers are urgent, especially when they threaten this unit.
        if target.target is unit:
            score += 45.0
        elif self._threatens(target, unit):
            score += 28.0
        if self.game.effective_attack_range(target) >= distance:
            score += 14.0

        # Finishing a unit is valuable, but does not outweigh every immediate danger.
        health_ratio = target.health / target.max_health
        score += (1.0 - health_ratio) * 30.0
        if target.health <= unit.damage:
            score += 32.0

        if unit.kind in MELEE_UNIT_KINDS and target.kind == "archer":
            score += 34.0
        elif unit.kind == "archer":
            if target.kind == "archer":
                score += 12.0
            if (
                target.damage >= unit.health
                or target.kind in MELEE_UNIT_KINDS and distance <= 5.0
            ):
                score += 22.0

        # Locally protect fragile allied archers.
        allied_archers = [
            ally for ally in self.game.nearby_units(
                unit, self.AWARENESS_RADIUS
            )
            if ally.team == unit.team and ally.kind == "archer" and ally.health > 0
        ]
        if any(
            dist((target.x, target.y), (ally.x, ally.y)) <= self.ARCHER_PROTECTION_RADIUS
            or self._threatens(target, ally)
            for ally in allied_archers
        ):
            score += 32.0

        # Units approaching or attacking the red king receive defensive priority.
        protected_king = self.game.team_king("red")
        if protected_king is not None and (
            dist((target.x, target.y), (protected_king.x, protected_king.y))
            <= self.KING_DEFENSE_RADIUS
            or target.target is protected_king
        ):
            score += 70.0
        return score

    def choose_target(self, unit):
        if not unit.is_enemy_ai_commandable:
            unit.target = None
            return None
        if not self.game._movement_snapshot_active:
            self.game.rebuild_unit_spatial_hash()
        # A recovering squad has received an explicit retreat order. Local
        # awareness must not turn that order back into an individual attack;
        # the strategic controller will either re-engage the whole squad or
        # interrupt recovery to defend the king.
        if self.retreat_ordered(unit):
            unit.target = None
            return None
        if self.state == AIState.RECOVERING and unit.uid in self.recovery_guards:
            candidates = [
                opponent for opponent in self.game.units
                if opponent.team != unit.team
                and opponent.health > 0
                and dist((unit.x, unit.y), (opponent.x, opponent.y))
                <= self.game.effective_attack_range(unit)
            ]
            unit.target = min(
                candidates,
                key=lambda opponent: (
                    dist((unit.x, unit.y), (opponent.x, opponent.y)),
                    opponent.uid,
                ),
                default=None,
            )
            return unit.target

        guard_checkpoint = self._checkpoint_guard_for(unit)
        guards_king = self.game.custom_level_active and unit.uid in self.reserve
        red_king = self.game.team_king("red")

        def eligible(target):
            return self._is_valid_target(unit, target) and (
                guard_checkpoint is None
                or dist(
                    (target.x, target.y),
                    (guard_checkpoint.x, guard_checkpoint.y),
                ) <= guard_checkpoint.profile.defender_leash
            ) and (
                not guards_king
                or red_king is not None and dist(
                    (target.x, target.y), (red_king.x, red_king.y)
                ) <= self.KING_DEFENSE_RADIUS
            )

        candidates = [
            opponent for opponent in self.game.nearby_units(
                unit, max(self.auto_engagement_radius(),
                          self.game.effective_attack_range(unit))
            )
            if eligible(opponent)
        ]
        current = unit.target if eligible(unit.target) else None
        if not candidates:
            unit.target = None
            return None

        score = (
            self._defensive_target_score
            if self.state == AIState.DEFENDING and unit.uid in self.defenders
            else lambda target: self.target_score(unit, target)
        )
        best = max(candidates, key=lambda target: (
            score(target),
            -getattr(target, "uid", 0),
        ))
        if current is not None and best is not current:
            if score(best) < score(current) + self.SWITCH_MARGIN:
                best = current
        unit.target = best
        return best

    @staticmethod
    def _unit_vector(origin, destination):
        dx, dy = destination[0] - origin[0], destination[1] - origin[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return 0.0, 0.0
        return dx / length, dy / length

    def _constrain_tactical_position(self, unit, position):
        """Keep local steering subordinate to the current strategic posture."""
        x, y = position
        guard_checkpoint = self._checkpoint_guard_for(unit)
        if guard_checkpoint is not None:
            anchor = (guard_checkpoint.x, guard_checkpoint.y)
            radius = guard_checkpoint.profile.defender_leash
        elif self.game.custom_level_active and unit.uid in self.reserve:
            anchor = (self.game.team_king("red").x, self.game.team_king("red").y)
            radius = self.KING_DEFENSE_RADIUS
        elif self.state == AIState.DEFENDING:
            anchor = (self.game.team_king("red").x, self.game.team_king("red").y)
            radius = self.KING_DEFENSE_RADIUS
        elif self.state in (AIState.RALLYING, AIState.BUILDING, AIState.RECOVERING):
            anchor = unit.target_pos or (unit.x, unit.y)
            radius = self.RALLY_LEASH
        else:
            anchor = None
            radius = 0
        if anchor is not None:
            dx, dy = x - anchor[0], y - anchor[1]
            length = math.hypot(dx, dy)
            if length > radius:
                x, y = anchor[0] + dx / length * radius, anchor[1] + dy / length * radius
        return clamp_to_map((x, y))

    def tactical_destination(self, unit, dt):
        """Return a short-lived local steering goal for enemy units only."""
        if not unit.is_enemy_ai_commandable:
            unit.tactical_pos = None
            return None
        if not self.game._movement_snapshot_active:
            self.game.rebuild_unit_spatial_hash()
        unit.tactical_timer = max(0.0, unit.tactical_timer - dt)
        if (
            self.state == AIState.RECOVERING
            and unit.uid in self.recovery_guards
        ):
            unit.tactical_pos = None
            return None
        if unit.tactical_timer > 0 and unit.tactical_pos is None:
            return unit.tactical_pos
        opponents = [
            other for other in self.game.nearby_units(
                unit, self.AWARENESS_RADIUS
            )
            if other.team != unit.team and other.health > 0
            and self.game.is_team_visible(unit.team, other.x, other.y)
        ]

        if unit.kind == "archer":
            melee = [
                other for other in opponents if other.kind in MELEE_UNIT_KINDS
            ]
            threat = min(
                melee,
                key=lambda other: dist((unit.x, unit.y), (other.x, other.y)),
                default=None,
            )
            threat_distance = (
                dist((unit.x, unit.y), (threat.x, threat.y)) if threat else math.inf
            )
            # A safe archer with a shot should fire instead of shuffling for formation.
            target = unit.target
            if (
                threat_distance >= self.ARCHER_DANGER_RADIUS
                and target is not None
                and dist((unit.x, unit.y), (target.x, target.y))
                <= self.game.effective_attack_range(unit)
            ):
                unit.tactical_pos = None
                unit.tactical_timer = 0
                return None
            if threat is not None and (
                threat_distance < self.ARCHER_DANGER_RADIUS
                or unit.tactical_pos is not None
                and threat_distance < self.ARCHER_SAFE_RADIUS
            ):
                if unit.tactical_pos is None or unit.tactical_timer <= 0:
                    away_x, away_y = self._unit_vector(
                        (threat.x, threat.y), (unit.x, unit.y)
                    )
                    if away_x == away_y == 0:
                        away_x = -1.0 if unit.uid % 2 else 1.0
                    travel = max(1.0, self.ARCHER_SAFE_RADIUS - threat_distance)
                    # At an edge, an angled fallback preserves retreat distance
                    # instead of repeatedly steering into the boundary.
                    directions = (
                        (away_x, away_y),
                        (-away_y, away_x),
                        (away_y, -away_x),
                    )
                    candidates = [
                        self._constrain_tactical_position(
                            unit, (unit.x + dx * travel, unit.y + dy * travel)
                        )
                        for dx, dy in directions
                    ]
                    unit.tactical_pos = max(
                        candidates,
                        key=lambda point: (
                            dist(point, (threat.x, threat.y)),
                            -point[0],
                            -point[1],
                        ),
                    )
                    unit.tactical_timer = self.TACTICAL_RECHECK
                return unit.tactical_pos
            unit.tactical_pos = None

        elif unit.kind in MELEE_UNIT_KINDS:
            allied_archers = [
                ally for ally in self.game.nearby_units(
                    unit, self.AWARENESS_RADIUS
                )
                if ally.team == unit.team and ally.kind == "archer" and ally.health > 0
            ]
            screen = None
            for archer in allied_archers:
                threats = [
                    foe for foe in self.game.unit_spatial_hash.neighbors(
                        (archer.x, archer.y),
                        self.ARCHER_PROTECTION_RADIUS + 2.0,
                    )
                    if foe.team != unit.team and foe.health > 0
                    and self.game.is_team_visible(unit.team, foe.x, foe.y)
                    if dist((archer.x, archer.y), (foe.x, foe.y))
                    <= self.ARCHER_PROTECTION_RADIUS + 2.0
                ]
                if threats:
                    threat = min(
                        threats,
                        key=lambda foe: dist((archer.x, archer.y), (foe.x, foe.y)),
                    )
                    score = dist((archer.x, archer.y), (threat.x, threat.y))
                    if screen is None or score < screen[0]:
                        screen = score, archer, threat
            if screen is not None and (
                unit.target is None
                or dist((unit.x, unit.y), (unit.target.x, unit.target.y))
                > self.game.effective_attack_range(unit)
            ):
                _, archer, threat = screen
                toward_x, toward_y = self._unit_vector(
                    (archer.x, archer.y), (threat.x, threat.y)
                )
                unit.tactical_pos = self._constrain_tactical_position(
                    unit, (archer.x + toward_x * 1.35, archer.y + toward_y * 1.35)
                )
                unit.tactical_timer = self.TACTICAL_RECHECK
                return unit.tactical_pos

        unit.tactical_pos = None
        unit.tactical_timer = self.TACTICAL_RECHECK
        return None

    def update(self, dt):
        self.elapsed += dt
        self.decision_timer += dt
        while self.decision_timer + 1e-9 >= self.decision_interval:
            self.decision_timer -= self.decision_interval
            self.make_decision()

    def make_decision(self):
        self.decision_count += 1
        self.recruitment_timer -= self.decision_interval
        self._record_losses()
        self._update_strategic_knowledge()
        self.evaluate_engaged_combat_groups()
        field_assessment = self._field_combat_assessment()
        threats = self._player_threats()
        threat_score = sum(danger for _, danger in threats)
        self.last_threat_score = threat_score
        self._cleanup_squad()
        self._secure_captured_editor_checkpoint()
        self._position_checkpoint_guards()
        self._position_custom_king_garrison()

        if (
            self.state != AIState.DEFENDING
            and threat_score >= self.DEFENSE_THREAT_THRESHOLD
        ):
            self._cleanup_squad()
            self._enter_defense(threats, threat_score)

        if self.state == AIState.DEFENDING:
            self._cleanup_squad()
            melee_threat = sum(
                danger for unit, danger in threats
                if unit.kind in MELEE_UNIT_KINDS
            )
            has_melee_defender = any(
                unit.uid in self.defenders and unit.kind in MELEE_UNIT_KINDS
                for unit in self._living_red_units()
            )
            if (
                melee_threat >= self.EMERGENCY_MELEE_THREAT
                and not has_melee_defender
                and not self.emergency_recruited
                and self.game.enemy_essence >= UNIT_COSTS["swordsman"]
            ):
                balance_before = self._production_balance()
                if self.game.recruit("swordsman", "red"):
                    recruit = self.game.units[-1]
                    self.reserve.add(recruit.uid)
                    self.defenders.add(recruit.uid)
                    self.emergency_recruited = True
                    self._known_red_uids[recruit.uid] = recruit.kind
                    self.last_production_choice = "swordsman"
                    balance_after = self._production_balance()
                    self.production_history.append({
                        "time": self.elapsed,
                        "state": self.state.name,
                        "kind": "swordsman",
                        "scores": self.production_scores(threat_score).copy(),
                        "emergency": True,
                        "target_shares": balance_before["target_shares"],
                        "spent_essence": balance_after["spent_essence"],
                        "selected_deficit": balance_before["deficits"]["swordsman"],
                    })
                    self.recruitment_timer = self.PRODUCTION_INTERVAL
            self._run_production(threat_score)
            self._assign_defenders(threats, threat_score)
            if threat_score >= self.DEFENSE_THREAT_THRESHOLD:
                self.defense_clear_elapsed = 0.0
            else:
                self.defense_clear_elapsed += self.decision_interval
                if self.defense_clear_elapsed >= self.DEFENSE_CLEAR_COOLDOWN:
                    self._finish_defense()
            return

        self._run_production(threat_score)

        self._cleanup_squad()
        self._reinforce_custom_garrisons_from_unassigned()
        self._assign_checkpoint_reinforcements()
        red_units = self._living_red_units()

        if self.state == AIState.BUILDING and red_units:
            self.transition_to(AIState.RALLYING)
            self.rally_elapsed = 0.0

        if self.state == AIState.RALLYING:
            self.rally_elapsed += self.decision_interval
            self._assign_available_units()
            strength_gate_passed = self._launch_strength_gate()
            rally_limit = (
                self.CHECKPOINT_MAX_RALLY_WAIT
                if self.game.level.has_checkpoints and self.checkpoint_target_uid is not None
                else self.MAX_RALLY_WAIT
            )
            timed_out = self.rally_elapsed >= rally_limit
            if self.last_seen_player_army:
                launch_ready = (
                    strength_gate_passed
                    and (self._formation_ready() or timed_out)
                )
            else:
                launch_ready = strength_gate_passed and (
                    self._formation_ready() or timed_out
                )
            if self.squad and launch_ready:
                self._launch_wave()
        elif self.state == AIState.ATTACKING:
            living_strength = len(self.squad)
            losses = self.wave_start_strength - living_strength
            loss_fraction = losses / max(1, self.wave_start_strength)
            hard_safety_reason = self._attack_hard_safety_reason()
            casualty_retreat = (
                loss_fraction >= self.RECOVERY_LOSS_FRACTION
            )
            casualty_victor = (
                self._victorious_player_composition(self.combat_opponent_uids)
                if losses > 0 else None
            )
            # Decision precedence:
            # 1. Hard safety always ends the attack.
            # 2. A wave within OBJECTIVE_COMMITMENT_RADIUS of the player king
            #    cannot take an elective casualty or strength retreat.
            # 3. Only a fresh advantage above CASUALTY_ADVANTAGE_MARGIN can
            #    override the casualty trigger.
            # 4. A weaker assessment retreats.
            # 5. Uncertain, missing, or stale evidence falls back to retreat
            #    when casualties have already made retreat necessary.
            if hard_safety_reason is not None:
                # A wiped-out wave can resolve a real encounter. Other hard
                # safety exits (such as an unreachable objective) cannot.
                self._begin_recovery(
                    casualty_victor
                    if hard_safety_reason == "no_viable_combat_units"
                    else None
                )
            elif self._checkpoint_within_commitment_radius():
                self._advance_wave()
            elif self._king_within_commitment_radius():
                self._advance_wave()
            elif self._can_finish_objective(field_assessment):
                self._advance_wave()
            elif casualty_retreat:
                if self._casualty_retreat_is_overridden(field_assessment):
                    self._advance_wave()
                else:
                    self._begin_recovery(casualty_victor)
            elif self._strength_decision(field_assessment) == "retreat":
                self._begin_recovery(
                    self._fresh_victorious_player_composition(field_assessment)
                )
            else:
                self._advance_wave()
        elif self.state == AIState.RECOVERING:
            self.recovery_elapsed += self.decision_interval
            if self._strength_decision(field_assessment) == "reengage":
                self.transition_to(AIState.ATTACKING)
                self.recovery_elapsed = 0.0
                self._advance_wave()
            elif self.recovery_elapsed >= self.RECOVERY_DURATION:
                self._finish_recovery()


class SoundtrackController:
    """Crossfade between procedural exploration and battle music."""

    FADE_MS = 700
    PEACEFUL_VOLUME = .38
    FIGHTING_VOLUME = .46
    LOOP_SECONDS = 8
    _sound_cache = {}

    def __init__(self):
        self.mode = None
        self._disabled = False
        self._peaceful_channel = None
        self._fighting_channel = None
        self._peaceful_sound = None
        self._fighting_sound = None

    @classmethod
    def _render_loop(cls, mood, sample_rate, channels):
        """Build a looping 16-bit PCM track without requiring audio assets."""
        frame_count = sample_rate * cls.LOOP_SECONDS
        segment_length = cls.LOOP_SECONDS / 4
        if mood == "peaceful":
            chords = (
                (130.81, 164.81, 196.00),
                (110.00, 130.81, 164.81),
                (87.31, 110.00, 130.81),
                (98.00, 123.47, 146.83),
            )
            melody = (
                392.00, 440.00, 329.63, 293.66,
                261.63, 329.63, 293.66, 246.94,
            )
        else:
            chords = (
                (73.42, 87.31, 110.00),
                (65.41, 77.78, 98.00),
                (73.42, 87.31, 110.00),
                (82.41, 98.00, 123.47),
            )
            melody = (
                293.66, 293.66, 349.23, 329.63,
                293.66, 261.63, 246.94, 261.63,
            )

        pcm = array("h")
        for index in range(frame_count):
            time = index / sample_rate
            segment = min(3, int(time / segment_length))
            chord = chords[segment]
            if mood == "peaceful":
                pad = sum(
                    math.sin(math.tau * frequency * time)
                    for frequency in chord
                ) / len(chord)
                note_index = int(time) % len(melody)
                note_time = time % 1.0
                pluck = (
                    math.sin(math.tau * melody[note_index] * time)
                    * math.exp(-3.2 * note_time)
                )
                wave = (
                    .52 * pad * (1 + .12 * math.sin(math.tau * time / 4))
                    + .24 * pluck
                )
            else:
                root = chord[0]
                drone = (
                    math.sin(math.tau * root * time)
                    + .45 * math.sin(math.tau * root * 2 * time)
                ) / 1.45
                pulse_time = time % .5
                pulse_index = int(time / .5) % len(melody)
                pulse = (
                    math.sin(math.tau * melody[pulse_index] * time)
                    * math.exp(-7 * pulse_time)
                )
                beat_time = time % .5
                drum = (
                    math.sin(math.tau * (82 - 90 * beat_time) * beat_time)
                    * math.exp(-13 * beat_time)
                )
                wave = .50 * drone + .30 * pulse + .28 * drum

            # A short edge fade prevents clicks at the loop boundary.
            edge = min(
                1.0, time / .025, (cls.LOOP_SECONDS - time) / .025
            )
            sample = int(max(-1.0, min(1.0, wave * edge)) * 13500)
            pcm.extend((sample,) * channels)
        return pcm.tobytes()

    def _ensure_audio(self):
        if self._disabled:
            return False
        if self._peaceful_sound is not None:
            return True
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            sample_rate, sample_size, channels = pygame.mixer.get_init()
            if sample_size != -16 or channels not in (1, 2):
                self._disabled = True
                return False
            pygame.mixer.set_num_channels(
                max(2, pygame.mixer.get_num_channels())
            )
            cache_key = (sample_rate, channels)
            sounds = self._sound_cache.get(cache_key)
            if sounds is None:
                sounds = (
                    pygame.mixer.Sound(buffer=self._render_loop(
                        "peaceful", sample_rate, channels
                    )),
                    pygame.mixer.Sound(buffer=self._render_loop(
                        "fighting", sample_rate, channels
                    )),
                )
                self._sound_cache[cache_key] = sounds
            self._peaceful_sound, self._fighting_sound = sounds
            # There are no sound effects yet, so stable music channels keep
            # ownership deterministic when a level or test creates a Game.
            self._peaceful_channel = pygame.mixer.Channel(0)
            self._fighting_channel = pygame.mixer.Channel(1)
            self._peaceful_channel.stop()
            self._fighting_channel.stop()
            return True
        except pygame.error:
            # Audio-less systems should still be able to play the game.
            self._disabled = True
            return False

    def set_mode(self, mode):
        if mode not in (None, "peaceful", "fighting"):
            raise ValueError(f"Invalid soundtrack mode: {mode!r}")
        if mode == self.mode:
            return
        previous = self.mode
        self.mode = mode
        if mode is None and self._peaceful_channel is None:
            return
        if not self._ensure_audio():
            return
        if previous == "peaceful" or mode is None:
            self._peaceful_channel.fadeout(self.FADE_MS)
        if previous == "fighting" or mode is None:
            self._fighting_channel.fadeout(self.FADE_MS)
        if mode == "peaceful":
            self._peaceful_channel.set_volume(self.PEACEFUL_VOLUME)
            self._peaceful_channel.play(
                self._peaceful_sound, loops=-1, fade_ms=self.FADE_MS
            )
        elif mode == "fighting":
            self._fighting_channel.set_volume(self.FIGHTING_VOLUME)
            self._fighting_channel.play(
                self._fighting_sound, loops=-1, fade_ms=self.FADE_MS
            )

    def shutdown(self):
        self.set_mode(None)
        if self._peaceful_channel is not None:
            self._peaceful_channel.stop()
            self._fighting_channel.stop()


class Button:
    def __init__(self, rect, text, sub="", disabled_text=(130, 126, 116), disabled_sub=(110, 105, 97)):
        self.rect = pygame.Rect(rect)
        self.text, self.sub = text, sub
        self.disabled_text = disabled_text
        self.disabled_sub = disabled_sub

    def draw(self, surf, mouse, label_font, cost_font, enabled=True):
        self.enabled = enabled
        hover = self.rect.collidepoint(mouse)
        color = (88, 73, 53) if enabled else (60, 57, 53)
        if hover and enabled:
            color = (112, 91, 60)
        pygame.draw.rect(surf, (29, 27, 24), self.rect.inflate(4, 4), border_radius=9)
        pygame.draw.rect(surf, color, self.rect, border_radius=7)
        pygame.draw.rect(surf, GOLD if hover and enabled else (145, 119, 75), self.rect, 2, border_radius=7)
        text = label_font.render(self.text, True, CREAM if enabled else self.disabled_text)
        if self.sub:
            text_rect = text.get_rect(topleft=(self.rect.x + 12, self.rect.y + 8))
        else:
            text_rect = text.get_rect(center=self.rect.center)
        surf.blit(text, text_rect)
        if self.sub:
            surf.blit(cost_font.render(self.sub, True, (215, 185, 108) if enabled else self.disabled_sub), (self.rect.x + 12, self.rect.y + 34))


class HardModeAI(EnemyAI):
    """Player-style strategic controller used by the optional hard mode.

    Unit-level targeting, kiting, and visibility still come from ``EnemyAI``.
    This class replaces its wave planner with the same recruit, rally,
    reserve, checkpoint, and flanking decisions used by the gameplay
    controller.
    """

    TARGET_SHARES = {
        3: {"swordsman": .20, "archer": .40, "shield": .40},
        4: {"swordsman": .15, "archer": .55, "shield": .30},
        5: {"swordsman": .20, "archer": .40, "shield": .40},
        0: {"swordsman": .20, "archer": .40, "shield": .40},
    }
    RALLY_VALUES = {3: 12000, 4: 10000, 5: 6500, 0: 6500}
    RECRUIT_INTERVAL = .5
    ORDER_INTERVAL = 8.0
    RESERVE_VALUES = {4: 2000, 5: 2500, 0: 2500}

    def __init__(self, game, rng=None, decision_interval=.25):
        super().__init__(game, rng, decision_interval)
        self.next_recruit = 0.0
        self.next_order = 0.0
        self.assault_started = False
        self.assault_uids: set[int] = set()
        self.current_checkpoint_uid = None
        self.march_x = None
        self.flank_index = 0
        self.controller_status = "Rallying the Crimson army"

    def _controller_army(self):
        return [
            unit for unit in self.game.units
            if unit.is_enemy_ai_commandable and unit.health > 0
        ]

    @staticmethod
    def _unit_value(unit):
        return UNIT_COSTS.get(unit.kind, 300)

    def _army_value(self, units=None):
        if units is None:
            units = self._controller_army()
        return sum(self._unit_value(unit) for unit in units)

    def _assault_units(self):
        return [
            unit for unit in self._controller_army()
            if unit.uid in self.assault_uids
        ]

    def _available_kinds(self):
        return tuple(
            kind for kind in UNIT_KINDS
            if kind not in self.unavailable_production_kinds
        )

    def _choose_recruit(self):
        available = self._available_kinds()
        if not available:
            return None
        investment = {kind: 0 for kind in available}
        for unit in self._controller_army():
            if unit.kind in investment:
                investment[unit.kind] += UNIT_COSTS[unit.kind]
        shares = self.TARGET_SHARES.get(
            self.game.level_number, self.TARGET_SHARES[0]
        )

        def projected_error(kind):
            projected = dict(investment)
            projected[kind] += UNIT_COSTS[kind]
            total = sum(projected.values()) or 1
            return sum(
                abs(projected[candidate] / total - shares[candidate])
                for candidate in projected
            )

        preferred = min(
            available, key=lambda kind: (projected_error(kind), kind)
        )
        return (
            preferred
            if self.game.enemy_essence >= UNIT_COSTS[preferred]
            else None
        )

    def _recruit(self):
        while True:
            kind = self._choose_recruit()
            if kind is None or not self.game.recruit(kind, "red"):
                return
            self.last_production_choice = kind

    def _threats_to_king(self):
        king = self.game.team_king("red")
        if king is None:
            return []
        return sorted(
            (
                unit for unit in self.game.units
                if self.game.teams_hostile("red", unit.team)
                and unit.health > 0
                and dist((unit.x, unit.y), (king.x, king.y)) <= 20
            ),
            key=lambda unit: (dist((unit.x, unit.y), (king.x, king.y)), unit.uid),
        )

    def _set_controller_state(self, state):
        if state != self.state:
            self.state = state
            self.state_history.append((self.elapsed, state))

    def _rally_value(self):
        return self.RALLY_VALUES.get(
            self.game.level_number, self.RALLY_VALUES[0]
        )

    def _reset_broken_assault(self):
        if not self.assault_started:
            return
        committed = self._army_value(self._assault_units())
        factor = .5 if self.game.level_number == 4 else .75
        if committed >= self._rally_value() * factor:
            return
        self.assault_started = False
        self.assault_uids.clear()
        self.current_checkpoint_uid = None
        self.march_x = None
        self.flank_index = 0

    def _begin_assault(self):
        if self.assault_started:
            return
        self.assault_started = True
        reserve_value = self.RESERVE_VALUES.get(
            self.game.level_number,
            self.RESERVE_VALUES[0] if self.game.custom_level_active else 0,
        )
        commit_target = max(0, self._army_value() - reserve_value)
        committed_value = 0
        for unit in sorted(self._controller_army(), key=lambda item: item.uid):
            if committed_value >= commit_target:
                break
            self.assault_uids.add(unit.uid)
            committed_value += self._unit_value(unit)

    def _checkpoint_target(self):
        current = self.game.checkpoint_by_uid(self.current_checkpoint_uid)
        if current is not None and current.owner != "red":
            return current
        remaining = [
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.owner != "red"
        ]
        if not remaining:
            self.current_checkpoint_uid = None
            return None
        army = self._assault_units() or self._controller_army()
        king = self.game.team_king("red")
        origin = (
            (
                sum(unit.x for unit in army) / len(army),
                sum(unit.y for unit in army) / len(army),
            )
            if army else (king.x, king.y)
        )
        target = min(
            remaining,
            key=lambda checkpoint: (
                dist(origin, (checkpoint.x, checkpoint.y)), checkpoint.uid
            ),
        )
        self.current_checkpoint_uid = target.uid
        self.checkpoint_target_uid = target.uid
        return target

    def _choose_objective(self):
        self._reset_broken_assault()
        value = self._army_value()
        threats = self._threats_to_king()
        if threats and not self.assault_started:
            self.controller_status = "Defending the Crimson King"
            self._set_controller_state(AIState.DEFENDING)
            return (threats[0].x, threats[0].y)
        if not self.assault_started and value < self._rally_value():
            king = self.game.team_king("red")
            self.controller_status = f"Rallying army — {value:,} gold fielded"
            self._set_controller_state(AIState.RALLYING)
            return (king.x + 2, king.y)

        self._begin_assault()
        self._set_controller_state(AIState.ATTACKING)

        if self.game.level_number == 4 and not self.game.custom_level_active:
            flank = [
                (MAP_SIZE - 45.0, MAP_SIZE * .25),
                (48.0, MAP_SIZE * .25),
            ]
            committed = self._assault_units()
            if committed and self.flank_index < len(flank):
                center = (
                    sum(unit.x for unit in committed) / len(committed),
                    sum(unit.y for unit in committed) / len(committed),
                )
                if dist(center, flank[self.flank_index]) < 8:
                    self.flank_index += 1
            if self.flank_index < len(flank):
                self.controller_status = "Flanking the Verdant host"
                return flank[self.flank_index]

        if self.game.level.has_checkpoints:
            checkpoint = self._checkpoint_target()
            if checkpoint is not None:
                self.controller_status = "Assaulting a strategic hold"
                return checkpoint.x, checkpoint.y

        green_king = self.game.team_king("green")
        if green_king is not None:
            self.controller_status = "Marching on the Verdant King"
            return green_king.x, green_king.y
        return GREEN_KING_POSITION

    def _order_units(self, units, world):
        units = [unit for unit in units if unit.health > 0]
        if not units:
            return
        columns = math.ceil(math.sqrt(len(units)))
        destinations = [
            clamp_to_map((
                world[0] + (index % columns - (columns - 1) / 2) * 1.15,
                world[1] + (index // columns) * 1.15,
            ))
            for index in range(len(units))
        ]
        for unit, destination in zip(
            sorted(units, key=lambda item: item.uid), destinations
        ):
            self.game.clear_navigation(unit)
            unit.target = None
            unit.target_auto_acquired = False
            unit.order_pos = destination
            unit.target_pos = destination

    def _issue_orders(self):
        army = self._controller_army()
        if not army:
            return
        objective = self._choose_objective()
        ordered = self._assault_units() if self.assault_started else army
        self._order_units(ordered, objective)
        if self.assault_started:
            threats = self._threats_to_king()
            if threats:
                reserve = [
                    unit for unit in army if unit.uid not in self.assault_uids
                ]
                self._order_units(reserve, (threats[0].x, threats[0].y))

    def update(self, dt):
        self.elapsed += dt
        self.decision_timer += dt
        while self.elapsed + 1e-9 >= self.next_recruit:
            self._recruit()
            self.next_recruit += self.RECRUIT_INTERVAL
        while self.elapsed + 1e-9 >= self.next_order:
            self._issue_orders()
            self.next_order += self.ORDER_INTERVAL


class Game:
    def __init__(
        self, enemy_rng=None, ai_decision_interval=.25, terrain_seed=None,
        soundtrack=None,
    ):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.big = pygame.font.Font(None, 72)
        self.title = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 25)
        self.small = pygame.font.Font(None, 19)
        self.button_font = pygame.font.Font(None, 25)
        self.button_cost_font = pygame.font.Font(None, 18)
        self.soundtrack = (
            soundtrack if soundtrack is not None else SoundtrackController()
        )
        self.state = "menu"
        # This is deliberately a presentation setting.  Team visibility sets
        # continue to drive targeting, combat, AI knowledge, and exploration.
        self.fog_of_war_enabled = True
        self.play_btn = Button((WIDTH // 2 - 100, HEIGHT // 2 + 85, 200, 62), "Play!")
        self.editor_btn = Button((WIDTH // 2 - 100, HEIGHT // 2 + 151, 200, 44), "Level Editor")
        self.fog_btn = Button((WIDTH // 2 - 100, HEIGHT // 2 + 160, 200, 44), "")
        self.pause_fog_btn = Button((WIDTH // 2 - 120, HEIGHT // 2 + 24, 240, 44), "")
        self.level_buttons = []
        self.selected_level_page = 1
        self.level_nav_buttons = []
        self.level_dot_rects = []
        self.level_location_rects = []
        self.checkpoint_bar_entries = []
        self.level_number = 3
        self.level = LEVELS[self.level_number]
        self.custom_level_active = False
        self.campaign_hard_mode = False
        self.hard_mode = False
        self.difficulty_buttons = []
        self.enemy_rng = enemy_rng
        self.ai_decision_interval = ai_decision_interval
        self.terrain_seed = TERRAIN_SEED if terrain_seed is None else terrain_seed
        self.reset()
        try:
            self.editor_draft = EditorLevelDraft.from_dict(
                json.loads(CUSTOM_LEVEL_FILE.read_text(encoding="utf-8"))
            )
            self.editor_notice = "Saved custom level loaded"
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.editor_draft = make_default_editor_draft()
            self.editor_notice = "Expanded 200 × 200 canvas ready"
        self.editor_tab = "paint"
        self.editor_tool = "path"
        self.editor_brush_size = 3
        self.editor_dragging = False
        self.editor_slider_dragging = None
        self.editor_revision = 0
        self._editor_map_cache_key = None
        self._editor_map_cache = None
        self.editor_buttons = []
        self.editor_sliders = []
        self.editor_canvas = pygame.Rect(0, 0, 0, 0)
        self.editor_map_rect = pygame.Rect(0, 0, 0, 0)
        self.editor_random_hold_count = 3
        self.editor_random_hold_connections = 100
        self.editor_random_path_amount = 25
        self.editor_random_terrain_weights = {
            "plains": 33, "forest": 33, "mountain": 34,
        }

    def reset(self, level_number=None):
        if level_number is not None:
            self.level_number = level_number
            self.custom_level_active = False
            self.hard_mode = bool(
                self.campaign_hard_mode and self.level_number >= 3
            )
        if not self.custom_level_active:
            self.level = LEVELS[self.level_number]
            configure_map(self.level.map_size)
        else:
            self.level = self.editor_draft.to_level_config()
            configure_map(
                self.level.map_size,
                self.editor_draft.green_start,
                self.editor_draft.red_start,
            )
        self.units: list[Unit] = []
        self.unit_spatial_hash = UnitSpatialHash()
        self.essence = self.level.starting_essence
        self.enemy_essence = self.level.enemy_starting_essence
        self.uid = 0
        self.navigation_time = 0.0
        self.terrain_revision = getattr(self, "terrain_revision", 0) + 1
        self.path_calculation_count = 0
        self.path_calculation_lengths: list[int] = []
        self.path_expanded_nodes = 0
        self.path_max_expanded_nodes = 0
        self.path_limit_failures = 0
        green_king = self.add_unit("king", "green", *GREEN_KING_POSITION)
        red_king = self.add_unit("king", "red", *RED_KING_POSITION)
        green_king.home_position = GREEN_KING_POSITION
        red_king.home_position = RED_KING_POSITION
        for king in (green_king, red_king):
            for guard_offset in KING_GUARD_POST_OFFSETS:
                guard_post = clamp_to_map(
                    offset_from((king.x, king.y), guard_offset)
                )
                guard = self.add_unit("knight", king.team, *guard_post)
                guard.home_position = guard_post
        self.camera = list(CAMERA_START)
        self.zoom = 30.0 if self.level_number == 1 else 13.0
        self.clamp_camera()
        self.explored = set()
        self.visible = set()
        self.red_visible = set()
        self._team_visibility_initialized = {"green": False, "red": False}
        self._vision_mask_cache = {}
        self._vision_terrain_signature = None
        self._fog_revision = 0
        self._fog_cache_key = None
        self._fog_cache_surface = None
        self._terrain_tile_cache = {}
        self._terrain_world_cache_key = None
        self._terrain_world_cache_surface = None
        self.drag_start = None
        self.drag_now = None
        self.arrows = []
        self.particles = []
        self.king_slashes: list[SlashEffect] = []
        self.checkpoints: list[Checkpoint] = []
        self.checkpoint_bar_entries = []
        self.message = (
            "Defeat all enemy units"
            if self.level_number == 1
            else (
                "Hard mode — defeat the Crimson King"
                if self.hard_mode else "Defeat the Crimson King"
            )
        )
        self.message_time = 4
        self.winner = None
        self.essence_tick = 0
        self.reveal_tick = 0
        self.terrain = self.make_terrain()
        if self.level.has_checkpoints:
            for checkpoint in self.checkpoints:
                initial_count = (
                    checkpoint.profile.initial_melee
                    + checkpoint.profile.initial_ranged
                )
                for index in range(initial_count):
                    self.spawn_checkpoint_defender(checkpoint, initial_index=index)
        for kind, dx, dy in self.level.player_starting_units:
            self.add_unit(kind, "green", *offset_from(GREEN_KING_POSITION, (dx, dy)))
        for kind, dx, dy in self.level.enemy_starting_units:
            self.add_unit(kind, "red", *offset_from(RED_KING_POSITION, (dx, dy)))
        if self.level_number == 1:
            self.units[:] = [
                unit for unit in self.units
                if not (
                    unit.team == "red"
                    and (unit.is_king_objective or unit.is_autonomous_guard)
                )
            ]
        ai_class = (
            HardModeAI
            if self.hard_mode and self.level.enemy_ai == "full"
            else EnemyAI
        )
        self.enemy_ai = ai_class(
            self, self.enemy_rng, self.ai_decision_interval
        )
        self._movement_snapshot_active = False
        self._path_searches_this_update = 0
        self.rebuild_unit_spatial_hash()

    def start_level(self, level_number, terrain_seed=None):
        """Begin a fresh battlefield, preserving its seed for later retries."""
        self.selected_level_page = level_number
        if terrain_seed is None:
            terrain_seed = random.SystemRandom().getrandbits(64)
        self.terrain_seed = terrain_seed
        self.reset(level_number)

    def start_custom_level(self):
        """Build and play the current editor draft without mutating campaign data."""
        self.custom_level_active = True
        self.level_number = 0
        self.level = self.editor_draft.to_level_config()
        self.hard_mode = self.editor_draft.hard_mode
        self.fog_of_war_enabled = self.editor_draft.fog_of_war
        self.terrain_seed = random.SystemRandom().getrandbits(64)
        self.reset()

    def rebuild_unit_spatial_hash(self):
        """Snapshot all living units for local collision queries."""
        self.unit_spatial_hash.rebuild(self.units)

    def nearby_units(
        self, unit, radius=UNIT_NEIGHBOR_QUERY_RADIUS, position=None
    ):
        position = position or self.unit_spatial_hash.positions.get(
            unit.uid, (unit.x, unit.y)
        )
        return self.unit_spatial_hash.neighbors(
            position, radius, exclude=unit
        )

    @staticmethod
    def _overlap_fallback_direction(unit, other):
        """Return opposite, deterministic directions for an exact-overlap pair."""
        low_uid, high_uid = sorted((unit.uid, other.uid))
        angle = (
            (low_uid * 0.7548776662466927 + high_uid * 0.5698402909980532)
            * math.tau
        ) % math.tau
        direction = (math.cos(angle), math.sin(angle))
        return direction if unit.uid == low_uid else (-direction[0], -direction[1])

    def unit_separation_vector(self, unit, position=None):
        """Calculate soft overlap correction without changing strategic state.

        This local physical response is shared by both teams. It does not
        replace the preferred velocity supplied by an order, tactical slot, or
        combat approach; ``move_unit_toward`` blends the two vectors.
        """
        if not self._movement_snapshot_active:
            self.rebuild_unit_spatial_hash()
        separation_x = separation_y = 0.0
        minimum_distance = UNIT_SEPARATION_RADIUS - UNIT_SOFT_OVERLAP
        unit_x, unit_y = position or self.unit_spatial_hash.positions.get(
            unit.uid, (unit.x, unit.y)
        )
        for other in self.nearby_units(
            unit, UNIT_SEPARATION_RADIUS, (unit_x, unit_y)
        ):
            other_x, other_y = self.unit_spatial_hash.positions.get(
                other.uid, (other.x, other.y)
            )
            dx, dy = unit_x - other_x, unit_y - other_y
            distance = math.hypot(dx, dy)
            penetration = minimum_distance - distance
            if penetration <= 0:
                continue
            if distance <= 1e-9:
                direction_x, direction_y = self._overlap_fallback_direction(
                    unit, other
                )
            else:
                direction_x, direction_y = dx / distance, dy / distance
            separation_x += direction_x * penetration
            separation_y += direction_y * penetration
        if not (
            math.isfinite(separation_x) and math.isfinite(separation_y)
        ):
            return 0.0, 0.0
        return separation_x, separation_y

    def team_king(self, team):
        """Return the team's live strategic objective, if it still exists."""
        return next(
            (
                unit for unit in self.units
                if unit.team == team
                and unit.is_king_objective
                and unit.health > 0
            ),
            None,
        )

    def objective_for(self, attacking_team):
        """Return the live opposing king that a team must destroy."""
        return self.team_king("red" if attacking_team == "green" else "green")

    def objective_position(self, team):
        king = self.team_king(team)
        return (king.x, king.y) if king is not None else None

    def objective_health(self, team):
        king = self.team_king(team)
        return max(0, king.health) if king is not None else 0

    def make_terrain(self):
        if self.custom_level_active:
            terrain = dict(self.editor_draft.terrain)
            self._terrain_region_count = 0
            path_cells = tuple(sorted(
                (
                    position for position, cell in terrain.items()
                    if cell.kind == "path"
                ),
                key=lambda position: (position[0], position[1]),
            ))
            self._terrain_road_routes = (path_cells,) if path_cells else ()
            quiet_zones = (
                (*self.editor_draft.green_start, 6.0),
                (*self.editor_draft.red_start, 6.0),
            )
            self._terrain_protected_cells = {
                (x, y)
                for x in range(MAP_SIZE) for y in range(MAP_SIZE)
                if any(
                    (x + .5 - qx) ** 2 + (y + .5 - qy) ** 2 < radius ** 2
                    for qx, qy, radius in quiet_zones
                )
            }
            self.checkpoints = []
            for uid, hold in enumerate(self.editor_draft.holds, 1):
                cell_kind = terrain[(hold.x, hold.y)].kind
                terrain_kind = cell_kind if cell_kind != "path" else "plains"
                faction = CHECKPOINT_FACTION_BY_TERRAIN[terrain_kind]
                self.checkpoints.append(Checkpoint(
                    uid, hold.x + .5, hold.y + .5,
                    terrain_kind, faction, faction, EDITOR_CHECKPOINT_PROFILE,
                ))
            return terrain
        rng = random.Random(
            f"verdant-crown:{self.terrain_seed}:{self.level_number}:{MAP_SIZE}"
        )
        terrain = {}
        self._terrain_road_routes = ()
        # Weighted nearest-region assignment preserves large, readable terrain
        # masses while allowing each seed to vary their proportions and size.
        # Level one deliberately stays all plains so its opening remains simple.
        base_region_count = max(20, round(MAP_SIZE / 3))
        region_count = max(12, round(base_region_count * rng.uniform(.75, 1.25)))
        self._terrain_region_count = 0 if self.level_number == 1 else region_count
        biome_kinds = ("plains", "forest", "mountain")
        complete_sets, remainder = divmod(region_count, len(biome_kinds))
        region_kinds = list(biome_kinds) * complete_sets
        region_kinds.extend(rng.sample(biome_kinds, remainder))
        rng.shuffle(region_kinds)

        regions = [
            (
                rng.uniform(0, MAP_SIZE),
                rng.uniform(0, MAP_SIZE),
                region_kinds[index],
                rng.uniform(.72, 1.35),
            )
            for index in range(region_count)
        ]
        quiet_zones = (
            (self.team_king("green").x, self.team_king("green").y, 6.0),
            (*offset_from(GREEN_KING_POSITION, (5.5, .5)), 4.75),
            (self.team_king("red").x, self.team_king("red").y, 6.0),
            (*offset_from(RED_KING_POSITION, (-5.5, .5)), 4.75),
        )
        self._terrain_protected_cells = {
            (x, y)
            for x in range(MAP_SIZE)
            for y in range(MAP_SIZE)
            if any(
                (x + .5 - qx) ** 2 + (y + .5 - qy) ** 2 < radius ** 2
                for qx, qy, radius in quiet_zones
            )
        }
        for x in range(MAP_SIZE):
            for y in range(MAP_SIZE):
                variation = rng.randrange(4)
                kind = "plains" if self.level_number == 1 else min(
                    regions,
                    key=lambda region: (
                        (x + .5 - region[0]) ** 2
                        + (y + .5 - region[1]) ** 2
                    ) / region[3] ** 2,
                )[2]
                terrain[(x, y)] = TerrainCell(kind, variation)
        if self.level_number != 1:
            self._terrain_road_routes = self._make_road_routes(rng)
            for route in self._terrain_road_routes:
                for x, y in route:
                    for path_y in (y, min(y + 1, MAP_SIZE - 1)):
                        variation = terrain[(x, path_y)].variation
                        terrain[(x, path_y)] = TerrainCell("path", variation)
        # Reapply protected plains last so paths never expose kings, guards, or
        # fresh recruits to the path terrain's increased incoming damage.
        for (x, y), cell in terrain.items():
            if (x, y) in self._terrain_protected_cells:
                terrain[(x, y)] = TerrainCell("plains", cell.variation)
        if self.level.has_checkpoints:
            self.checkpoints = self._make_checkpoints(rng, terrain)
            road_routes = list(self._terrain_road_routes)
            checkpoint_cells = {checkpoint.cell for checkpoint in self.checkpoints}
            for checkpoint in self.checkpoints:
                spur = self._make_checkpoint_road_spur(checkpoint, terrain)
                road_routes.append(tuple(spur))
                for x, y in spur:
                    if (x, y) in checkpoint_cells:
                        continue
                    variation = terrain[(x, y)].variation
                    terrain[(x, y)] = TerrainCell("path", variation)
            self._terrain_road_routes = tuple(road_routes)
        return terrain

    def _make_checkpoints(self, rng, terrain):
        """Place biome holds and Level 5's deterministic large edge holds."""
        checkpoints = []
        occupied = []
        road_cells = {
            cell for route in self._terrain_road_routes for cell in route
        }
        for uid, terrain_kind in enumerate(("mountain", "forest", "plains"), 1):
            candidates = []
            for (x, y), cell in terrain.items():
                position = (x + .5, y + .5)
                if (
                    cell.kind != terrain_kind
                    or (x, y) in road_cells
                    or (x, y) in self._terrain_protected_cells
                    or x < 12 or y < 8 or x >= MAP_SIZE - 12 or y >= MAP_SIZE - 8
                    or dist(position, GREEN_KING_POSITION) < 24
                    or dist(position, RED_KING_POSITION) < 24
                    or any(dist(position, previous) < 28 for previous in occupied)
                ):
                    continue
                same_biome = sum(
                    terrain.get((x + dx, y + dy), TerrainCell("path", 0)).kind
                    == terrain_kind
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                )
                if same_biome < 7:
                    continue
                nearest_road = min(
                    (abs(x - rx) + abs(y - ry) for rx, ry in road_cells),
                    default=MAP_SIZE,
                )
                if 4 <= nearest_road <= 28:
                    candidates.append((nearest_road, rng.random(), x, y))
            if not candidates:
                # Region generation guarantees every biome; retain strict
                # terrain/path separation if an unusually fragmented seed has
                # no roomy candidate.
                candidates = [
                    (0, rng.random(), x, y)
                    for (x, y), cell in terrain.items()
                    if cell.kind == terrain_kind
                    and (x, y) not in road_cells
                    and (x, y) not in self._terrain_protected_cells
                    and 3 <= x < MAP_SIZE - 3 and 3 <= y < MAP_SIZE - 3
                    and all(dist((x + .5, y + .5), p) >= 20 for p in occupied)
                ]
            _, _, x, y = min(candidates, key=lambda entry: (entry[0], entry[1]))
            faction = CHECKPOINT_FACTION_BY_TERRAIN[terrain_kind]
            profile = (
                LEVEL_FIVE_STANDARD_CHECKPOINT_PROFILE
                if self.level_number == 5
                else STANDARD_CHECKPOINT_PROFILE
            )
            checkpoint = Checkpoint(
                uid, x + .5, y + .5, terrain_kind, faction, faction, profile
            )
            checkpoints.append(checkpoint)
            occupied.append((checkpoint.x, checkpoint.y))
        if self.level_number == 5:
            factions = rng.sample(("demon", "frost_giant"), 2)
            edge_depth = round(MAP_SIZE * .20)
            edge_margin = math.ceil(LARGE_CHECKPOINT_PROFILE.defender_leash)
            edge_bands = (
                range(edge_margin, edge_depth),
                range(MAP_SIZE - edge_depth, MAP_SIZE - edge_margin),
            )
            for faction, y_band in zip(factions, edge_bands):
                candidates = []
                for y in y_band:
                    for x in range(12, MAP_SIZE - 12):
                        cell = terrain[(x, y)]
                        position = (x + .5, y + .5)
                        if (
                            cell.kind == "path"
                            or (x, y) in road_cells
                            or (x, y) in self._terrain_protected_cells
                            or dist(position, GREEN_KING_POSITION) < 24
                            or dist(position, RED_KING_POSITION) < 24
                            or any(dist(position, previous) < 24 for previous in occupied)
                        ):
                            continue
                        nearest_road = min(
                            (abs(x - rx) + abs(y - ry) for rx, ry in road_cells),
                            default=MAP_SIZE,
                        )
                        candidates.append((nearest_road, rng.random(), x, y))
                if not candidates:
                    raise RuntimeError(
                        f"Unable to place Level 5 {faction} edge hold"
                    )
                _, _, x, y = min(candidates, key=lambda entry: (entry[0], entry[1]))
                checkpoint = Checkpoint(
                    len(checkpoints) + 1,
                    x + .5,
                    y + .5,
                    terrain[(x, y)].kind,
                    faction,
                    faction,
                    LARGE_CHECKPOINT_PROFILE,
                    spawn_timer=LARGE_CHECKPOINT_PROFILE.spawn_seconds,
                )
                checkpoints.append(checkpoint)
                occupied.append((checkpoint.x, checkpoint.y))
        return checkpoints

    def _make_checkpoint_road_spur(self, checkpoint, terrain):
        """Connect the nearest road to a cell beside a checkpoint."""
        road_cells = {
            cell for route in self._terrain_road_routes for cell in route
        }
        cx, cy = checkpoint.cell
        adjacent = [
            (cx + dx, cy + dy)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if 0 <= cx + dx < MAP_SIZE and 0 <= cy + dy < MAP_SIZE
        ]
        end, start = min(
            ((end, start) for end in adjacent for start in road_cells),
            key=lambda pair: (
                abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]),
                pair[0], pair[1],
            ),
        )
        x, y = start
        route = [(x, y)]
        while (x, y) != end:
            if x != end[0]:
                x += 1 if end[0] > x else -1
            elif y != end[1]:
                y += 1 if end[1] > y else -1
            route.append((x, y))
        return route

    def _make_road_routes(self, rng):
        """Return a connected main road and one or two split/rejoin branches."""
        clearance = RECRUIT_FORWARD_OFFSET + 8.0
        start_x = round(GREEN_KING_POSITION[0] + clearance)
        end_x = round(RED_KING_POSITION[0] - clearance)
        span = max(1, end_x - start_x)
        amplitude = min(12.0, MAP_SIZE * .18)
        main_anchors = [(start_x, MAP_CENTER)]
        anchor_fractions = (.25, .5, .75)
        section_width = span / 4
        maximum_section_bend = min(amplitude, section_width * .65)
        previous_y = MAP_CENTER
        for index, fraction in enumerate(anchor_fractions):
            remaining_sections = 4 - (index + 1)
            reachable_offset = remaining_sections * maximum_section_bend
            candidate_y = previous_y + rng.uniform(
                -maximum_section_bend, maximum_section_bend
            )
            anchor_y = clamp(
                candidate_y,
                max(3, MAP_CENTER - reachable_offset),
                min(MAP_SIZE - 4, MAP_CENTER + reachable_offset),
            )
            main_anchors.append((
                round(start_x + span * fraction),
                anchor_y,
            ))
            previous_y = anchor_y
        main_anchors.append((end_x, MAP_CENTER))
        main_route = self._smooth_road_route(main_anchors)
        main_y = {x: y for x, y in main_route}

        branch_count = rng.randint(1, 2)
        branch_ranges = (
            ((.15, .55), (.45, .85)) if branch_count == 2
            else ((.28, .72),)
        )
        routes = [main_route]
        for range_start, range_end in branch_ranges:
            branch_start_x = round(start_x + span * range_start)
            branch_end_x = round(start_x + span * range_end)
            branch_start_y = main_y[branch_start_x]
            branch_end_y = main_y[branch_end_x]
            midpoint_x = round((branch_start_x + branch_end_x) / 2)
            branch_baseline_y = (branch_start_y + branch_end_y) / 2
            branch_amplitude = min(
                15.0,
                MAP_SIZE * .14,
                max(4.0, (midpoint_x - branch_start_x) * .75),
            )
            minimum_offset = branch_amplitude * .85
            available_room = {
                -1: branch_baseline_y - 3,
                1: MAP_SIZE - 4 - branch_baseline_y,
            }
            directions = [
                direction for direction, room in available_room.items()
                if room >= minimum_offset
            ]
            direction = rng.choice(directions)
            maximum_offset = min(branch_amplitude, available_room[direction])
            offset = direction * rng.uniform(minimum_offset, maximum_offset)
            midpoint_y = branch_baseline_y + offset
            branch_anchors = [
                (branch_start_x, branch_start_y),
                (midpoint_x, midpoint_y),
                (branch_end_x, branch_end_y),
            ]
            routes.append(self._smooth_road_route(branch_anchors))
        return tuple(tuple(route) for route in routes)

    @staticmethod
    def _smooth_road_route(anchors):
        """Interpolate ordered anchors with smooth bends, one center cell per x."""
        route = []
        for index, ((x0, y0), (x1, y1)) in enumerate(zip(anchors, anchors[1:])):
            width = max(1, x1 - x0)
            first_x = x0 if index == 0 else x0 + 1
            for x in range(first_x, x1 + 1):
                progress = (x - x0) / width
                eased = progress * progress * (3.0 - 2.0 * progress)
                y = round(y0 + (y1 - y0) * eased)
                route.append((x, int(clamp(y, 0, MAP_SIZE - 1))))
        return route

    def add_unit(self, kind, team, x, y):
        if kind not in ALL_UNIT_KINDS:
            raise ValueError(f"Invalid unit kind: {kind!r}")
        self.uid += 1
        unit = Unit(kind, team, x, y, uid=self.uid)
        self.units.append(unit)
        return unit

    @staticmethod
    def teams_hostile(first, second):
        if first == second:
            return False
        if first in NATIVE_FACTIONS and second in NATIVE_FACTIONS:
            return True
        if first in NATIVE_FACTIONS or second in NATIVE_FACTIONS:
            return bool({first, second} & {"green", "red"})
        return {first, second} == {"green", "red"}

    def spawn_checkpoint_defender(self, checkpoint, initial_index=None):
        living = [
            unit for unit in self.units
            if unit.uid in checkpoint.defender_uids and unit.health > 0
        ]
        if (
            checkpoint.owner != checkpoint.native_faction
            or len(living) >= checkpoint.profile.max_defenders
        ):
            return None
        melee, ranged = CHECKPOINT_UNITS[checkpoint.native_faction]
        if initial_index is not None:
            kind = (
                melee
                if initial_index < checkpoint.profile.initial_melee
                else ranged
            )
        else:
            initial_count = (
                checkpoint.profile.initial_melee
                + checkpoint.profile.initial_ranged
            )
            kind = (
                ranged
                if (checkpoint.spawn_count - initial_count) % 2 == 0
                else melee
            )
        slot = checkpoint.spawn_count
        angle = (slot * 2.399963229728653) % math.tau
        radius = (
            2.0 + (slot % 3) * .65
            if not checkpoint.profile.opposite_large_target
            else 3.0 + math.sqrt(slot) * .8
        )
        position = clamp_to_map((
            checkpoint.x + math.cos(angle) * radius,
            checkpoint.y + math.sin(angle) * radius,
        ))
        unit = self.add_unit(kind, checkpoint.native_faction, *position)
        unit.home_position = position
        unit.checkpoint_uid = checkpoint.uid
        checkpoint.defender_uids.add(unit.uid)
        checkpoint.spawn_count += 1
        return unit

    def spawn_captured_checkpoint_unit(self, checkpoint):
        """Raise one native-faction troop for a Verdant or Crimson owner."""
        if checkpoint.owner not in ("green", "red"):
            return None
        team_units = checkpoint.captured_unit_uids[checkpoint.owner]
        living_uids = {
            unit.uid for unit in self.units
            if unit.uid in team_units and unit.health > 0
        }
        team_units.intersection_update(living_uids)
        if len(team_units) >= CAPTURED_CHECKPOINT_MAX_UNITS:
            return None

        melee, ranged = CHECKPOINT_UNITS[checkpoint.native_faction]
        kind = ranged if checkpoint.captured_spawn_count % 2 == 0 else melee
        slot = checkpoint.captured_spawn_count
        angle = (slot * 2.399963229728653) % math.tau
        radius = 2.0 + (slot % 3) * .65
        position = clamp_to_map((
            checkpoint.x + math.cos(angle) * radius,
            checkpoint.y + math.sin(angle) * radius,
        ))
        unit = self.add_unit(kind, checkpoint.owner, *position)
        unit.home_position = position
        unit.checkpoint_uid = checkpoint.uid
        team_units.add(unit.uid)
        checkpoint.captured_spawn_count += 1
        return unit

    def native_raid_objective(self, checkpoint):
        """Choose the nearest other native hold or living king."""
        origin = (checkpoint.x, checkpoint.y)
        candidates = []
        if checkpoint.profile.opposite_large_target:
            opposite = next((
                other for other in self.checkpoints
                if other is not checkpoint
                and other.profile.opposite_large_target
                and other.owner == other.native_faction
                and other.owner != checkpoint.owner
            ), None)
            if opposite is not None:
                return (
                    dist(origin, (opposite.x, opposite.y)),
                    0,
                    opposite.uid,
                    "checkpoint",
                    opposite,
                )
        else:
            candidates = [
            (
                dist(origin, (other.x, other.y)),
                0,
                other.uid,
                "checkpoint",
                other,
            )
            for other in self.checkpoints
            if (
                other is not checkpoint
                and other.owner == other.native_faction
                and other.owner != checkpoint.owner
            )
            ]
        for team_index, team in enumerate(("green", "red")):
            king = self.team_king(team)
            if king is not None:
                candidates.append((
                    dist(origin, (king.x, king.y)),
                    1,
                    team_index,
                    "king",
                    king,
                ))
        return min(candidates, default=None)

    def launch_native_raid(self, checkpoint):
        """Detach a profile-sized force at its threshold and choose an objective."""
        if checkpoint.owner != checkpoint.native_faction:
            return []
        active_raid = any(
            unit.health > 0
            and unit.team == checkpoint.owner
            and unit.checkpoint_uid == checkpoint.uid
            and (
                unit.raid_target_checkpoint_uid is not None
                or unit.raid_target_king_team is not None
            )
            for unit in self.units
        )
        if active_raid:
            return []
        living = sorted(
            (
                unit for unit in self.units
                if unit.uid in checkpoint.defender_uids and unit.health > 0
            ),
            key=lambda unit: unit.uid,
        )
        if len(living) < checkpoint.profile.raid_threshold:
            return []
        objective = self.native_raid_objective(checkpoint)
        if objective is None:
            return []
        _, _, _, objective_kind, target = objective
        raiders = living[:checkpoint.profile.raid_size]
        for unit in raiders:
            checkpoint.defender_uids.discard(unit.uid)
            unit.home_position = None
            if objective_kind == "checkpoint":
                unit.raid_target_checkpoint_uid = target.uid
                unit.raid_target_king_team = None
                unit.target_pos = (target.x, target.y)
            else:
                unit.raid_target_checkpoint_uid = None
                unit.raid_target_king_team = target.team
                unit.target_pos = (target.x, target.y)
            self.clear_navigation(unit)
        return raiders

    def garrison_native_raiders(self, checkpoint, faction):
        """Turn a successful native raid into the captured hold's garrison."""
        raiders = [
            unit for unit in self.units
            if unit.health > 0
            and unit.team == faction
            and unit.raid_target_checkpoint_uid == checkpoint.uid
            and dist((unit.x, unit.y), (checkpoint.x, checkpoint.y))
            <= checkpoint.profile.capture_radius
        ]
        for unit in raiders:
            source = self.checkpoint_by_uid(unit.checkpoint_uid)
            if source is not None:
                source.defender_uids.discard(unit.uid)
            unit.checkpoint_uid = checkpoint.uid
            unit.raid_target_checkpoint_uid = None
            unit.raid_target_king_team = None
            unit.home_position = (unit.x, unit.y)
            unit.target = None
            unit.target_pos = None
            checkpoint.defender_uids.add(unit.uid)
            self.clear_navigation(unit)
        return raiders

    def checkpoint_by_uid(self, uid):
        return next((checkpoint for checkpoint in self.checkpoints if checkpoint.uid == uid), None)

    def checkpoint_income(self, team):
        return sum(
            checkpoint.profile.income
            for checkpoint in self.checkpoints
            if checkpoint.owner == team and checkpoint.income_active
        )

    def income_rate(self, team):
        base = self.level.player_income if team == "green" else self.level.enemy_income
        return base + self.checkpoint_income(team)

    def update_checkpoints(self, dt):
        for checkpoint in self.checkpoints:
            previous_under_attack = checkpoint.under_attack
            previous_capturing_team = checkpoint.capturing_team
            ownership_changed = False
            checkpoint.defender_uids = {
                uid for uid in checkpoint.defender_uids
                if any(unit.uid == uid and unit.health > 0 for unit in self.units)
            }
            for team, unit_uids in checkpoint.captured_unit_uids.items():
                checkpoint.captured_unit_uids[team] = {
                    uid for uid in unit_uids
                    if any(
                        unit.uid == uid and unit.team == team and unit.health > 0
                        for unit in self.units
                    )
                }
            if checkpoint.owner in NATIVE_FACTIONS:
                # A second friendly raid may still be en route when the first
                # one completes the capture. Fold it into the new garrison
                # instead of leaving its source permanently marked as raiding.
                self.garrison_native_raiders(checkpoint, checkpoint.owner)
            self.launch_native_raid(checkpoint)
            if (
                checkpoint.owner == checkpoint.native_faction
                and not checkpoint.ever_captured
            ):
                checkpoint.spawn_timer -= max(0.0, dt)
                while checkpoint.spawn_timer <= 0:
                    self.spawn_checkpoint_defender(checkpoint)
                    self.launch_native_raid(checkpoint)
                    checkpoint.spawn_timer += checkpoint.profile.spawn_seconds
            elif checkpoint.owner in ("green", "red"):
                checkpoint.captured_spawn_timer -= max(0.0, dt)
                while checkpoint.captured_spawn_timer <= 1e-9:
                    self.spawn_captured_checkpoint_unit(checkpoint)
                    checkpoint.captured_spawn_timer += (
                        CAPTURED_CHECKPOINT_SPAWN_SECONDS
                    )
            present = {
                team for team in ("green", "red", *NATIVE_FACTIONS)
                if any(
                    unit.team == team
                    and (
                        unit.is_purchasable_army_unit
                        or (
                            unit.is_native_defender
                            and unit.raid_target_checkpoint_uid == checkpoint.uid
                        )
                    )
                    and unit.health > 0
                    and dist((unit.x, unit.y), (checkpoint.x, checkpoint.y))
                    <= checkpoint.profile.capture_radius
                    for unit in self.units
                )
            }
            hostile_teams = {
                team for team in present
                if self.teams_hostile(checkpoint.owner, team)
            }
            checkpoint.under_attack = bool(hostile_teams)
            checkpoint.contested = len(present) > 1
            if checkpoint.owner in NATIVE_FACTIONS and checkpoint.defender_uids:
                checkpoint.capturing_team = None
                checkpoint.capture_progress = 0.0
            else:
                attackers = present - {checkpoint.owner}
                if len(present) == 1 and len(attackers) == 1:
                    capturing_team = next(iter(attackers))
                    if checkpoint.capturing_team != capturing_team:
                        checkpoint.capturing_team = capturing_team
                        checkpoint.capture_progress = 0.0
                    checkpoint.capture_progress += max(0.0, dt)
                    if (
                        checkpoint.capture_progress + 1e-9
                        >= CHECKPOINT_CAPTURE_SECONDS
                    ):
                        previous_owner = checkpoint.owner
                        checkpoint.owner = capturing_team
                        ownership_changed = True
                        checkpoint.ever_captured = capturing_team in ("green", "red")
                        if capturing_team in NATIVE_FACTIONS:
                            checkpoint.native_faction = capturing_team
                            checkpoint.spawn_timer = checkpoint.profile.spawn_seconds
                            self.garrison_native_raiders(
                                checkpoint, capturing_team
                            )
                        else:
                            checkpoint.captured_spawn_timer = (
                                CAPTURED_CHECKPOINT_SPAWN_SECONDS
                            )
                        checkpoint.capturing_team = None
                        checkpoint.capture_progress = 0.0
                        checkpoint.under_attack = False
                        checkpoint.contested = False
                        if capturing_team == "green":
                            self.message = (
                                f"{checkpoint.native_faction.replace('_', ' ').title()} hold captured"
                                " — income and healing active"
                            )
                        elif capturing_team == "red" and previous_owner == "green":
                            self.message = (
                                f"{checkpoint.native_faction.replace('_', ' ').title()} hold lost"
                            )
                        elif capturing_team in NATIVE_FACTIONS:
                            faction = capturing_team.replace("_", " ").title()
                            self.message = f"{faction} raid captured the hold"
                        else:
                            self.message = (
                                f"Crimson army captured the "
                                f"{checkpoint.native_faction.replace('_', ' ').title()} hold"
                            )
                        self.message_time = 3.0
                else:
                    checkpoint.capturing_team = None
                    checkpoint.capture_progress = 0.0
            if (
                checkpoint.owner in ("green", "red")
                and checkpoint.income_active
            ):
                for unit in self.units:
                    if (
                        unit.team == checkpoint.owner
                        and unit.is_purchasable_army_unit
                        and unit.health > 0
                        and unit.health < unit.max_health
                        and dist((unit.x, unit.y), (checkpoint.x, checkpoint.y))
                        <= checkpoint.profile.heal_radius
                    ):
                        unit.health = min(
                            unit.max_health,
                            unit.health + CHECKPOINT_HEAL_RATE * max(0.0, dt),
                        )
            if (
                not ownership_changed
                and
                checkpoint.owner in ("green", "red")
                and checkpoint.under_attack != previous_under_attack
            ):
                if checkpoint.under_attack:
                    self.message = (
                        f"{checkpoint.native_faction.replace('_', ' ').title()} hold contested"
                        " — income and healing suppressed"
                    )
                else:
                    self.message = (
                        f"{checkpoint.native_faction.replace('_', ' ').title()} hold secure"
                        " — income and healing restored"
                    )
                self.message_time = 2.8
            elif (
                checkpoint.capturing_team is not None
                and checkpoint.capturing_team != previous_capturing_team
            ):
                faction = {
                    "green": "Verdant",
                    "red": "Crimson",
                    **{
                        native: native.replace("_", " ").title()
                        for native in NATIVE_FACTIONS
                    },
                }[checkpoint.capturing_team]
                force = (
                    "raid"
                    if checkpoint.capturing_team in NATIVE_FACTIONS
                    else "army"
                )
                self.message = (
                    f"{faction} {force} capturing the "
                    f"{checkpoint.native_faction.replace('_', ' ').title()} hold"
                )
                self.message_time = 2.5

    def native_defender_target(self, unit):
        checkpoint = self.checkpoint_by_uid(unit.checkpoint_uid)
        if checkpoint is None:
            return None
        if unit.raid_target_checkpoint_uid is not None or unit.raid_target_king_team:
            candidates = [
                other for other in self.units
                if (
                    other.health > 0
                    and self.teams_hostile(unit.team, other.team)
                    and dist((other.x, other.y), (unit.x, unit.y))
                    <= UNIT_VISION_RADIUS
                )
            ]
            return min(
                candidates,
                key=lambda other: (
                    dist((unit.x, unit.y), (other.x, other.y)), other.uid
                ),
                default=None,
            )
        candidates = [
            other for other in self.units
            if other.health > 0 and self.teams_hostile(unit.team, other.team)
            and dist((other.x, other.y), (checkpoint.x, checkpoint.y))
            <= checkpoint.profile.defender_leash
        ]
        return min(
            candidates,
            key=lambda other: (dist((unit.x, unit.y), (other.x, other.y)), other.uid),
            default=None,
        )

    def native_raid_destination(self, unit):
        if unit.raid_target_checkpoint_uid is not None:
            checkpoint = self.checkpoint_by_uid(unit.raid_target_checkpoint_uid)
            if checkpoint is not None:
                return checkpoint.x, checkpoint.y
        if unit.raid_target_king_team:
            king = self.team_king(unit.raid_target_king_team)
            if king is not None:
                return king.x, king.y
        return None

    def world_to_screen(self, x, y):
        w, h = self.screen.get_size()
        return (w / 2 + (x - self.camera[0]) * self.zoom,
                (h - HUD_H) / 2 + (y - self.camera[1]) * self.zoom)

    def screen_to_world(self, pos):
        w, h = self.screen.get_size()
        return (self.camera[0] + (pos[0] - w / 2) / self.zoom,
                self.camera[1] + (pos[1] - (h - HUD_H) / 2) / self.zoom)

    def clamp_camera(self):
        """Keep the viewport on the battlefield at every supported zoom."""
        w, h = self.screen.get_size()
        half_w = w / (2 * self.zoom)
        half_h = (h - HUD_H) / (2 * self.zoom)
        self.camera[0] = (
            MAP_CENTER if half_w >= MAP_CENTER
            else clamp(self.camera[0], half_w, MAP_SIZE - half_w)
        )
        self.camera[1] = (
            MAP_CENTER if half_h >= MAP_CENTER
            else clamp(self.camera[1], half_h, MAP_SIZE - half_h)
        )

    def recruit(self, kind, team="green"):
        if kind in ALL_UNIT_KINDS and kind not in PURCHASABLE_UNIT_KINDS:
            return False
        if kind not in ALL_UNIT_KINDS:
            raise ValueError(f"Invalid unit kind: {kind!r}")
        if team == "green" and kind not in self.level.player_units:
            return False
        if team == "red" and self.level.enemy_ai == "none":
            return False
        cost = UNIT_COSTS[kind]
        wallet = self.essence if team == "green" else self.enemy_essence
        if wallet < cost:
            if team == "green":
                self.message, self.message_time = "Not enough gold", 1.5
            return False
        if team == "green":
            self.essence -= cost
            spawn_king, direction = self.team_king("green"), 1
        else:
            self.enemy_essence -= cost
            spawn_king, direction = self.team_king("red"), -1
        count = sum(
            u.team == team and u.is_purchasable_army_unit
            for u in self.units
        )
        y = (
            spawn_king.y + RECRUIT_FIRST_LATERAL_OFFSET
            + (count % RECRUIT_SLOTS_PER_COLUMN) * RECRUIT_LATERAL_SPACING
        )
        recruit = self.add_unit(
            kind,
            team,
            *clamp_to_map((spawn_king.x + direction * RECRUIT_FORWARD_OFFSET, y)),
        )
        if team == "green":
            # A fresh recruit immediately joins a nearby visible fight instead
            # of waiting at the keep for its first explicit player order.
            self.update_visibility()
            nearby_enemies = [
                unit for unit in self.units
                if (
                    self.teams_hostile(unit.team, team)
                    and unit.health > 0
                    and self.currently_visible_enemy(unit)
                    and dist((recruit.x, recruit.y), (unit.x, unit.y))
                    <= PLAYER_RECRUIT_ENGAGE_RADIUS
                )
            ]
            target = min(
                nearby_enemies,
                key=lambda unit: (
                    dist((recruit.x, recruit.y), (unit.x, unit.y)),
                    unit.uid,
                ),
                default=None,
            )
            if target is not None:
                recruit.target = target
                recruit.target_pos = (target.x, target.y)
        return True

    def select_kind(self, kind=None):
        for u in self.units:
            u.selected = (
                u.is_player_commandable
                and (kind is None or u.kind == kind)
            )

    def issue_order(self, world):
        selected = [u for u in self.units if u.selected and u.is_player_commandable]
        if not selected:
            return
        visible_enemies = [
            u for u in self.units
            if (
                self.teams_hostile("green", u.team)
                and u.health > 0
                and self.is_visible(u.x, u.y)
            )
        ]
        candidates = visible_enemies
        clicked = min(candidates, key=lambda e: dist((e.x, e.y), world), default=None)
        cols = math.ceil(math.sqrt(len(selected)))
        formation_destinations = [
            clamp_to_map((
                world[0] + (i % cols - (cols - 1) / 2) * 1.15,
                world[1] + (i // cols) * 1.15,
            ))
            for i in range(len(selected))
        ]
        if clicked and dist((clicked.x, clicked.y), world) < 1.5:
            for u, formation_destination in zip(
                selected, formation_destinations
            ):
                self.clear_navigation(u)
                u.target, u.target_pos = clicked, (clicked.x, clicked.y)
                # A target can die or disappear while a large group is still
                # crossing the map. Retain the clicked formation as the
                # strategic destination so that losing the target resumes the
                # order instead of stopping and leaving the group scattered.
                u.order_pos = formation_destination
                u.target_auto_acquired = False
            return
        for u, formation_destination in zip(selected, formation_destinations):
            self.clear_navigation(u)
            u.target = None
            u.target_auto_acquired = False
            u.order_pos = formation_destination
            u.target_pos = u.order_pos

    @staticmethod
    def clear_navigation(unit):
        """Invalidate cached path state while preserving the strategic order."""
        unit.nav_destination = None
        unit.nav_waypoints.clear()
        unit.nav_waypoint_index = 0
        unit.nav_blocked_time = 0.0
        unit.nav_last_path_time = -math.inf
        unit.nav_destination_key = None
        unit.nav_last_progress_position = None
        unit.nav_clear_time = 0.0
        unit.nav_terrain_revision = -1
        unit.nav_terrain_route = False
        unit.nav_direct_check_timer = 0.0

    def release_combat_target(self, unit):
        """Drop a combat target and resume a surviving player ground order."""
        unit.target = None
        unit.target_auto_acquired = False
        if unit.is_player_commandable and unit.order_pos is not None:
            unit.target_pos = unit.order_pos
        self.clear_navigation(unit)

    def currently_visible_enemy(self, enemy):
        return self.is_visible(enemy.x, enemy.y)

    def has_visible_enemy(self):
        """Return whether a living hostile unit is in the player's true vision."""
        return any(
            unit.health > 0
            and self.teams_hostile("green", unit.team)
            and self.currently_visible_enemy(unit)
            for unit in self.units
        )

    def update_soundtrack(self):
        """Keep gameplay music aligned with the player's current information."""
        if self.state != "playing" or self.winner:
            mode = None
        else:
            mode = "fighting" if self.has_visible_enemy() else "peaceful"
        self.soundtrack.set_mode(mode)

    def is_visible(self, x, y):
        return (int(x), int(y)) in self.visible

    def is_display_visible(self, x, y):
        """Return whether the player UI should render this world position."""
        return not self.fog_of_war_enabled or self.is_visible(x, y)

    def toggle_fog_of_war(self):
        """Toggle only the player's fog overlay and hidden-object rendering."""
        self.fog_of_war_enabled = not self.fog_of_war_enabled

    def is_team_visible(self, team, x, y):
        """Return current shared terrain visibility for either combat team."""
        if team not in self._team_visibility_initialized:
            return False
        # ``visible`` is also a long-standing player-facing/test-facing fog
        # interface and may be deliberately edited between updates.
        if team == "green":
            return (int(x), int(y)) in self.visible
        if not self._team_visibility_initialized[team]:
            self.update_team_visibility(team)
        return (int(x), int(y)) in self.red_visible

    def terrain_sight_cost(self, start, end):
        """Return the terrain-weighted cost of the grid ray from start to end.

        The observer's own cell is not crossed and therefore has no cost. Each
        subsequent cell charges its terrain cost, scaled by the cardinal or
        diagonal distance used to enter it.
        """
        cells = self._corridor_cells(start, end)
        total = 0.0
        previous = cells[0]
        for cell in cells[1:]:
            step_length = (
                math.sqrt(2)
                if cell[0] != previous[0] and cell[1] != previous[1]
                else 1.0
            )
            terrain = self.terrain.get(cell)
            if terrain is None:
                terrain = TerrainCell("plains", 0)
            total += step_length * terrain_vision_cost(terrain.kind)
            previous = cell
        return total

    def has_terrain_line_of_sight(self, start, end, sight_budget):
        """Return whether a terrain-weighted grid ray fits the sight budget."""
        end_cell = self._nav_cell(end)
        if not (0 <= end_cell[0] < MAP_SIZE and 0 <= end_cell[1] < MAP_SIZE):
            return False
        return self.terrain_sight_cost(start, end) <= sight_budget

    def _vision_mask(self, start, sight_budget):
        """Return a cached sight mask for one observer grid cell."""
        observer_cell = self._nav_cell(start)
        key = (self.terrain_revision, observer_cell, float(sight_budget))
        cached = self._vision_mask_cache.get(key)
        if cached is not None:
            return cached
        cheapest_vision_cost = min(
            terrain_vision_cost(kind) for kind in TERRAIN_KINDS
        )
        max_distance = sight_budget / cheapest_vision_cost
        sx, sy = observer_cell
        mask = set()
        for x in range(
            max(0, int(sx - max_distance)),
            min(MAP_SIZE, int(sx + max_distance) + 1),
        ):
            for y in range(
                max(0, int(sy - max_distance)),
                min(MAP_SIZE, int(sy + max_distance) + 1),
            ):
                if self.has_terrain_line_of_sight(
                    observer_cell, (x, y), sight_budget
                ):
                    mask.add((x, y))
        self._vision_mask_cache[key] = frozenset(mask)
        return self._vision_mask_cache[key]

    def _refresh_vision_terrain_signature(self):
        """Invalidate masks when tests or tools replace terrain in place."""
        signature = hash(tuple(
            self.terrain[(x, y)].kind
            for x in range(MAP_SIZE) for y in range(MAP_SIZE)
        ))
        if signature != self._vision_terrain_signature:
            self._vision_mask_cache.clear()
            self._vision_terrain_signature = signature

    def update_team_visibility(self, team, refresh_terrain=True):
        """Refresh one team's shared sight map using cached observer masks."""
        if refresh_terrain:
            self._refresh_vision_terrain_signature()
        if team == "green" and self.level_number == 1:
            cells = {(x, y) for x in range(MAP_SIZE) for y in range(MAP_SIZE)}
        else:
            king = self.team_king(team)
            sources = (
                [(king.x, king.y, self.enemy_ai.KING_VISION_RADIUS)]
                if king is not None else []
            )
            sources += [
                (
                    unit.x,
                    unit.y,
                    self.enemy_ai.SCOUTING_RADIUS
                    if team == "red" else UNIT_VISION_RADIUS,
                )
                for unit in self.units
                if unit.team == team and unit.kind in COMBAT_UNIT_KINDS
                and unit.health > 0
            ]
            cells = set()
            for sx, sy, sight_budget in sources:
                cells.update(self._vision_mask((sx, sy), sight_budget))
            if self.level.has_checkpoints:
                for owned_checkpoint in self.checkpoints:
                    if owned_checkpoint.owner != team:
                        continue
                    cx, cy = owned_checkpoint.cell
                    radius = int(math.ceil(owned_checkpoint.profile.vision_radius))
                    cells.update(
                        (x, y)
                        for x in range(max(0, cx - radius), min(MAP_SIZE, cx + radius + 1))
                        for y in range(max(0, cy - radius), min(MAP_SIZE, cy + radius + 1))
                        if (x - cx) ** 2 + (y - cy) ** 2
                        <= owned_checkpoint.profile.vision_radius ** 2
                    )
            if team == "red" and self.level.has_checkpoints:
                checkpoint = self.checkpoint_by_uid(
                    self.enemy_ai.checkpoint_target_uid
                )
                if checkpoint is not None and self.enemy_ai.state == AIState.ATTACKING:
                    cx, cy = checkpoint.cell
                    radius = int(math.ceil(checkpoint.profile.defender_leash))
                    cells.update(
                        (x, y)
                        for x in range(max(0, cx - radius), min(MAP_SIZE, cx + radius + 1))
                        for y in range(max(0, cy - radius), min(MAP_SIZE, cy + radius + 1))
                        if (x - cx) ** 2 + (y - cy) ** 2
                        <= checkpoint.profile.defender_leash ** 2
                    )
        if team == "green":
            self.visible = cells
        else:
            self.red_visible = cells
        self._team_visibility_initialized[team] = True
        return cells

    def update_visibility(self):
        previous_visible = self.visible.copy()
        previous_explored_count = len(self.explored)
        self._refresh_vision_terrain_signature()
        self.update_team_visibility("green", refresh_terrain=False)
        self.update_team_visibility("red", refresh_terrain=False)
        for checkpoint in self.checkpoints:
            if checkpoint.cell in self.visible:
                checkpoint.discovered = True
        self.explored.update(self.visible)
        if self.visible != previous_visible or len(self.explored) != previous_explored_count:
            self._fog_revision += 1

    def find_target(self, unit, search_radius=None):
        if search_radius is None:
            search_radius = self.effective_attack_range(unit)
        if not self._movement_snapshot_active:
            self.rebuild_unit_spatial_hash()
        opponents = [
            candidate for candidate in self.nearby_units(unit, search_radius)
            if self.teams_hostile(unit.team, candidate.team) and candidate.health > 0
            and self.is_team_visible(unit.team, candidate.x, candidate.y)
        ]
        in_range = [
            enemy for enemy in opponents
            if dist((unit.x, unit.y), (enemy.x, enemy.y)) <= search_radius
        ]
        return min(
            in_range,
            key=lambda e: (dist((unit.x, unit.y), (e.x, e.y)), e.uid),
            default=None,
        )

    def autonomous_king_target(self, king):
        """Choose the nearest enemy inside the king's home defense radius."""
        return self.autonomous_guard_target(king)

    def autonomous_guard_target(self, guard):
        """Choose the nearest enemy inside a special unit's home defense radius."""
        candidates = [
            unit for unit in self.units
            if self.is_valid_guard_target(guard, unit)
            and (
                guard.team != "red"
                or self.is_team_visible("red", unit.x, unit.y)
            )
        ]
        return min(
            candidates,
            key=lambda unit: (
                dist((guard.x, guard.y), (unit.x, unit.y)),
                unit.uid,
            ),
            default=None,
        )

    @staticmethod
    def special_unit_engagement_radius(guard):
        if (
            guard.is_king_objective
            and guard.king_recovering
            and guard.king_recovery_home_reached
        ):
            return KING_RECOVERY_ENGAGEMENT_RADIUS
        return GUARD_LEASH_DISTANCE

    def is_valid_guard_target(self, guard, target):
        if (
            target is None
            or not self.teams_hostile(guard.team, target.team)
            or target.health <= 0
        ):
            return False
        home = guard.home_position or (guard.x, guard.y)
        return (
            dist(home, (target.x, target.y))
            <= self.special_unit_engagement_radius(guard)
        )

    @staticmethod
    def apply_movement_slow(unit, multiplier, duration):
        """Apply or refresh the strongest active non-stacking movement slow."""
        if unit.health <= 0:
            return
        if unit.slow_timer <= 0:
            unit.slow_multiplier = multiplier
        else:
            unit.slow_multiplier = min(unit.slow_multiplier, multiplier)
        unit.slow_timer = max(unit.slow_timer, duration)

    def native_splash_targets(self, attacker, primary, radius):
        """Return at most three deterministic secondary impact targets."""
        return sorted(
            (
                unit for unit in self.units
                if unit is not primary and unit.health > 0
                and self.teams_hostile(attacker.team, unit.team)
                and dist((unit.x, unit.y), (primary.x, primary.y)) <= radius
            ),
            key=lambda unit: (
                dist((unit.x, unit.y), (primary.x, primary.y)), unit.uid
            ),
        )[:NATIVE_SPLASH_TARGET_LIMIT]

    def guard_chase_destination(self, guard, target):
        """Clamp a pursuit point to the guard's leash circle."""
        home = guard.home_position or (guard.x, guard.y)
        dx, dy = target.x - home[0], target.y - home[1]
        distance = math.hypot(dx, dy)
        engagement_radius = self.special_unit_engagement_radius(guard)
        if distance <= engagement_radius:
            return target.x, target.y
        return (
            home[0] + dx / distance * engagement_radius,
            home[1] + dy / distance * engagement_radius,
        )

    def attack(self, attacker, target):
        if attacker.health <= 0 or target.health <= 0:
            return
        if (
            attacker.team == "red"
            and not self.is_team_visible("red", target.x, target.y)
        ):
            return
        damage = attacker.damage
        if (
            attacker.kind == "orc_spear_thrower"
            and attacker.health < attacker.max_health * .5
        ):
            damage *= 1.35
        if attacker.is_ranged:
            arrow_multiplier = {
                "shield": ARCHER_DAMAGE_VS_SHIELD_MULTIPLIER,
                "king": ARCHER_DAMAGE_VS_KING_MULTIPLIER,
                "knight": ARCHER_DAMAGE_VS_KNIGHT_MULTIPLIER,
            }.get(getattr(target, "kind", None), 1.0) if attacker.kind == "archer" else 1.0
            damage *= arrow_multiplier
            attacker_terrain = self.terrain_kind_at((attacker.x, attacker.y))
            target_terrain = self.terrain_kind_at((target.x, target.y))
            if attacker.kind == "archer" and attacker_terrain == "mountain" and target_terrain != "mountain":
                damage *= 1.2
            damage *= TERRAIN_METADATA[target_terrain][
                "ranged_damage_taken_multiplier"
            ]
        target_terrain = self.terrain_kind_at((target.x, target.y))
        damage *= TERRAIN_METADATA[target_terrain]["damage_taken_multiplier"]
        if target.kind == "dwarf_guard" and attacker.is_ranged:
            damage *= .70
        if target.kind == "dwarf_arbalist" and target.braced:
            damage *= .75
        target_health_before = target.health
        target.health -= damage
        target.flash = .12
        if attacker.kind == "demon_reaver":
            damage_dealt = min(target_health_before, max(0.0, damage))
            attacker.health = min(
                attacker.max_health,
                attacker.health + damage_dealt * DEMON_LIFESTEAL_RATIO,
            )
        if attacker.kind == "frost_colossus":
            self.apply_movement_slow(
                target, FROST_COLOSSUS_SLOW_MULTIPLIER, FROST_SLOW_SECONDS
            )
        if attacker.kind in ("infernal_warlock", "ice_hurler"):
            splash_radius = (
                WARLOCK_SPLASH_RADIUS
                if attacker.kind == "infernal_warlock"
                else ICE_HURLER_SPLASH_RADIUS
            )
            for splash_target in self.native_splash_targets(
                attacker, target, splash_radius
            ):
                splash_target.health -= damage * NATIVE_SPLASH_DAMAGE_RATIO
                splash_target.flash = .12
                if attacker.kind == "ice_hurler":
                    self.apply_movement_slow(
                        splash_target,
                        ICE_HURLER_SLOW_MULTIPLIER,
                        FROST_SLOW_SECONDS,
                    )
            if attacker.kind == "ice_hurler":
                self.apply_movement_slow(
                    target, ICE_HURLER_SLOW_MULTIPLIER, FROST_SLOW_SECONDS
                )
        if attacker.kind == "orc_cleaver":
            splash_target = min(
                (
                    unit for unit in self.units
                    if unit is not target and unit.health > 0
                    and self.teams_hostile(attacker.team, unit.team)
                    and dist((unit.x, unit.y), (target.x, target.y)) <= 1.25
                ),
                key=lambda unit: (
                    dist((unit.x, unit.y), (target.x, target.y)), unit.uid
                ),
                default=None,
            )
            if splash_target is not None:
                splash_target.health -= damage * .5
                splash_target.flash = .12
        if (
            target.is_king_objective
            and target.health > 0
            and target.health <= target.max_health * KING_RECOVERY_HEALTH_RATIO
            and not target.king_recovering
        ):
            self.begin_king_recovery(target)
        attacker.attack_timer = attacker.cooldown
        if attacker.is_ranged:
            attacker.movement_lock_timer = attacker.cooldown
            self.arrows.append([attacker.x, attacker.y, target.x, target.y, .22, attacker.team])
        elif attacker.kind == "king":
            dx, dy = target.x - attacker.x, target.y - attacker.y
            length = math.hypot(dx, dy)
            if length:
                dx, dy = dx / length, dy / length
            self.king_slashes.append(
                SlashEffect(
                    attacker.x, attacker.y, dx, dy,
                    KING_SLASH_LIFETIME, attacker.team,
                )
            )
        else:
            mx, my = (attacker.x + target.x) / 2, (attacker.y + target.y) / 2
            self.particles.append([mx, my, .25, attacker.team])

    def begin_king_recovery(self, king):
        """Immediately cancel combat and send a half-health king home."""
        king.king_recovering = True
        king.king_recovery_home_reached = False
        king.target = None
        king.target_pos = king.home_position or (king.x, king.y)
        king.tactical_pos = None
        self.clear_navigation(king)

    def terrain_kind_at(self, position):
        """Return gameplay terrain at a world position, defaulting to plains."""
        x, y = clamp_to_map(position)
        cell = self.terrain.get((int(x), int(y)))
        return "plains" if cell is None else cell.kind

    def effective_attack_range(self, unit):
        """Return a unit's current range after attacker-terrain bonuses."""
        bonus = 0.0
        if unit.kind == "archer":
            bonus = TERRAIN_METADATA[self.terrain_kind_at((unit.x, unit.y))][
                "archer_range_bonus"
            ]
        return unit.attack_range + bonus

    def terrain_cell_and_speed_multiplier(self, position):
        """Resolve gameplay terrain for an in-bounds world position safely.

        Cosmetic variation is deliberately ignored.  The plains fallback
        keeps movement usable for tools that construct a partial terrain map.
        """
        x, y = clamp_to_map(position)
        cell = self.terrain.get((
            min(MAP_SIZE - 1, max(0, int(x))),
            min(MAP_SIZE - 1, max(0, int(y))),
        ))
        if cell is None:
            cell = TerrainCell("plains", 0)
        return cell, terrain_movement_multiplier(cell.kind)

    def _move_with_terrain(self, unit, velocity, dt, max_distance=None):
        """Integrate a base velocity, splitting time at terrain boundaries.

        Separation is terrain-scaled along with intended travel.  Its combined
        speed remains capped at the existing separation maximum, including on
        paths, so a fast tile cannot turn overlap correction into tunneling.
        """
        velocity_x, velocity_y = velocity
        base_speed = math.hypot(velocity_x, velocity_y)
        if base_speed <= 1e-12 or dt <= 0:
            return
        direction_x = velocity_x / base_speed
        direction_y = velocity_y / base_speed
        remaining_time = dt
        remaining_distance = max_distance
        while remaining_time > 1e-12:
            # At an exact boundary, sample the tile being entered rather than
            # repeatedly charging time to the tile just left.
            sample_x = unit.x + direction_x * 1e-9
            sample_y = unit.y + direction_y * 1e-9
            terrain_cell, multiplier = self.terrain_cell_and_speed_multiplier(
                (sample_x, sample_y)
            )
            if unit.kind == "elf_bladedancer" and terrain_cell.kind == "forest":
                multiplier = 1.0
            movement_speed = unit.speed * unit.slow_multiplier
            effective_speed = min(
                base_speed * multiplier,
                movement_speed * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER,
            )
            if effective_speed <= 1e-12:
                break
            allowed_distance = effective_speed * remaining_time
            if remaining_distance is not None:
                allowed_distance = min(allowed_distance, remaining_distance)

            boundary_distance = math.inf
            for coordinate, direction in (
                (unit.x, direction_x), (unit.y, direction_y)
            ):
                if direction > 1e-12:
                    boundary = math.floor(coordinate + 1e-9) + 1
                    boundary_distance = min(
                        boundary_distance, (boundary - coordinate) / direction
                    )
                elif direction < -1e-12:
                    boundary = math.ceil(coordinate - 1e-9) - 1
                    boundary_distance = min(
                        boundary_distance, (boundary - coordinate) / direction
                    )

            travel = min(allowed_distance, boundary_distance)
            if travel <= 1e-12:
                break
            unit.x, unit.y = clamp_to_map((
                unit.x + direction_x * travel,
                unit.y + direction_y * travel,
            ))
            remaining_time -= travel / effective_speed
            if remaining_distance is not None:
                remaining_distance -= travel
                if remaining_distance <= 1e-12:
                    break
            if travel + 1e-12 < allowed_distance:
                continue
            break

    def move_unit_toward(self, unit, destination, dt):
        """Blend preferred travel with shared local separation.

        During ``Game.update`` every unit reads the same pre-movement spatial
        snapshot. Direct calls rebuild the index, which keeps this primitive
        useful and unsurprising in tests and tools.
        """
        dx, dy = destination[0] - unit.x, destination[1] - unit.y
        distance = math.hypot(dx, dy)
        movement_speed = unit.speed * unit.slow_multiplier
        preferred_x = preferred_y = 0.0
        if distance >= .08:
            preferred_x = dx / distance * movement_speed
            preferred_y = dy / distance * movement_speed

        preferred_step = min(
            distance, movement_speed * max(0.0, dt)
        ) if distance >= .08 else 0.0
        predicted_position = (
            unit.x + dx / distance * preferred_step,
            unit.y + dy / distance * preferred_step,
        ) if preferred_step else (unit.x, unit.y)
        separation_x, separation_y = self.unit_separation_vector(
            unit, predicted_position
        )
        separation_amount = math.hypot(separation_x, separation_y)
        # A unit already at its assigned slot should ignore shallow crowd
        # pressure. Deep penetration still resolves, so this cannot create
        # permanent stacks at a shared destination.
        if (
            distance <= UNIT_SLOT_SETTLE_RADIUS
            and separation_amount <= .04
        ):
            separation_amount = 0.0
            separation_x = separation_y = 0.0
        if separation_amount <= UNIT_TINY_SEPARATION:
            separation_x = separation_y = 0.0
        else:
            overlap_response = min(
                1.0, separation_amount / UNIT_SOFT_OVERLAP
            )
            overlap_response = overlap_response * overlap_response * (
                3.0 - 2.0 * overlap_response
            )
            separation_speed = min(
                max(
                    separation_amount * UNIT_SEPARATION_GAIN,
                    movement_speed
                    * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER
                    * overlap_response,
                ),
                movement_speed * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER,
            )
            separation_x = separation_x / separation_amount * separation_speed
            separation_y = separation_y / separation_amount * separation_speed

        velocity_x = preferred_x + separation_x
        velocity_y = preferred_y + separation_y
        velocity = math.hypot(velocity_x, velocity_y)
        if velocity <= 1e-12 or dt <= 0:
            return False
        max_speed = movement_speed * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER
        if velocity > max_speed:
            velocity_x *= max_speed / velocity
            velocity_y *= max_speed / velocity
        before = (unit.x, unit.y)
        self._move_with_terrain(
            unit,
            (velocity_x, velocity_y),
            dt,
            distance if separation_x == separation_y == 0 else None,
        )
        if unit.is_king_objective or unit.is_autonomous_guard:
            home = unit.home_position or before
            leash_dx, leash_dy = unit.x - home[0], unit.y - home[1]
            leash_distance = math.hypot(leash_dx, leash_dy)
            if leash_distance > GUARD_LEASH_DISTANCE:
                unit.x = home[0] + leash_dx / leash_distance * GUARD_LEASH_DISTANCE
                unit.y = home[1] + leash_dy / leash_distance * GUARD_LEASH_DISTANCE
                unit.x, unit.y = clamp_to_map((unit.x, unit.y))
        moved = dist(before, (unit.x, unit.y)) > 1e-9
        unit.moved_this_update |= moved
        if moved and unit.kind == "dwarf_arbalist":
            unit.stationary_time = 0.0
            unit.braced = False
        return moved

    @staticmethod
    def _nav_cell(position):
        x, y = clamp_to_map(position)
        return int(x), int(y)

    @staticmethod
    def _nav_world(cell):
        return clamp_to_map((cell[0] + .5, cell[1] + .5))

    @staticmethod
    def _segment_distance(point, start, end):
        vx, vy = end[0] - start[0], end[1] - start[1]
        length2 = vx * vx + vy * vy
        if length2 <= 1e-12:
            return dist(point, start)
        amount = max(0.0, min(
            1.0,
            ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy)
            / length2,
        ))
        closest = (start[0] + vx * amount, start[1] + vy * amount)
        return dist(point, closest)

    def _navigation_occupancy(self, mover, final_destination, combat_target=None):
        """Build deterministic dynamic occupancy from the movement snapshot.

        Stationary units and enemies are hard A* obstacles. Moving allies are
        costly rather than blocked so crossing groups can flow through one
        another. The mover, its combat target, and final destination remain
        enterable. Stable UID iteration makes equivalent occupancy deterministic.
        """
        hard, soft = set(), {}
        clearance = max(0.0, UNIT_PHYSICAL_RADIUS - UNIT_SOFT_OVERLAP)
        for other in sorted(self.units, key=lambda candidate: candidate.uid):
            if other is mover or other is combat_target or other.health <= 0:
                continue
            moving_ally = (
                other.team == mover.team
                and other.target_pos is not None
                and other.speed > 0
                and not other.is_king_objective
            )
            stationary_special = (
                other.is_king_objective
                or (other.is_autonomous_guard and other.target_pos is None)
            )
            radius = clearance * 2
            min_x = max(0, int(math.floor(other.x - radius)))
            max_x = min(MAP_SIZE - 1, int(math.floor(other.x + radius)))
            min_y = max(0, int(math.floor(other.y - radius)))
            max_y = min(MAP_SIZE - 1, int(math.floor(other.y + radius)))
            for x in range(min_x, max_x + 1):
                for y in range(min_y, max_y + 1):
                    cell = (x, y)
                    if dist(self._nav_world(cell), (other.x, other.y)) > radius:
                        continue
                    if moving_ally and not stationary_special:
                        soft[cell] = max(soft.get(cell, 0.0), 8.0)
                    else:
                        hard.add(cell)
        hard.discard(self._nav_cell((mover.x, mover.y)))
        # Orders remain achievable even when their precise cell is occupied.
        hard.discard(self._nav_cell(final_destination))
        return hard, soft

    def _corridor_clear(self, start, end, hard_cells):
        """Grid line-of-sight with the same no-corner-cutting rule as A*."""
        cells = self._corridor_cells(start, end)
        start_cell = cells[0]
        previous = start_cell
        for cell in cells[1:]:
            if cell in hard_cells:
                return False
            if cell[0] != previous[0] and cell[1] != previous[1]:
                if (cell[0], previous[1]) in hard_cells:
                    return False
                if (previous[0], cell[1]) in hard_cells:
                    return False
            previous = cell
        return True

    def _corridor_cells(self, start, end):
        """Return deterministic Bresenham cells crossed by a nav segment."""
        start_cell, end_cell = self._nav_cell(start), self._nav_cell(end)
        x, y = start_cell
        target_x, target_y = end_cell
        dx, dy = abs(target_x - x), abs(target_y - y)
        step_x = 1 if x < target_x else -1
        step_y = 1 if y < target_y else -1
        error = dx - dy
        cells = []
        while True:
            cells.append((x, y))
            if (x, y) == end_cell:
                return cells
            doubled = 2 * error
            next_x, next_y = x, y
            if doubled > -dy:
                error -= dy
                next_x += step_x
            if doubled < dx:
                error += dx
                next_y += step_y
            x, y = next_x, next_y

    def _terrain_step_cost(self, current, neighbor):
        """Return base-speed travel time for a cardinal or diagonal grid step.

        Costs are seconds for a hypothetical unit whose plains speed is one
        tile/second. Entering terrain divides geometric step length by its
        speed multiplier; actual unit speed is a common factor and cannot
        change the optimal route.
        """
        diagonal = current[0] != neighbor[0] and current[1] != neighbor[1]
        length = math.sqrt(2) if diagonal else 1.0
        cell = self.terrain.get(neighbor)
        if cell is None:
            cell = TerrainCell("plains", 0)
        return length / terrain_movement_multiplier(cell.kind)

    def _terrain_corridor_cost(self, start, end):
        cells = self._corridor_cells(start, end)
        return sum(
            self._terrain_step_cost(current, neighbor)
            for current, neighbor in zip(cells, cells[1:])
        )

    def _terrain_search_relevant(self, start, end):
        """Bound the one-shot A* policy to terrain near the direct order."""
        start_cell, end_cell = self._nav_cell(start), self._nav_cell(end)
        radius = min(
            UNIT_TERRAIN_ROUTE_SCAN_RADIUS,
            max(1, int(math.ceil(dist(start_cell, end_cell) * .25))),
        )
        min_x = max(0, min(start_cell[0], end_cell[0]) - radius)
        max_x = min(MAP_SIZE - 1, max(start_cell[0], end_cell[0]) + radius)
        min_y = max(0, min(start_cell[1], end_cell[1]) - radius)
        max_y = min(MAP_SIZE - 1, max(start_cell[1], end_cell[1]) + radius)
        return any(
            terrain_movement_multiplier(
                self.terrain[(x, y)].kind
                if (x, y) in self.terrain else "plains"
            ) != 1.0
            for x in range(min_x, max_x + 1)
            for y in range(min_y, max_y + 1)
        )

    def _direct_unit_corridor_clear(
        self, mover, start, end, combat_target=None
    ):
        """Use exact unit geometry before paying the cost of grid routing."""
        clearance = UNIT_SEPARATION_RADIUS - UNIT_SOFT_OVERLAP
        if not self._movement_snapshot_active:
            self.rebuild_unit_spatial_hash()
        for other in self.unit_spatial_hash.segment_candidates(
            start, end, clearance
        ):
            if other is mover or other is combat_target or other.health <= 0:
                continue
            moving_unit = (
                other.target_pos is not None
                and other.speed > 0
                and not other.is_king_objective
            )
            # Moving armies resolve one another through attack-move targeting
            # and local separation. Treating every opponent as a static wall
            # launches an A* search for almost every unit in a dense battle.
            if moving_unit:
                continue
            # The exact destination remains enterable even when occupied.
            if dist((other.x, other.y), end) < clearance * .5:
                continue
            if self._segment_distance((other.x, other.y), start, end) < clearance:
                return False
        return True

    def _astar(self, mover, destination, combat_target=None):
        hard, soft = self._navigation_occupancy(
            mover, destination, combat_target
        )
        start, goal = self._nav_cell((mover.x, mover.y)), self._nav_cell(destination)
        directions = (
            (-1, 0), (0, -1), (0, 1), (1, 0),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        )
        route_x, route_y = goal[0] - start[0], goal[1] - start[1]
        route_length = max(1.0, math.hypot(route_x, route_y))
        side_preference = mover.nav_side_preference or (
            -1 if mover.uid % 2 else 1
        )

        def side_penalty(cell):
            offset_x, offset_y = cell[0] - start[0], cell[1] - start[1]
            cross = route_x * offset_y - route_y * offset_x
            return max(0.0, -side_preference * cross / route_length) * .001

        frontier = [(0.0, 0.0, start[1], start[0], start)]
        came_from = {}
        costs = {start: 0.0}
        expanded = 0
        while frontier:
            _, current_cost, _, _, current = heapq.heappop(frontier)
            if current_cost != costs.get(current):
                continue
            if expanded >= UNIT_ASTAR_MAX_EXPANSIONS:
                self.path_expanded_nodes += expanded
                self.path_max_expanded_nodes = max(
                    self.path_max_expanded_nodes, expanded
                )
                self.path_limit_failures += 1
                return None, hard
            expanded += 1
            if current == goal:
                break
            for offset_x, offset_y in directions:
                neighbor = (current[0] + offset_x, current[1] + offset_y)
                if not (0 <= neighbor[0] < MAP_SIZE and 0 <= neighbor[1] < MAP_SIZE):
                    continue
                if neighbor in hard:
                    continue
                diagonal = offset_x != 0 and offset_y != 0
                if diagonal and (
                    (current[0] + offset_x, current[1]) in hard
                    or (current[0], current[1] + offset_y) in hard
                ):
                    continue
                step_cost = self._terrain_step_cost(current, neighbor)
                new_cost = current_cost + step_cost + soft.get(neighbor, 0.0)
                if new_cost + 1e-12 >= costs.get(neighbor, math.inf):
                    continue
                costs[neighbor] = new_cost
                came_from[neighbor] = current
                # The fastest terrain multiplier is 2.0, so straight-line
                # distance / 2 is an admissible lower bound in these units.
                heuristic = math.hypot(
                    goal[0] - neighbor[0], goal[1] - neighbor[1]
                ) / 2.0
                heapq.heappush(frontier, (
                    new_cost + heuristic + side_penalty(neighbor), new_cost,
                    neighbor[1], neighbor[0], neighbor,
                ))
        self.path_expanded_nodes += expanded
        self.path_max_expanded_nodes = max(
            self.path_max_expanded_nodes, expanded
        )
        if goal not in costs:
            return None, hard
        cells, current = [goal], goal
        while current != start:
            current = came_from[current]
            cells.append(current)
        cells.reverse()
        # Greedily smooth only when the clear segment is no slower than the
        # A* sub-route. This retains waypoints that capture terrain savings.
        waypoints = []
        anchor_position = (mover.x, mover.y)
        index = 1
        while index < len(cells):
            furthest = index
            route_cost = self._terrain_step_cost(
                cells[index - 1], cells[index]
            )
            for candidate in range(index + 1, len(cells)):
                route_cost += self._terrain_step_cost(
                    cells[candidate - 1], cells[candidate]
                )
                if not self._corridor_clear(
                    anchor_position, self._nav_world(cells[candidate]), hard
                ):
                    break
                if self._terrain_corridor_cost(
                    anchor_position, self._nav_world(cells[candidate])
                ) > route_cost + 1e-9:
                    continue
                furthest = candidate
            waypoint = (
                destination if furthest == len(cells) - 1
                else self._nav_world(cells[furthest])
            )
            waypoints.append(clamp_to_map(waypoint))
            anchor_position = waypoints[-1]
            index = furthest + 1
        return waypoints, hard

    def _navigation_destination(self, unit, destination, combat_target):
        destination = clamp_to_map(destination)
        if combat_target is None:
            return destination
        dx, dy = unit.x - combat_target.x, unit.y - combat_target.y
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            dx, dy, length = 1.0, 0.0, 1.0
        # Aim slightly inside range so the movement tolerance cannot leave the
        # unit just outside combat range forever.
        approach = max(0.0, self.effective_attack_range(unit) - .12)
        return clamp_to_map((
            combat_target.x + dx / length * approach,
            combat_target.y + dy / length * approach,
        ))

    def navigate_unit_toward(self, unit, destination, dt, combat_target=None):
        """Move directly unless obstruction or a sustained stall activates A*.

        Detour waypoints are cached across updates. A changed destination or
        combat-target identity invalidates them immediately; blocked cached
        segments replan on a bounded interval, and a clear direct corridor
        must remain clear briefly before an old detour is discarded.
        """
        final = self._navigation_destination(unit, destination, combat_target)
        if dist((unit.x, unit.y), final) <= UNIT_SLOT_SETTLE_RADIUS:
            self.clear_navigation(unit)
            return self.move_unit_toward(unit, final, dt)
        target_key = (
            getattr(combat_target, "uid", None),
            combat_target is not None,
        )
        destination_changed = (
            unit.nav_destination is None
            or dist(unit.nav_destination, final) > .35
            or unit.nav_destination_key != target_key
            or unit.nav_terrain_revision != self.terrain_revision
        )
        if destination_changed:
            self.clear_navigation(unit)
            unit.nav_destination = final
            unit.nav_destination_key = target_key
            unit.nav_last_progress_position = (unit.x, unit.y)
            unit.nav_terrain_revision = self.terrain_revision
            # Keep equivalent detours on one deterministic side for the life
            # of this strategic destination.
            unit.nav_side_preference = -1 if unit.uid % 2 else 1
        next_waypoint = (
            unit.nav_waypoints[unit.nav_waypoint_index]
            if unit.nav_waypoint_index < len(unit.nav_waypoints) else None
        )
        unit.nav_direct_check_timer = max(
            0.0, unit.nav_direct_check_timer - max(0.0, dt)
        )
        if (
            not destination_changed
            and next_waypoint is None
            and unit.nav_direct_check_timer > 0
        ):
            direct_clear = True
        else:
            direct_clear = self._direct_unit_corridor_clear(
                unit, (unit.x, unit.y), final, combat_target
            )
            unit.nav_direct_check_timer = .12
        # Occupancy is only needed to create or validate a detour.  The common
        # unobstructed case has already been decided by exact unit geometry.
        next_blocked = (
            next_waypoint is not None
            and not self._direct_unit_corridor_clear(
                unit, (unit.x, unit.y), next_waypoint, combat_target
            )
        )
        last_progress = unit.nav_last_progress_position or (unit.x, unit.y)
        progress = dist(last_progress, (unit.x, unit.y))
        if progress >= .04:
            unit.nav_blocked_time = 0.0
            unit.nav_last_progress_position = (unit.x, unit.y)
        else:
            unit.nav_blocked_time += max(0.0, dt)

        refresh_due = (
            self.navigation_time - unit.nav_last_path_time
            >= UNIT_PATH_RECALCULATION_INTERVAL
        )
        stalled = unit.nav_blocked_time >= UNIT_BLOCKED_TIME_THRESHOLD
        terrain_search = (
            destination_changed
            and direct_clear
            and combat_target is None
            and dist((unit.x, unit.y), final) <= UNIT_TERRAIN_ROUTE_MAX_DISTANCE
            and self._terrain_search_relevant((unit.x, unit.y), final)
        )
        need_path = (
            (not direct_clear or stalled or terrain_search)
            and (
                destination_changed
                or (
                    refresh_due
                    and (
                        not unit.nav_waypoints
                        or next_blocked
                        or stalled
                    )
                )
            )
        )
        if (
            need_path
            and (
                not self._movement_snapshot_active
                or self._path_searches_this_update
                < UNIT_ASTAR_SEARCHES_PER_UPDATE
            )
        ):
            if self._movement_snapshot_active:
                self._path_searches_this_update += 1
            waypoints, _ = self._astar(unit, final, combat_target)
            self.path_calculation_count += 1
            self.path_calculation_lengths.append(
                0 if waypoints is None else len(waypoints)
            )
            unit.nav_last_path_time = self.navigation_time
            unit.nav_blocked_time = 0.0
            unit.nav_last_progress_position = (unit.x, unit.y)
            unit.nav_waypoints = waypoints or []
            unit.nav_terrain_route = terrain_search and bool(waypoints)
            unit.nav_waypoint_index = 0
            unit.nav_clear_time = 0.0
            next_waypoint = unit.nav_waypoints[0] if unit.nav_waypoints else None
        elif direct_clear and next_waypoint is not None and not unit.nav_terrain_route:
            unit.nav_clear_time += max(0.0, dt)
            if unit.nav_clear_time < UNIT_PATH_CLEAR_HYSTERESIS:
                direct_clear = False
        else:
            unit.nav_clear_time = 0.0
        if direct_clear and not unit.nav_terrain_route:
            unit.nav_waypoints.clear()
            unit.nav_waypoint_index = 0
            next_waypoint = None

        travel_target = clamp_to_map(next_waypoint or final)
        moved = self.move_unit_toward(unit, travel_target, dt)
        if next_waypoint is not None and dist(
            (unit.x, unit.y), next_waypoint
        ) <= UNIT_WAYPOINT_ARRIVAL_TOLERANCE:
            unit.nav_waypoint_index += 1
        if dist((unit.x, unit.y), final) < .08:
            self.clear_navigation(unit)
        return moved

    def update_unit(self, u, dt):
        moved_last_update = u.moved_this_update
        u.moved_this_update = False
        if u.slow_timer <= dt + 1e-9:
            u.slow_timer = 0.0
            u.slow_multiplier = 1.0
        else:
            u.slow_timer -= max(0.0, dt)
        if u.kind == "dwarf_arbalist":
            if moved_last_update:
                u.stationary_time = 0.0
                u.braced = False
            else:
                u.stationary_time += max(0.0, dt)
                u.braced = (
                    u.stationary_time + 1e-9
                    >= DWARF_ARBALIST_BRACE_SECONDS
                )
        if u.health <= 0:
            u.selected = False
            u.target = None
            u.target_pos = None
            u.order_pos = None
            u.target_auto_acquired = False
            u.tactical_pos = None
            u.slow_timer = 0.0
            u.slow_multiplier = 1.0
            self.clear_navigation(u)
            return
        if u.is_king_objective or u.is_autonomous_guard:
            u.selected = False
            u.tactical_pos = None
            if u.home_position is None:
                u.home_position = (u.x, u.y)
            if u.is_king_objective:
                if (
                    u.health <= u.max_health * KING_RECOVERY_HEALTH_RATIO
                    and not u.king_recovering
                ):
                    self.begin_king_recovery(u)
                at_home = dist((u.x, u.y), u.home_position) < .08
                if (
                    at_home
                    and u.health < u.max_health
                    and not self._movement_snapshot_active
                ):
                    u.health = min(u.max_health, u.health + KING_HOME_HEAL_RATE * dt)
                if u.health >= u.max_health:
                    u.king_recovering = False
                    u.king_recovery_home_reached = False
        elif not (u.is_player_commandable or u.is_enemy_ai_commandable or u.is_native_defender):
            u.selected = False
            u.target = None
            u.target_pos = None
        u.attack_timer = max(0, u.attack_timer - dt)
        if u.movement_lock_timer <= dt + 1e-9:
            u.movement_lock_timer = 0
        else:
            u.movement_lock_timer -= dt
        u.flash = max(0, u.flash - dt)
        movement_locked = u.is_ranged and u.movement_lock_timer > 0
        target = u.target
        if target is not None and getattr(target, "health", 0) <= 0:
            dead_target_position = (target.x, target.y)
            self.release_combat_target(u)
            target = None
            if (
                u.order_pos is None
                and
                u.target_pos is not None
                and dist(u.target_pos, dead_target_position) <= .35
            ):
                u.target_pos = None
        if (
            u.is_player_commandable
            and target is not None
            and u.target_auto_acquired
            and (
                not self.is_team_visible("green", target.x, target.y)
                or dist((u.x, u.y), (target.x, target.y))
                > PLAYER_AUTO_ATTACK_LEASH_RADIUS
            )
        ):
            self.release_combat_target(u)
            target = None
        if u.is_king_objective or u.is_autonomous_guard:
            if (
                u.is_king_objective
                and u.king_recovering
                and not u.king_recovery_home_reached
            ):
                u.target = None
                u.target_pos = u.home_position
                if dist((u.x, u.y), u.home_position) < .08:
                    u.x, u.y = u.home_position
                    u.target_pos = None
                    self.clear_navigation(u)
                    u.king_recovery_home_reached = True
                else:
                    self.navigate_unit_toward(u, u.home_position, dt)
                    if (u.x, u.y) == u.home_position:
                        u.target_pos = None
                        u.king_recovery_home_reached = True
                if not u.king_recovery_home_reached:
                    return
            target = self.autonomous_guard_target(u)
            u.target = target
            if target is None:
                u.target_pos = u.home_position
                if dist((u.x, u.y), u.home_position) < .08:
                    u.x, u.y = u.home_position
                    u.target_pos = None
                else:
                    self.navigate_unit_toward(u, u.home_position, dt)
                    if (u.x, u.y) == u.home_position:
                        u.target_pos = None
                return
            d = dist((u.x, u.y), (target.x, target.y))
            if d <= self.effective_attack_range(u):
                u.target_pos = None
                self.clear_navigation(u)
                if u.attack_timer <= 0:
                    self.attack(u, target)
                return
            u.target_pos = self.guard_chase_destination(u, target)
            self.navigate_unit_toward(u, u.target_pos, dt, target)
            return
        if u.is_native_defender:
            checkpoint = self.checkpoint_by_uid(u.checkpoint_uid)
            raid_destination = self.native_raid_destination(u)
            is_raider = (
                u.raid_target_checkpoint_uid is not None
                or u.raid_target_king_team is not None
            )
            target = self.native_defender_target(u)
            u.target = target
            if checkpoint is None:
                u.target_pos = None
                return
            if target is None:
                home = (
                    raid_destination
                    if is_raider and raid_destination is not None
                    else u.home_position or (checkpoint.x, checkpoint.y)
                )
                if dist((u.x, u.y), home) <= .08:
                    u.x, u.y = home
                    u.target_pos = None
                    self.clear_navigation(u)
                else:
                    u.target_pos = home
                    self.navigate_unit_toward(u, home, dt)
                return
            distance = dist((u.x, u.y), (target.x, target.y))
            if u.kind == "elf_ranger":
                dx, dy = u.x - target.x, u.y - target.y
                if distance <= 1e-9:
                    dx, dy, distance = 1.0, 0.0, 1.0
                desired = (
                    target.x + dx / distance * ELF_RANGER_PREFERRED_RANGE,
                    target.y + dy / distance * ELF_RANGER_PREFERRED_RANGE,
                )
                leash_center = raid_destination or (checkpoint.x, checkpoint.y)
                leash_dx = desired[0] - leash_center[0]
                leash_dy = desired[1] - leash_center[1]
                leash_distance = math.hypot(leash_dx, leash_dy)
                if leash_distance > ELF_RANGER_KITE_LEASH:
                    desired = (
                        leash_center[0]
                        + leash_dx / leash_distance * ELF_RANGER_KITE_LEASH,
                        leash_center[1]
                        + leash_dy / leash_distance * ELF_RANGER_KITE_LEASH,
                    )
                if (
                    abs(distance - ELF_RANGER_PREFERRED_RANGE) > .2
                    and not movement_locked
                ):
                    u.target_pos = clamp_to_map(desired)
                    self.navigate_unit_toward(u, u.target_pos, dt, target)
                distance = dist((u.x, u.y), (target.x, target.y))
                if (
                    distance <= self.effective_attack_range(u)
                    and u.attack_timer <= 0
                ):
                    self.attack(u, target)
                return
            if distance <= self.effective_attack_range(u):
                u.target_pos = None
                self.clear_navigation(u)
                if u.attack_timer <= 0 and (not u.is_ranged or not u.moved_this_update):
                    self.attack(u, target)
                return
            u.target_pos = (target.x, target.y)
            if not movement_locked:
                self.navigate_unit_toward(u, u.target_pos, dt, target)
            return
        if u.is_enemy_ai_commandable:
            auto = self.enemy_ai.choose_target(u)
            # Strategic scoring may prefer an opponent that still needs to be
            # pursued. Do not walk past a player unit that can be struck now.
            if (
                not self.enemy_ai.retreat_ordered(u)
                and (
                    auto is None
                    or dist((u.x, u.y), (auto.x, auto.y))
                    > self.effective_attack_range(u)
                )
            ):
                in_range = self.find_target(u)
                if in_range is not None:
                    auto = in_range
            target = auto
        elif u.is_player_commandable:
            # Player units have no target scoring or sticky combat priority:
            # continuously follow whichever visible enemy is nearest.
            auto = self.find_target(u, PLAYER_AUTO_ATTACK_RADIUS)
        else:
            auto = None
        if auto is not None:
            target = auto
            u.target = auto
            if u.is_player_commandable:
                u.target_auto_acquired = True
            elif u.is_enemy_ai_commandable:
                # This snapshot is the only pursuit information retained if
                # shared red vision is lost on a later update.
                u.target_pos = (auto.x, auto.y)
        tactical_pos = (
            self.enemy_ai.tactical_destination(u, dt)
            if u.is_enemy_ai_commandable else None
        )
        if tactical_pos is not None:
            if not movement_locked and self.move_unit_toward(
                u, tactical_pos, dt
            ):
                return
            if dist((u.x, u.y), tactical_pos) < .08:
                u.tactical_pos = None
        if target is not None:
            d = dist((u.x, u.y), (target.x, target.y))
            if d <= self.effective_attack_range(u):
                self.clear_navigation(u)
                if (
                    u.attack_timer <= 0
                    and (not u.is_ranged or not u.moved_this_update)
                ):
                    self.attack(u, target)
                return
            u.target_pos = (target.x, target.y)
        if u.target_pos:
            if dist((u.x, u.y), u.target_pos) < .08:
                if (
                    movement_locked
                    or not self.navigate_unit_toward(
                        u, u.target_pos, dt, target
                    )
                ):
                    u.target_pos = None
                    if (
                        target is None
                        and u.is_player_commandable
                        and u.order_pos is not None
                    ):
                        u.order_pos = None
                    self.clear_navigation(u)
            elif not movement_locked:
                self.navigate_unit_toward(u, u.target_pos, dt, target)
        elif not movement_locked:
            # Commandable units with no current order may still resolve an
            # excessive overlap. Kings and idle guards never reach this path.
            self.move_unit_toward(u, (u.x, u.y), dt)

    def update(self, dt):
        if self.state != "playing" or self.winner:
            self.update_soundtrack()
            return
        self.message_time = max(0, self.message_time - dt)
        self.navigation_time += max(0.0, dt)
        self._path_searches_this_update = 0
        self.update_checkpoints(dt)
        self.essence += self.income_rate("green") * dt
        self.enemy_essence += self.income_rate("red") * dt
        if self.level.enemy_ai == "full":
            self.enemy_ai.update(dt)
        elif self.level.enemy_ai == "simple":
            self.update_simple_enemy_ai()
        # One deterministic snapshot per simulation update. Movement still uses
        # the same pre-movement positions, avoiding list-order feedback.
        self.rebuild_unit_spatial_hash()
        self._movement_snapshot_active = True
        try:
            for u in list(self.units):
                self.update_unit(u, dt)
                # A king can die partway through this loop. Stop immediately:
                # level-three AI routines require both live objectives and
                # must not run after team_king() starts returning None.
                if (
                    self.objective_health("green") <= 0
                    or (
                        self.level_number != 1
                        and self.objective_health("red") <= 0
                    )
                ):
                    break
        finally:
            self._movement_snapshot_active = False
        for king in (
            unit for unit in self.units
            if unit.is_king_objective and unit.health > 0
        ):
            home = king.home_position or (king.x, king.y)
            if dist((king.x, king.y), home) < .08 and king.health < king.max_health:
                king.health = min(
                    king.max_health,
                    king.health + KING_HOME_HEAL_RATE * dt,
                )
                if king.health >= king.max_health:
                    king.king_recovering = False
                    king.king_recovery_home_reached = False
        dead_units = [unit for unit in self.units if unit.health <= 0]
        dead_green_king = any(
            unit.team == "green" and unit.is_king_objective
            for unit in dead_units
        )
        dead_red_king = any(
            unit.team == "red" and unit.is_king_objective
            for unit in dead_units
        )
        # A mutual kill is a defeat: the player must keep the Verdant King
        # alive while destroying the Crimson King.
        if dead_green_king:
            self.winner = "DEFEAT"
        elif dead_red_king or (
            self.level_number == 1
            and not any(
                unit.team == "red" and unit.health > 0
                for unit in self.units
            )
        ):
            self.winner = "VICTORY"
        for unit in self.units:
            if unit.team == "green" and unit.health <= 0:
                self.enemy_ai.forget_player_unit(unit.uid)
            if unit.target is not None and getattr(unit.target, "health", 0) <= 0:
                dead_target_position = (unit.target.x, unit.target.y)
                self.release_combat_target(unit)
                if (
                    unit.order_pos is None
                    and
                    unit.target_pos is not None
                    and dist(unit.target_pos, dead_target_position) <= .35
                ):
                    unit.target_pos = None
        self.units[:] = [u for u in self.units if u.health > 0]
        living_targets = set(id(unit) for unit in self.units)
        for unit in self.units:
            if unit.target is not None and (
                id(unit.target) not in living_targets
                or getattr(unit.target, "health", 0) <= 0
            ):
                self.release_combat_target(unit)
        for a in self.arrows:
            a[4] -= dt
        self.arrows[:] = [a for a in self.arrows if a[4] > 0]
        for p in self.particles:
            p[2] -= dt
        self.particles[:] = [p for p in self.particles if p[2] > 0]
        for slash in self.king_slashes:
            slash.life -= dt
        self.king_slashes[:] = [
            slash for slash in self.king_slashes if slash.life > 0
        ]
        self.reveal_tick -= dt
        if self.reveal_tick <= 0:
            self.update_visibility()
            self.reveal_tick = .12
        self.update_soundtrack()

    def update_simple_enemy_ai(self):
        """Spend each complete 200-essence tranche on an immediate attacker."""
        while self.enemy_essence >= UNIT_COSTS["swordsman"]:
            if not self.recruit("swordsman", "red"):
                break
            attacker = self.units[-1]
            objective = self.team_king("green")
            if objective is not None:
                attacker.target = objective
                attacker.target_pos = (objective.x, objective.y)

    def draw_terrain(self):
        w, h = self.screen.get_size()
        view_h = h - HUD_H
        self.screen.fill((70, 101, 55), pygame.Rect(0, 0, w, max(0, view_h)))
        old_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(0, 0, w, max(0, view_h)))
        cache_key = (self.terrain_revision, MAP_SIZE, self.zoom)
        if cache_key != self._terrain_world_cache_key:
            world_size = max(1, round(MAP_SIZE * self.zoom))
            world = pygame.Surface((world_size, world_size))
            detailed = self.zoom >= TERRAIN_DETAIL_MIN_ZOOM
            for x in range(MAP_SIZE):
                sx0, sx1 = round(x * self.zoom), round((x + 1) * self.zoom)
                for y in range(MAP_SIZE):
                    sy0, sy1 = round(y * self.zoom), round((y + 1) * self.zoom)
                    cell = self.terrain[(x, y)]
                    tile_surface = self.terrain_tile_surface(
                        cell.kind, cell.variation,
                        (sx1 - sx0, sy1 - sy0), detailed=detailed,
                    )
                    world.blit(tile_surface, (sx0, sy0))
            self._terrain_world_cache_surface = world
            self._terrain_world_cache_key = cache_key
        border = self.world_to_screen(0, 0)
        self.screen.blit(
            self._terrain_world_cache_surface,
            (round(border[0]), round(border[1])),
        )
        pygame.draw.rect(
            self.screen, (39, 54, 35),
            (border[0], border[1], MAP_SIZE * self.zoom, MAP_SIZE * self.zoom),
            max(2, int(self.zoom * .15)),
        )
        self.screen.set_clip(old_clip)

    def draw_checkpoints(self):
        owner_colors = {
            "green": GREEN, "red": RED,
            **NATIVE_FACTION_COLORS,
        }
        for checkpoint in self.checkpoints:
            if not self.is_display_visible(checkpoint.x, checkpoint.y):
                continue
            sx, sy = self.world_to_screen(checkpoint.x, checkpoint.y)
            size = max(
                18,
                round(self.zoom * 2.2 * checkpoint.profile.render_scale),
            )
            center = (round(sx), round(sy))
            pygame.draw.circle(self.screen, (39, 34, 28), center, size, max(2, size // 7))
            pygame.draw.circle(
                self.screen, owner_colors[checkpoint.owner], center,
                max(4, size - max(2, size // 7)),
            )
            if checkpoint.native_faction == "dwarf":
                tower = pygame.Rect(0, 0, size * 1.05, size * 1.2)
                tower.center = center
                pygame.draw.rect(self.screen, (89, 91, 87), tower)
                for offset in (-.34, 0, .34):
                    battlement = pygame.Rect(0, 0, size * .22, size * .25)
                    battlement.midbottom = (center[0] + size * offset, tower.top + size * .12)
                    pygame.draw.rect(self.screen, (164, 162, 147), battlement)
                pygame.draw.rect(
                    self.screen, (43, 39, 34),
                    (center[0] - size * .15, center[1], size * .3, size * .55),
                    border_top_left_radius=max(1, size // 7),
                    border_top_right_radius=max(1, size // 7),
                )
            elif checkpoint.native_faction == "elf":
                trunk = pygame.Rect(center[0] - size * .12, center[1] - size * .05, size * .24, size * .75)
                pygame.draw.rect(self.screen, (92, 64, 39), trunk)
                pygame.draw.circle(self.screen, (34, 96, 54), (center[0], center[1] - size * .2), round(size * .72))
                pygame.draw.circle(self.screen, (79, 157, 91), (center[0] - size * .2, center[1] - size * .4), round(size * .36))
            elif checkpoint.native_faction == "orc":
                pygame.draw.line(
                    self.screen, (74, 49, 31),
                    (center[0], center[1] + size * .65),
                    (center[0], center[1] - size * .65), max(3, size // 5),
                )
                pygame.draw.polygon(self.screen, (218, 204, 160), [
                    (center[0], center[1] - size * .72),
                    (center[0] - size * .62, center[1] - size * .28),
                    (center[0] - size * .18, center[1] - size * .08),
                ])
                pygame.draw.polygon(self.screen, (218, 204, 160), [
                    (center[0], center[1] - size * .72),
                    (center[0] + size * .62, center[1] - size * .28),
                    (center[0] + size * .18, center[1] - size * .08),
                ])
            elif checkpoint.native_faction == "demon":
                pygame.draw.polygon(self.screen, (55, 25, 24), [
                    (center[0] - size * .62, center[1] + size * .58),
                    (center[0] - size * .45, center[1] - size * .36),
                    (center[0] - size * .18, center[1] - size * .70),
                    (center[0], center[1] - size * .26),
                    (center[0] + size * .18, center[1] - size * .70),
                    (center[0] + size * .45, center[1] - size * .36),
                    (center[0] + size * .62, center[1] + size * .58),
                ])
                pygame.draw.circle(
                    self.screen, (244, 107, 40), center, round(size * .25)
                )
                pygame.draw.circle(
                    self.screen, (255, 198, 66), center, round(size * .11)
                )
            else:  # frost_giant
                pygame.draw.polygon(self.screen, (183, 229, 242), [
                    (center[0] - size * .62, center[1] + size * .56),
                    (center[0] - size * .52, center[1] - size * .18),
                    (center[0] - size * .28, center[1] - size * .72),
                    (center[0], center[1] - size * .38),
                    (center[0] + size * .28, center[1] - size * .72),
                    (center[0] + size * .52, center[1] - size * .18),
                    (center[0] + size * .62, center[1] + size * .56),
                ])
                pygame.draw.polygon(self.screen, (79, 133, 174), [
                    (center[0] - size * .22, center[1] + size * .56),
                    (center[0], center[1] - size * .25),
                    (center[0] + size * .22, center[1] + size * .56),
                ])
            if checkpoint.capturing_team:
                progress = checkpoint.capture_progress / CHECKPOINT_CAPTURE_SECONDS
                pygame.draw.arc(
                    self.screen,
                    owner_colors[checkpoint.capturing_team],
                    pygame.Rect(center[0] - size - 4, center[1] - size - 4, (size + 4) * 2, (size + 4) * 2),
                    -math.pi / 2, -math.pi / 2 + math.tau * progress,
                    max(2, size // 6),
                )
            if 0 <= sx < self.screen.get_width() and 0 <= sy < self.screen.get_height() - HUD_H:
                owner_name = {
                    "green": "VERDANT", "red": "CRIMSON",
                    **NATIVE_FACTION_LABELS,
                }[checkpoint.owner]
                if checkpoint.contested:
                    status = "CONTESTED"
                elif checkpoint.capturing_team:
                    amount = round(
                        checkpoint.capture_progress / CHECKPOINT_CAPTURE_SECONDS * 100
                    )
                    status = f"CAPTURING {amount}%"
                elif checkpoint.owner in ("green", "red"):
                    income = int(checkpoint.profile.income)
                    status = (
                        f"+{income} ACTIVE"
                        if checkpoint.income_active
                        else f"+{income} SUPPRESSED"
                    )
                else:
                    status = "NATIVE HOLD"
                label = self.small.render(
                    f"{owner_name} • {status}", True, CREAM
                )
                label_rect = label.get_rect(
                    midbottom=(round(sx), round(sy - size - 8))
                ).inflate(12, 7)
                pygame.draw.rect(
                    self.screen, (28, 27, 24), label_rect, border_radius=5
                )
                pygame.draw.rect(
                    self.screen, owner_colors[checkpoint.owner], label_rect,
                    2, border_radius=5,
                )
                self.screen.blit(label, label.get_rect(center=label_rect.center))

    def draw_checkpoint_edge_markers(self):
        """Point toward discovered holds outside the current battlefield view."""
        if not self.level.has_checkpoints:
            return
        owner_colors = {
            "green": GREEN, "red": RED,
            **NATIVE_FACTION_COLORS,
        }
        w, h = self.screen.get_size()
        view = pygame.Rect(18, CHECKPOINT_OBJECTIVE_BAR_HEIGHT + 14, w - 36,
                           h - HUD_H - CHECKPOINT_OBJECTIVE_BAR_HEIGHT - 30)
        screen_center = (w / 2, (view.top + view.bottom) / 2)
        for checkpoint in self.checkpoints:
            if self.fog_of_war_enabled and not checkpoint.discovered:
                continue
            sx, sy = self.world_to_screen(checkpoint.x, checkpoint.y)
            if view.collidepoint(sx, sy):
                continue
            dx, dy = sx - screen_center[0], sy - screen_center[1]
            if abs(dx) + abs(dy) <= 1e-9:
                continue
            scale = min(
                (view.right - screen_center[0]) / dx if dx > 0 else
                (view.left - screen_center[0]) / dx if dx < 0 else math.inf,
                (view.bottom - screen_center[1]) / dy if dy > 0 else
                (view.top - screen_center[1]) / dy if dy < 0 else math.inf,
            )
            marker = (
                round(screen_center[0] + dx * scale),
                round(screen_center[1] + dy * scale),
            )
            length = math.hypot(dx, dy)
            ux, uy = dx / length, dy / length
            px, py = -uy, ux
            points = [
                (marker[0] + ux * 10, marker[1] + uy * 10),
                (marker[0] - ux * 7 + px * 7, marker[1] - uy * 7 + py * 7),
                (marker[0] - ux * 7 - px * 7, marker[1] - uy * 7 - py * 7),
            ]
            pygame.draw.polygon(self.screen, (28, 27, 24), points)
            pygame.draw.polygon(
                self.screen, owner_colors[checkpoint.owner], points, 3
            )
            initial = self.small.render(
                checkpoint.native_faction[0].upper(), True, CREAM
            )
            initial_rect = initial.get_rect(center=(
                round(marker[0] - ux * 15), round(marker[1] - uy * 15)
            ))
            self.screen.blit(initial, initial_rect)

    def terrain_tile_surface(self, kind, variation, size, detailed=None):
        """Return a cached, deterministic primitive tile for one terrain cell."""
        if kind not in TERRAIN_KINDS or type(variation) is not int or not 0 <= variation <= 3:
            raise ValueError("Invalid terrain tile kind or variation")
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        if detailed is None:
            detailed = min(width, height) >= TERRAIN_DETAIL_MIN_ZOOM
        key = (kind, variation, width, height, detailed)
        cached = self._terrain_tile_cache.get(key)
        if cached is not None:
            return cached
        surface = pygame.Surface((width, height))
        base = TERRAIN_METADATA[kind]["base_color"]
        tone = (-3, -1, 1, 3)[variation]
        surface.fill(tuple(clamp(channel + tone, 0, 255) for channel in base))
        if detailed:
            self._draw_terrain_detail(surface, kind, variation)
        self._terrain_tile_cache[key] = surface
        return surface

    @staticmethod
    def _draw_terrain_detail(surface, kind, variation):
        """Draw one of exactly four code-native detail arrangements."""
        w, h = surface.get_size()
        point = lambda x, y: (round(w * x), round(h * y))
        line_width = max(1, round(min(w, h) * .07))
        if kind == "plains":
            grass = (48, 101, 49)
            centers = (((.28, .70),), ((.70, .66),), ((.30, .35), (.72, .72)), ((.62, .38),))
            for cx, cy in centers[variation]:
                root = point(cx, cy)
                pygame.draw.line(surface, grass, root, point(cx - .08, cy - .25), line_width)
                pygame.draw.line(surface, grass, root, point(cx + .09, cy - .20), line_width)
            if variation in (1, 3):
                flower = (239, 205, 112) if variation == 1 else (226, 219, 190)
                pygame.draw.circle(surface, flower, point(.30 if variation == 1 else .75, .30 if variation == 1 else .70), max(1, round(min(w, h) * .07)))
        elif kind == "forest":
            layouts = (
                ((.35, .40, .25), (.67, .62, .24)),
                ((.30, .67, .23), (.57, .35, .27), (.76, .68, .19)),
                ((.27, .35, .20), (.52, .61, .28), (.77, .31, .19)),
                ((.38, .50, .29), (.70, .42, .22), (.70, .73, .17)),
            )
            for cx, cy, radius in layouts[variation]:
                r = max(2, round(min(w, h) * radius))
                pygame.draw.ellipse(surface, (31, 55, 34), (round(w * (cx - .08)), round(h * (cy + radius * .55)), max(2, round(w * .16)), max(2, round(h * .16))))
                pygame.draw.circle(surface, (38, 105, 54), point(cx, cy), r)
                pygame.draw.circle(surface, (55, 125, 65), point(cx - .06, cy - .07), max(1, round(r * .55)))
        elif kind == "path":
            pass
        else:  # mountain
            layouts = (
                ((.18, .78), (.50, .18), (.82, .78)),
                ((.10, .75), (.40, .30), (.58, .58), (.72, .18), (.92, .75)),
                ((.08, .80), (.35, .31), (.49, .59), (.67, .14), (.94, .80)),
                ((.08, .76), (.36, .22), (.54, .54), (.72, .29), (.94, .76)),
            )
            points = [point(x, y) for x, y in layouts[variation]]
            pygame.draw.polygon(surface, (76, 77, 73), points)
            peak_index = min(range(len(points)), key=lambda index: points[index][1])
            peak = points[peak_index]
            pygame.draw.polygon(surface, (124, 121, 111), [peak, points[-1], point(.54, .72)])
            pygame.draw.lines(surface, (166, 166, 153), False, [point(.42, .40), peak, point(.57, .40)], max(1, line_width - 1))

    def draw_cracks(self, rect, ratio, seed):
        if ratio > .78:
            return
        random.seed(seed)
        stages = 1 if ratio > .5 else 2 if ratio > .25 else 3
        cx, cy = rect.center
        for branch in range(stages * 3):
            angle = random.random() * math.tau
            length = rect.width * (.18 + .09 * stages) * random.uniform(.7, 1.1)
            ex, ey = cx + math.cos(angle) * length, cy + math.sin(angle) * length
            pygame.draw.line(self.screen, (38, 31, 27), (cx, cy), (ex, ey), max(1, rect.width // 13))
            if stages > 1:
                bx, by = (cx + ex) / 2, (cy + ey) / 2
                pygame.draw.line(self.screen, (38, 31, 27), (bx, by), (bx + math.cos(angle + 1) * length * .35, by + math.sin(angle + 1) * length * .35), max(1, rect.width // 16))

    def draw_unit(self, u, screen_position=None, render_size=None):
        if screen_position is None:
            if u.team != "green" and not self.is_display_visible(u.x, u.y):
                return
            sx, sy = self.world_to_screen(u.x, u.y)
        else:
            sx, sy = screen_position
        size = (
            max(MIN_UNIT_RENDER_SIZE, int(self.zoom * UNIT_RENDER_SCALES[u.kind]))
            if render_size is None
            else render_size
        )
        rect = pygame.Rect(0, 0, size, size)
        rect.center = (round(sx), round(sy))
        color = {
            "green": GREEN,
            "red": RED,
            "dwarf": (126, 113, 85),
            "elf": (46, 142, 113),
            "orc": (119, 102, 43),
            "demon": NATIVE_FACTION_COLORS["demon"],
            "frost_giant": NATIVE_FACTION_COLORS["frost_giant"],
        }.get(u.team, RED)
        if u.flash > 0: color = CREAM
        if u.selected:
            pygame.draw.circle(self.screen, GOLD, rect.center, int(size * .68), max(1, size // 9))
        pygame.draw.rect(self.screen, (32, 31, 28), rect.inflate(2, 2), border_radius=max(2, size // 4))
        pygame.draw.rect(self.screen, color, rect, border_radius=max(2, size // 4))
        if u.kind == "swordsman":
            # Match the archer's simple equipment-emblem treatment: pale
            # weapon, brown fittings, and the team-colored tile beneath.
            blade_start = (
                rect.left + size * .34,
                rect.bottom - size * .3,
            )
            blade_end = (
                rect.right - size * .14,
                rect.top + size * .14,
            )
            pygame.draw.line(
                self.screen,
                (55, 51, 45),
                blade_start,
                blade_end,
                max(3, size // 5),
            )
            pygame.draw.line(
                self.screen,
                (225, 223, 202),
                blade_start,
                blade_end,
                max(2, size // 8),
            )
            pygame.draw.polygon(
                self.screen,
                (225, 220, 196),
                [
                    blade_end,
                    (blade_end[0] - size * .17, blade_end[1] + size * .05),
                    (blade_end[0] - size * .05, blade_end[1] + size * .17),
                ],
            )
            pygame.draw.line(
                self.screen, (109, 67, 35),
                (blade_start[0] - size * .1, blade_start[1] - size * .1),
                (blade_start[0] + size * .1, blade_start[1] + size * .1),
                max(2, size // 9),
            )
            pygame.draw.line(
                self.screen, (92, 65, 39), blade_start,
                (rect.left + size * .22, rect.bottom - size * .18),
                max(2, size // 8),
            )
        elif u.kind == "king":
            # A broad three-point crown stays legible even at the minimum
            # footprint; the inset team tile remains visible around it.
            outline = [
                (rect.left + size * .16, rect.top + size * .30),
                (rect.left + size * .23, rect.bottom - size * .18),
                (rect.right - size * .23, rect.bottom - size * .18),
                (rect.right - size * .16, rect.top + size * .30),
                (rect.right - size * .35, rect.top + size * .47),
                (rect.centerx, rect.top + size * .13),
                (rect.left + size * .35, rect.top + size * .47),
            ]
            pygame.draw.polygon(self.screen, (72, 53, 24), outline)
            crown = [
                (rect.left + size * .22, rect.top + size * .33),
                (rect.left + size * .28, rect.bottom - size * .24),
                (rect.right - size * .28, rect.bottom - size * .24),
                (rect.right - size * .22, rect.top + size * .33),
                (rect.right - size * .37, rect.top + size * .49),
                (rect.centerx, rect.top + size * .20),
                (rect.left + size * .37, rect.top + size * .49),
            ]
            pygame.draw.polygon(self.screen, GOLD, crown)
            pygame.draw.line(
                self.screen, (255, 225, 122),
                (rect.left + size * .29, rect.bottom - size * .31),
                (rect.right - size * .29, rect.bottom - size * .31),
                max(1, size // 10),
            )
        elif u.kind == "knight":
            # Angular, eight-sided steel great helm with a dark eye slit and
            # a team-color opening.
            helm = [
                (rect.left + size * .32, rect.top + size * .15),
                (rect.right - size * .32, rect.top + size * .15),
                (rect.right - size * .20, rect.top + size * .27),
                (rect.right - size * .20, rect.bottom - size * .27),
                (rect.right - size * .32, rect.bottom - size * .15),
                (rect.left + size * .32, rect.bottom - size * .15),
                (rect.left + size * .20, rect.bottom - size * .27),
                (rect.left + size * .20, rect.top + size * .27),
            ]
            pygame.draw.polygon(self.screen, (54, 58, 59), helm)
            inset = max(1, size * .06)
            helm_face = [
                (rect.left + size * .32, rect.top + size * .15 + inset),
                (rect.right - size * .32, rect.top + size * .15 + inset),
                (rect.right - size * .20 - inset, rect.top + size * .27),
                (rect.right - size * .20 - inset, rect.bottom - size * .27),
                (rect.right - size * .32, rect.bottom - size * .15 - inset),
                (rect.left + size * .32, rect.bottom - size * .15 - inset),
                (rect.left + size * .20 + inset, rect.bottom - size * .27),
                (rect.left + size * .20 + inset, rect.top + size * .27),
            ]
            pygame.draw.polygon(self.screen, (184, 193, 191), helm_face)
            helm_bounds = pygame.Rect(
                rect.left + size * .20, rect.top + size * .15,
                size * .60, size * .70,
            )
            pygame.draw.arc(
                self.screen, (235, 239, 226), helm_bounds.inflate(-2, -2),
                math.pi, math.tau, max(1, size // 10),
            )
            slit_y = rect.top + size * .49
            pygame.draw.line(
                self.screen, (41, 43, 42),
                (rect.left + size * .25, slit_y),
                (rect.right - size * .25, slit_y),
                max(2, size // 8),
            )
            pygame.draw.line(
                self.screen, color,
                (rect.centerx, slit_y),
                (rect.centerx, rect.bottom - size * .17),
                max(2, size // 9),
            )
        elif u.kind == "dwarf_guard":
            pygame.draw.circle(self.screen, (190, 191, 180), rect.center, round(size * .36))
            pygame.draw.line(self.screen, (80, 55, 34), (rect.left + size * .25, rect.bottom - size * .18), (rect.right - size * .22, rect.top + size * .18), max(2, size // 8))
            pygame.draw.polygon(self.screen, (222, 224, 213), [
                (rect.right - size * .12, rect.top + size * .1),
                (rect.right - size * .42, rect.top + size * .15),
                (rect.right - size * .18, rect.top + size * .42),
            ])
        elif u.kind == "dwarf_arbalist":
            pygame.draw.line(self.screen, (79, 52, 30), (rect.left + size * .15, rect.centery), (rect.right - size * .12, rect.centery), max(2, size // 8))
            pygame.draw.arc(self.screen, (214, 216, 205), rect.inflate(-size * .2, -size * .35), 0, math.pi, max(2, size // 8))
            pygame.draw.line(self.screen, (234, 226, 194), (rect.centerx, rect.top + size * .2), (rect.centerx, rect.bottom - size * .2), max(1, size // 12))
        elif u.kind == "elf_bladedancer":
            pygame.draw.arc(self.screen, (238, 224, 158), rect.inflate(-size * .2, -size * .12), -math.pi * .65, math.pi * .65, max(2, size // 7))
            pygame.draw.arc(self.screen, (224, 238, 209), rect.inflate(-size * .38, -size * .05), math.pi * .35, math.pi * 1.65, max(2, size // 9))
        elif u.kind == "elf_ranger":
            bow = rect.inflate(-size * .35, -size * .08)
            pygame.draw.arc(self.screen, (206, 170, 79), bow, -math.pi / 2, math.pi / 2, max(2, size // 8))
            pygame.draw.line(self.screen, CREAM, (bow.centerx, bow.top), (bow.centerx, bow.bottom), max(1, size // 12))
            pygame.draw.polygon(self.screen, (223, 237, 207), [(rect.right - size * .12, rect.centery), (rect.right - size * .3, rect.centery - size * .1), (rect.right - size * .3, rect.centery + size * .1)])
        elif u.kind == "orc_cleaver":
            pygame.draw.line(self.screen, (71, 48, 29), (rect.left + size * .22, rect.bottom - size * .15), (rect.right - size * .3, rect.top + size * .28), max(3, size // 7))
            pygame.draw.polygon(self.screen, (191, 191, 176), [
                (rect.right - size * .38, rect.top + size * .12),
                (rect.right - size * .08, rect.top + size * .2),
                (rect.right - size * .22, rect.top + size * .5),
                (rect.right - size * .48, rect.top + size * .4),
            ])
        elif u.kind == "orc_spear_thrower":
            pygame.draw.line(self.screen, (91, 59, 31), (rect.left + size * .16, rect.bottom - size * .16), (rect.right - size * .18, rect.top + size * .18), max(2, size // 9))
            pygame.draw.polygon(self.screen, (220, 216, 190), [
                (rect.right - size * .08, rect.top + size * .08),
                (rect.right - size * .36, rect.top + size * .16),
                (rect.right - size * .2, rect.top + size * .34),
            ])
        elif u.kind == "demon_reaver":
            pygame.draw.polygon(self.screen, (64, 28, 24), [
                (rect.left + size * .12, rect.top + size * .28),
                (rect.left + size * .34, rect.top + size * .08),
                (rect.centerx, rect.top + size * .34),
                (rect.right - size * .34, rect.top + size * .08),
                (rect.right - size * .12, rect.top + size * .28),
                (rect.right - size * .28, rect.bottom - size * .12),
                (rect.left + size * .28, rect.bottom - size * .12),
            ])
            pygame.draw.line(
                self.screen, (255, 143, 48),
                (rect.left + size * .2, rect.bottom - size * .18),
                (rect.right - size * .12, rect.top + size * .18),
                max(3, size // 7),
            )
        elif u.kind == "infernal_warlock":
            pygame.draw.circle(
                self.screen, (255, 119, 35), rect.center, round(size * .28)
            )
            pygame.draw.circle(
                self.screen, (255, 218, 90), rect.center, round(size * .12)
            )
            pygame.draw.arc(
                self.screen, (64, 25, 23), rect.inflate(-size * .15, -size * .15),
                math.pi, math.tau, max(2, size // 8),
            )
        elif u.kind == "frost_colossus":
            pygame.draw.polygon(self.screen, (205, 238, 244), [
                (rect.centerx, rect.top + size * .06),
                (rect.right - size * .13, rect.top + size * .38),
                (rect.right - size * .25, rect.bottom - size * .08),
                (rect.left + size * .25, rect.bottom - size * .08),
                (rect.left + size * .13, rect.top + size * .38),
            ])
            pygame.draw.line(
                self.screen, (65, 111, 152),
                (rect.left + size * .22, rect.centery),
                (rect.right - size * .22, rect.centery), max(3, size // 7),
            )
        elif u.kind == "ice_hurler":
            pygame.draw.polygon(self.screen, (220, 248, 250), [
                (rect.centerx, rect.top + size * .06),
                (rect.right - size * .12, rect.centery),
                (rect.centerx, rect.bottom - size * .06),
                (rect.left + size * .12, rect.centery),
            ])
            pygame.draw.polygon(self.screen, (74, 132, 180), [
                (rect.centerx, rect.top + size * .2),
                (rect.right - size * .28, rect.centery),
                (rect.centerx, rect.bottom - size * .2),
                (rect.left + size * .28, rect.centery),
            ])
        if u.kind == "archer":
            arc = pygame.Rect(rect.left + size * .15, rect.top + size * .12, size * .62, size * .76)
            pygame.draw.arc(self.screen, (109, 67, 35), arc, -math.pi / 2, math.pi / 2, max(2, size // 8))
            pygame.draw.line(self.screen, CREAM, (arc.centerx, arc.top), (arc.centerx, arc.bottom), max(1, size // 12))
            pygame.draw.line(
                self.screen,
                (225, 223, 202),
                (rect.left + size * .24, rect.centery),
                (rect.right - size * .14, rect.centery),
                max(1, size // 12),
            )
            pygame.draw.polygon(
                self.screen,
                (225, 223, 202),
                [
                    (rect.right - size * .08, rect.centery),
                    (rect.right - size * .23, rect.centery - size * .11),
                    (rect.right - size * .23, rect.centery + size * .11),
                ],
            )
        elif u.kind == "shield":
            rim = [
                (rect.centerx, rect.top + size * .1),
                (rect.right - size * .15, rect.top + size * .25),
                (rect.right - size * .22, rect.bottom - size * .22),
                (rect.centerx, rect.bottom - size * .08),
                (rect.left + size * .22, rect.bottom - size * .22),
                (rect.left + size * .15, rect.top + size * .25),
            ]
            pygame.draw.polygon(self.screen, (45, 43, 39), rim)
            face = [
                (rect.centerx, rect.top + size * .17),
                (rect.right - size * .23, rect.top + size * .3),
                (rect.right - size * .29, rect.bottom - size * .28),
                (rect.centerx, rect.bottom - size * .16),
                (rect.left + size * .29, rect.bottom - size * .28),
                (rect.left + size * .23, rect.top + size * .3),
            ]
            pygame.draw.polygon(self.screen, (225, 223, 202), face)
            pygame.draw.line(
                self.screen, (109, 67, 35),
                (rect.centerx, rect.top + size * .22),
                (rect.centerx, rect.bottom - size * .23),
                max(2, size // 9),
            )
            pygame.draw.line(
                self.screen, (109, 67, 35),
                (rect.left + size * .3, rect.centery - size * .04),
                (rect.right - size * .3, rect.centery - size * .04),
                max(2, size // 10),
            )
        self.draw_cracks(rect, u.health / u.max_health, u.uid)

    def draw_effects(self):
        for x1, y1, x2, y2, life, team in self.arrows:
            t = 1 - life / .22
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            sx, sy = self.world_to_screen(x, y)
            projectile_color = {
                "demon": (255, 114, 35),
                "frost_giant": (191, 239, 250),
            }.get(team, GOLD)
            pygame.draw.circle(
                self.screen, projectile_color, (int(sx), int(sy)),
                max(2, int(self.zoom * .13)),
            )
        for x, y, life, team in self.particles:
            sx, sy = self.world_to_screen(x, y)
            radius = max(2, int(self.zoom * (1 - life / .25) * .4))
            pygame.draw.circle(self.screen, CREAM, (int(sx), int(sy)), radius, 1)
        for slash in self.king_slashes:
            if slash.team == "red" and not self.is_display_visible(slash.x, slash.y):
                continue
            progress = 1 - slash.life / KING_SLASH_LIFETIME
            reach = .35 + progress * .45
            cx = slash.x + slash.dx * reach
            cy = slash.y + slash.dy * reach
            px, py = -slash.dy, slash.dx
            half_width = .34
            start = self.world_to_screen(
                cx - slash.dx * .30 + px * half_width,
                cy - slash.dy * .30 + py * half_width,
            )
            end = self.world_to_screen(
                cx + slash.dx * .30 - px * half_width,
                cy + slash.dy * .30 - py * half_width,
            )
            pygame.draw.line(
                self.screen, (255, 225, 122), start, end,
                max(2, round(self.zoom * .12)),
            )

    def draw_fog(self):
        if self.level_number == 1 or not self.fog_of_war_enabled:
            return
        w, h = self.screen.get_size(); view_h = h - HUD_H
        left, top = self.screen_to_world((0, 0)); right, bottom = self.screen_to_world((w, view_h))
        x0, x1 = math.floor(left) - 2, math.ceil(right) + 3
        y0, y1 = math.floor(top) - 2, math.ceil(bottom) + 3
        cols, rows = x1 - x0, y1 - y0
        cache_key = (x0, x1, y0, y1, self.zoom, self._fog_revision)
        if cache_key != self._fog_cache_key:
            mask = pygame.Surface((cols, rows), pygame.SRCALPHA)
            for ix, x in enumerate(range(x0, x1)):
                for iy, y in enumerate(range(y0, y1)):
                    if not (0 <= x < MAP_SIZE and 0 <= y < MAP_SIZE):
                        alpha = FOG_UNEXPLORED_ALPHA
                    elif (x, y) in self.visible:
                        alpha = FOG_VISIBLE_ALPHA
                    elif (x, y) in self.explored:
                        alpha = FOG_EXPLORED_ALPHA
                    else:
                        alpha = FOG_UNEXPLORED_ALPHA
                    color = FOG_COLOR
                    if alpha == FOG_UNEXPLORED_ALPHA:
                        cloud = (
                            math.sin((x + y * .61) * FOG_TEXTURE_SCALE)
                            + math.sin((x * .37 - y) * FOG_TEXTURE_SCALE * .73)
                            + math.sin((x * .19 + y * .43) * FOG_TEXTURE_SCALE * .41)
                        ) / 3
                        tone = round(cloud * FOG_TEXTURE_STRENGTH)
                        color = tuple(channel + tone for channel in FOG_COLOR)
                    mask.set_at((ix, iy), (*color, alpha))
            self._fog_cache_surface = pygame.transform.smoothscale(
                mask,
                (max(1, round(cols * self.zoom)), max(1, round(rows * self.zoom))),
            )
            self._fog_cache_key = cache_key
        destination = self.world_to_screen(x0 - .5, y0 - .5)
        self.screen.blit(self._fog_cache_surface, (round(destination[0]), round(destination[1])))

    def draw_checkpoint_objective_bar(self):
        """Draw the persistent, clickable hold overview."""
        self.checkpoint_bar_entries = []
        if not self.level.has_checkpoints:
            return
        owner_colors = {
            "green": GREEN, "red": RED,
            **NATIVE_FACTION_COLORS,
        }
        w = self.screen.get_width()
        gap = 8
        count = len(self.checkpoints)
        total_width = min(w - 28, 1200 if count > 3 else 900)
        card_width = (total_width - gap * (count - 1)) // count
        start_x = (w - (card_width * count + gap * (count - 1))) // 2
        for index, checkpoint in enumerate(self.checkpoints):
            rect = pygame.Rect(
                start_x + index * (card_width + gap), 8, card_width, 50
            )
            self.checkpoint_bar_entries.append((rect, checkpoint))
            pygame.draw.rect(self.screen, (28, 27, 24), rect, border_radius=8)
            if self.fog_of_war_enabled and not checkpoint.discovered:
                pygame.draw.rect(
                    self.screen, (95, 86, 68), rect, 2, border_radius=8
                )
                unknown = self.title.render("?", True, (165, 155, 132))
                self.screen.blit(unknown, unknown.get_rect(center=rect.center))
                continue
            pygame.draw.rect(
                self.screen, owner_colors[checkpoint.owner], rect, 2,
                border_radius=8,
            )
            icon_center = rect.x + 24, rect.centery
            pygame.draw.circle(
                self.screen, owner_colors[checkpoint.owner], icon_center, 14
            )
            pygame.draw.circle(self.screen, CREAM, icon_center, 14, 2)
            icon = self.font.render(
                checkpoint.native_faction[0].upper(), True, CREAM
            )
            self.screen.blit(icon, icon.get_rect(center=icon_center))
            owner = {
                "green": "VERDANT", "red": "CRIMSON",
                **NATIVE_FACTION_LABELS,
            }[checkpoint.owner]
            native_label = NATIVE_FACTION_LABELS[checkpoint.native_faction]
            if count > 3:
                native_label = (
                    "FROST"
                    if checkpoint.native_faction == "frost_giant"
                    else native_label
                )
                owner = "NATIVE" if checkpoint.owner == checkpoint.native_faction else owner
                title_text = f"{native_label} • {owner}"
            else:
                title_text = f"{native_label} HOLD • {owner}"
            title = self.small.render(
                title_text, True, CREAM,
            )
            self.screen.blit(title, (rect.x + 45, rect.y + 8))
            if checkpoint.contested:
                income = int(checkpoint.profile.income)
                status = (
                    f"CONTESTED • +{income} OFF"
                    if count > 3 else f"CONTESTED • +{income} SUPPRESSED"
                )
            elif checkpoint.capturing_team:
                faction = {
                    "green": "VERDANT", "red": "CRIMSON",
                    **NATIVE_FACTION_LABELS,
                }[checkpoint.capturing_team]
                percent = round(
                    checkpoint.capture_progress / CHECKPOINT_CAPTURE_SECONDS * 100
                )
                status = (
                    f"{faction} • {percent}%"
                    if count > 3 else f"{faction} CAPTURING • {percent}%"
                )
            elif checkpoint.owner in ("green", "red"):
                income = int(checkpoint.profile.income)
                status = (
                    f"+{income} GOLD ACTIVE"
                    if checkpoint.income_active
                    else f"+{income} GOLD SUPPRESSED"
                )
            else:
                status = (
                    "DEFENDERS • NO INCOME"
                    if count > 3 else "NATIVE DEFENDERS • NO INCOME"
                )
            status_color = (
                (222, 119, 91) if checkpoint.under_attack else
                (183, 207, 158) if checkpoint.income_active else
                (190, 180, 153)
            )
            status_label = self.small.render(status, True, status_color)
            self.screen.blit(status_label, (rect.x + 45, rect.y + 27))
            if checkpoint.capturing_team:
                progress = clamp(
                    checkpoint.capture_progress / CHECKPOINT_CAPTURE_SECONDS,
                    0.0, 1.0,
                )
                pygame.draw.rect(
                    self.screen, (52, 48, 41),
                    (rect.x + 45, rect.bottom - 5, rect.width - 54, 3),
                )
                pygame.draw.rect(
                    self.screen,
                    owner_colors[checkpoint.capturing_team],
                    (rect.x + 45, rect.bottom - 5,
                     round((rect.width - 54) * progress), 3),
                )

    def draw_hud(self):
        w, h = self.screen.get_size(); top = h - HUD_H
        pygame.draw.rect(self.screen, (34, 31, 27), (0, top, w, HUD_H))
        pygame.draw.line(self.screen, (129, 102, 62), (0, top), (w, top), 3)
        pygame.draw.rect(
            self.screen, GOLD, (21, top + 23, 26, 12), border_radius=2
        )
        pygame.draw.rect(
            self.screen, (255, 225, 122), (23, top + 25, 22, 3),
            border_radius=1,
        )
        self.screen.blit(self.font.render(f"{int(self.essence):,} gold", True, CREAM), (55, top + 18))
        income = self.income_rate("green")
        income_text = f"+{int(income)} gold each second"
        if self.level.has_checkpoints:
            owned = sum(checkpoint.owner == "green" for checkpoint in self.checkpoints)
            income_text = (
                f"+{int(income)} gold/sec  •  "
                f"{owned}/{len(self.checkpoints)} holds"
            )
        self.screen.blit(self.small.render(income_text, True, (172, 158, 128)), (55, top + 44))
        labels = {
            "swordsman": "Hire Swordsman",
            "archer": "Hire Archer",
            "shield": "Hire Shield",
        }
        self.hud_buttons = []
        for index, kind in enumerate(self.level.player_units):
            cost = UNIT_COSTS[kind]
            text = labels[kind]
            button = Button(
                (245 + index * 195, top + 16, 180, 62), text,
                f"{cost} gold",
            )
            button.draw(
                self.screen, pygame.mouse.get_pos(), self.button_font,
                self.button_cost_font, self.essence >= cost,
            )
            self.hud_buttons.append((button, kind))
        counts = {
            kind: sum(u.team == "green" and u.kind == kind for u in self.units)
            for kind in UNIT_KINDS
        }
        selected = sum(
            u.selected and u.is_player_commandable for u in self.units
        )
        count_labels = {
            "swordsman": ("sword", "swords"),
            "archer": ("archer", "archers"),
            "shield": ("shield", "shields"),
        }
        army_parts = []
        for kind in self.level.player_units:
            singular, plural = count_labels[kind]
            army_parts.append(
                f"{counts[kind]} {singular if counts[kind] == 1 else plural}"
            )
        info = f"Army: {'  •  '.join(army_parts)}  •  {selected} selected"
        info_label = self.small.render(info, True, (190, 180, 153))
        info_rect = info_label.get_rect(topleft=(245, top + 84))
        self.screen.blit(info_label, info_rect)
        selection_hints = {
            "swordsman": "[1] Swords",
            "archer": "[2] Archers",
            "shield": "[4] Shields",
        }
        controls = "   ".join(
            selection_hints[kind] for kind in self.level.player_units
        ) + "   [3] All army   •   Right-click: order"
        label = self.small.render(controls, True, (165, 155, 132))
        controls_rect = label.get_rect(topleft=(245, top + 104))
        self.screen.blit(label, controls_rect)
        # Keep the objective status clear of the recruitment cards when the
        # window is narrow.  The resource column has a reserved lower row that
        # remains readable without compressing the three purchase buttons.
        king_rect = (
            pygame.Rect(55, top + 68, 170, 54)
            if w < 1045
            else pygame.Rect(w - 210, top + 12, 190, 58)
        )
        self.screen.blit(
            self.small.render("VERDANT KING", True, (165, 198, 165)),
            (king_rect.x, king_rect.y + 6),
        )
        self.screen.blit(
            self.font.render(
                f"{int(self.objective_health('green'))}"
                f" / {UNIT_STATS['king']['max_health']}",
                True,
                CREAM,
            ),
            (king_rect.x, king_rect.y + 27),
        )
        self.hud_layout = {
            "buttons": [button.rect.copy() for button, _ in self.hud_buttons],
            "army": info_rect,
            "controls": controls_rect,
            "king": king_rect,
            "hud": pygame.Rect(0, top, w, HUD_H),
        }
        self.hud_text = {
            "army": info,
            "controls": controls,
            "king": (
                f"Verdant King: {int(self.objective_health('green'))}"
                f" / {UNIT_STATS['king']['max_health']}"
            ),
        }

    def draw_menu(self):
        w, h = self.screen.get_size()
        self.screen.fill((27, 42, 31))
        # Decorative banner and sword field.
        for i in range(70):
            random.seed(i)
            x, y = random.randrange(w), random.randrange(h)
            pygame.draw.circle(self.screen, (42, 67, 45), (x, y), random.randrange(1, 4))
        banner = pygame.Rect(w // 2 - 310, 100, 620, 310)
        pygame.draw.rect(self.screen, (45, 40, 33), banner, border_radius=20)
        pygame.draw.rect(self.screen, (150, 119, 67), banner, 4, border_radius=20)
        title = self.big.render("VERDANT CROWN", True, CREAM)
        self.screen.blit(title, (w // 2 - title.get_width() // 2, 155))
        sub = self.title.render("A MEDIEVAL RTS", True, GOLD)
        self.screen.blit(sub, (w // 2 - sub.get_width() // 2, 225))
        lore = self.font.render(
            "Raise an army. Defy the Crimson King.",
            True,
            (191, 181, 152),
        )
        self.screen.blit(lore, (w // 2 - lore.get_width() // 2, 294))
        self.play_btn.rect.center = (w // 2, h // 2 + 92)
        self.play_btn.draw(self.screen, pygame.mouse.get_pos(), self.button_font, self.button_cost_font)
        self.editor_btn.rect.center = (w // 2, h // 2 + 152)
        self.editor_btn.draw(
            self.screen, pygame.mouse.get_pos(), self.button_font,
            self.button_cost_font,
        )
        self.fog_btn.rect.center = (w // 2, h // 2 + 204)
        self.fog_btn.text = (
            "Fog of War: ON" if self.fog_of_war_enabled else "Fog of War: OFF"
        )
        self.fog_btn.draw(
            self.screen, pygame.mouse.get_pos(), self.button_font,
            self.button_cost_font,
        )
        hint = self.small.render("Mouse + keyboard  •  Press Play to begin", True, (200, 190, 160))
        self.screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 80))

    def _draw_level_select_legacy(self):
        # Kept as a compatibility shim for callers from older test harnesses;
        # the former card-grid implementation has no runtime path.
        return self.draw_level_select()
        w, h = self.screen.get_size()
        self.screen.fill((24, 37, 28))
        heading = self.title.render("BEGIN THE CONQUEST", True, CREAM)
        self.screen.blit(heading, heading.get_rect(center=(w // 2, 92)))
        gap = max(24, round(w * .015))
        side_margin = max(80, round(w * .08))
        card_w = max(320, (w - side_margin * 2 - gap * 2) // 3)
        card_h = max(440, h - 260)
        start_x = w // 2 - (card_w * 3 + gap * 2) // 2
        self.level_buttons = []
        difficulties = {1: "EASY", 2: "MEDIUM", 3: "CONQUERER"}
        unit_names = {
            "swordsman": "Swordsmen",
            "archer": "Archers",
            "shield": "Shields",
        }

        for index, config in enumerate(LEVELS.values()):
            card = pygame.Rect(start_x + index * (card_w + gap), 145, card_w, card_h)
            hover = card.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(
                self.screen, (53, 48, 39) if hover else (43, 41, 35),
                card, border_radius=16,
            )
            pygame.draw.rect(
                self.screen, GOLD if hover else (132, 106, 65),
                card, 3, border_radius=16,
            )
            number = self.big.render(str(config.number), True, GOLD)
            self.screen.blit(
                number,
                number.get_rect(
                    center=(card.centerx, card.y + round(card_h * .10))
                ),
            )
            display_names = {
                1: "Survive the Ambush!",
                2: "Punish Your Enemies!",
                3: "Kill the Crimson King!",
            }
            display_name = display_names[config.number]
            name = self.font.render(display_name, True, CREAM)
            self.screen.blit(
                name,
                name.get_rect(
                    center=(card.centerx, card.y + round(card_h * .19))
                ),
            )
            story_descriptions = {
                1: (
                    "Crimson raiders strike at dawn. Hold the line and "
                    "survive."
                ),
                2: (
                    "March down the long path. Break every force sent "
                    "against you."
                ),
                3: (
                    "Storm the Crimson stronghold and end the tyrant's "
                    "reign."
                ),
            }
            words = story_descriptions[config.number].split()
            lines, line = [], ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if self.small.size(candidate)[0] > card_w - 70:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for line_index, text in enumerate(lines):
                description = self.small.render(text, True, (190, 180, 153))
                self.screen.blit(
                    description,
                    description.get_rect(
                        center=(
                            card.centerx,
                            card.y + round(card_h * .27) + line_index * 22,
                        )
                    ),
                )
            divider_color = (118, 94, 58)
            divider_inset = max(30, round(card_w * .10))
            first_divider_y = card.y + round(card_h * .36)
            pygame.draw.line(
                self.screen,
                divider_color,
                (card.x + divider_inset, first_divider_y),
                (card.right - divider_inset, first_divider_y),
                1,
            )

            # A compact battlefield preview fills the card without turning
            # descriptive copy into a wall of text.
            preview = pygame.Rect(
                card.x + divider_inset,
                card.y + round(card_h * .40),
                card_w - divider_inset * 2,
                round(card_h * .25),
            )
            pygame.draw.rect(
                self.screen, (52, 72, 48), preview, border_radius=8
            )
            pygame.draw.rect(
                self.screen, (101, 88, 59), preview, 2, border_radius=8
            )
            formations = {
                1: (
                    [
                        ("king", .18, .50),
                        ("swordsman", .36, .32),
                        ("swordsman", .36, .68),
                    ],
                    [
                        ("swordsman", .58, .24),
                        ("swordsman", .58, .50),
                        ("swordsman", .58, .76),
                        ("archer", .70, .50),
                    ],
                ),
                2: (
                    [
                        ("king", .10, .50),
                        ("archer", .23, .34),
                        ("archer", .23, .66),
                        ("swordsman", .38, .18),
                        ("swordsman", .38, .40),
                        ("swordsman", .38, .60),
                        ("swordsman", .38, .82),
                    ],
                    [
                        ("swordsman", .54, .26),
                        ("swordsman", .54, .50),
                        ("swordsman", .54, .74),
                        ("swordsman", .63, .26),
                        ("swordsman", .63, .50),
                        ("swordsman", .63, .74),
                        ("swordsman", .72, .26),
                        ("swordsman", .72, .50),
                        ("swordsman", .72, .74),
                        ("king", .86, .50),
                    ],
                ),
                3: (
                    [
                        ("king", .09, .50),
                        ("archer", .18, .35),
                        ("archer", .18, .65),
                        ("swordsman", .27, .23),
                        ("swordsman", .27, .41),
                        ("swordsman", .27, .59),
                        ("swordsman", .27, .77),
                        ("shield", .36, .30),
                        ("shield", .36, .50),
                        ("shield", .36, .70),
                    ],
                    [
                        ("shield", .59, .22),
                        ("shield", .59, .40),
                        ("shield", .59, .60),
                        ("shield", .59, .78),
                        ("swordsman", .68, .18),
                        ("swordsman", .68, .34),
                        ("swordsman", .68, .50),
                        ("swordsman", .68, .66),
                        ("swordsman", .68, .82),
                        ("swordsman", .76, .18),
                        ("swordsman", .76, .34),
                        ("swordsman", .76, .50),
                        ("swordsman", .76, .66),
                        ("swordsman", .76, .82),
                        ("archer", .84, .18),
                        ("archer", .84, .34),
                        ("archer", .84, .50),
                        ("archer", .84, .66),
                        ("archer", .84, .82),
                        ("king", .93, .50),
                    ],
                ),
            }
            green_formation, red_formation = formations[config.number]
            preview_unit_size = max(
                11, round(preview.height * (.12 if config.number == 3 else .20))
            )
            for team, formation in (
                ("green", green_formation),
                ("red", red_formation),
            ):
                for kind, x_ratio, y_ratio in formation:
                    preview_unit = Unit(kind, team, 0, 0)
                    size = round(
                        preview_unit_size
                        * UNIT_RENDER_SCALES[kind]
                        / UNIT_RENDER_SCALES["swordsman"]
                    )
                    self.draw_unit(
                        preview_unit,
                        (
                            preview.x + round(preview.width * x_ratio),
                            preview.y + round(preview.height * y_ratio),
                        ),
                        size,
                    )

            second_divider_y = card.y + round(card_h * .69)
            pygame.draw.line(
                self.screen,
                divider_color,
                (card.x + divider_inset, second_divider_y),
                (card.right - divider_inset, second_divider_y),
                1,
            )
            difficulty = self.small.render(
                f"DIFFICULTY  •  {difficulties[config.number]}",
                True,
                GOLD,
            )
            self.screen.blit(
                difficulty,
                difficulty.get_rect(
                    center=(card.centerx, card.y + round(card_h * .75))
                ),
            )
            available = "  •  ".join(
                unit_names[kind] for kind in config.player_units
            )
            unit_lines = [available]
            units_center_y = card.y + round(card_h * .81)
            for unit_line_index, unit_line in enumerate(unit_lines):
                units = self.small.render(
                    unit_line, True, (190, 180, 153)
                )
                self.screen.blit(
                    units,
                    units.get_rect(
                        center=(
                            card.centerx,
                            units_center_y
                            + (unit_line_index - (len(unit_lines) - 1) / 2)
                            * 19,
                        )
                    ),
                )
            button = Button(
                (card.x + 45, card.bottom - 60, card_w - 90, 44),
                f"Play Level {config.number}",
            )
            button.draw(
                self.screen, pygame.mouse.get_pos(),
                self.button_font, self.button_cost_font,
            )
            self.level_buttons.append((button, config.number))
        back = self.small.render("Esc to return", True, (190, 180, 153))
        self.screen.blit(back, back.get_rect(center=(w // 2, h - 58)))

    def _wrapped_lines(self, text, font, width):
        lines, current = [], ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _draw_selector_preview(self, rect, preview_type):
        pygame.draw.rect(self.screen, (48, 72, 48), rect, border_radius=10)
        pygame.draw.rect(self.screen, (120, 98, 61), rect, 2, border_radius=10)
        path_color = (171, 139, 82)
        r = max(6, min(rect.width, rect.height) // 24)
        if preview_type == "ambush":
            center = rect.center
            pygame.draw.circle(self.screen, GREEN, center, r * 2)
            pygame.draw.circle(self.screen, CREAM, center, r * 2, 2)
            for angle in (-2.6, -2.0, -1.2, -.45, .45, 1.2, 2.0, 2.6):
                point = (
                    round(center[0] + math.cos(angle) * rect.width * .35),
                    round(center[1] + math.sin(angle) * rect.height * .35),
                )
                pygame.draw.circle(self.screen, RED, point, r)
                pygame.draw.line(self.screen, RED, point, center, 2)
        elif preview_type == "road_waves":
            points = [
                (rect.x + 12, rect.bottom - rect.height * .25),
                (rect.x + rect.width * .30, rect.y + rect.height * .35),
                (rect.x + rect.width * .62, rect.y + rect.height * .62),
                (rect.right - 12, rect.y + rect.height * .28),
            ]
            pygame.draw.lines(self.screen, path_color, False, points, r * 2)
            pygame.draw.circle(self.screen, GREEN, points[0], r * 2)
            pygame.draw.circle(self.screen, RED, points[-1], r * 2)
            for amount in (.38, .56, .72):
                x = round(rect.x + rect.width * amount)
                y = round(rect.y + rect.height * (.30 + amount * .35))
                for offset in (-r * 2, 0, r * 2):
                    pygame.draw.circle(self.screen, RED, (x, y + offset), r)
        elif preview_type == "full_siege":
            road_y = rect.centery
            pygame.draw.line(
                self.screen, path_color,
                (rect.x + 12, road_y), (rect.right - 12, road_y), r * 2,
            )
            wall_x = rect.x + round(rect.width * .72)
            pygame.draw.rect(
                self.screen, (91, 86, 76),
                (wall_x, rect.y + rect.height * .18, rect.width * .20,
                 rect.height * .64),
            )
            for row in range(3):
                for column in range(5):
                    pygame.draw.circle(
                        self.screen, GREEN,
                        (rect.x + round(rect.width * (.18 + column * .08)),
                         rect.y + round(rect.height * (.32 + row * .18))), r,
                    )
            pygame.draw.circle(self.screen, RED, (wall_x + r * 3, road_y), r * 2)
        else:
            road_y = rect.centery
            pygame.draw.line(
                self.screen, path_color,
                (rect.x + 12, road_y), (rect.right - 12, road_y), r * 2,
            )
            holds = (
                (.32, .24, (132, 119, 92)),
                (.51, .76, (70, 151, 125)),
                (.69, .26, (132, 112, 48)),
            )
            for x_ratio, y_ratio, color in holds:
                point = (
                    rect.x + round(rect.width * x_ratio),
                    rect.y + round(rect.height * y_ratio),
                )
                pygame.draw.line(
                    self.screen, path_color,
                    (point[0], road_y), point, max(3, r // 2),
                )
                pygame.draw.circle(self.screen, color, point, r * 2)
                pygame.draw.circle(self.screen, CREAM, point, r * 2, 2)
            pygame.draw.circle(self.screen, GREEN, (rect.x + 20, road_y), r * 2)
            pygame.draw.circle(self.screen, RED, (rect.right - 20, road_y), r * 2)

    def _campaign_location_points(self, map_rect):
        """Return the five mission locations along the campaign road."""
        ratios = {
            1: (.16, .74),
            2: (.35, .62),
            3: (.52, .48),
            4: (.69, .35),
            5: (.84, .19),
        }
        return {
            number: (
                map_rect.x + round(map_rect.width * x_ratio),
                map_rect.y + round(map_rect.height * y_ratio),
            )
            for number, (x_ratio, y_ratio) in ratios.items()
        }

    def _draw_campaign_map(self, map_rect):
        """Draw the shared campaign world and its clickable mission markers."""
        mouse = pygame.mouse.get_pos()
        pygame.draw.rect(self.screen, (25, 54, 61), map_rect, border_radius=18)
        pygame.draw.rect(
            self.screen, (105, 91, 61), map_rect, 3, border_radius=18
        )

        for row in range(7):
            y = map_rect.y + round(map_rect.height * (.12 + row * .13))
            offset = (row % 2) * 18
            for x in range(map_rect.x + 18 + offset, map_rect.right - 26, 68):
                pygame.draw.arc(
                    self.screen, (42, 78, 82),
                    (x, y, 28, 10), 0, math.pi, 1,
                )

        def point(x_ratio, y_ratio):
            return (
                map_rect.x + round(map_rect.width * x_ratio),
                map_rect.y + round(map_rect.height * y_ratio),
            )

        coast_ratios = (
            (.07, .75), (.10, .51), (.06, .33), (.18, .16),
            (.39, .08), (.55, .13), (.74, .07), (.91, .19),
            (.94, .38), (.88, .54), (.93, .70), (.78, .87),
            (.57, .91), (.41, .85), (.23, .91),
        )
        coast = [point(*ratio) for ratio in coast_ratios]
        shadow = [(x + 7, y + 9) for x, y in coast]
        pygame.draw.polygon(self.screen, (20, 39, 39), shadow)
        pygame.draw.polygon(self.screen, (81, 110, 63), coast)

        # Broad regions make each stop feel like a distinct destination.
        pygame.draw.polygon(self.screen, (100, 131, 72), [
            point(.08, .70), point(.17, .50), point(.39, .53),
            point(.47, .85), point(.23, .90),
        ])
        pygame.draw.polygon(self.screen, (51, 98, 60), [
            point(.12, .48), point(.17, .18), point(.43, .09),
            point(.50, .51), point(.35, .60),
        ])
        pygame.draw.polygon(self.screen, (126, 112, 72), [
            point(.48, .50), point(.56, .14), point(.77, .08),
            point(.84, .43), point(.71, .55),
        ])
        pygame.draw.polygon(self.screen, (76, 109, 72), [
            point(.47, .53), point(.72, .50), point(.89, .70),
            point(.77, .86), point(.48, .86),
        ])
        pygame.draw.polygon(self.screen, (115, 126, 111), [
            point(.73, .08), point(.91, .18), point(.92, .39),
            point(.83, .42),
        ])
        pygame.draw.lines(self.screen, (173, 151, 91), True, coast, 3)

        river = [
            point(.45, .12), point(.48, .27), point(.45, .42),
            point(.51, .56), point(.48, .73), point(.55, .88),
        ]
        pygame.draw.lines(self.screen, (42, 82, 94), False, river, 6)
        pygame.draw.lines(self.screen, (84, 134, 141), False, river, 2)
        for x_ratio, y_ratio in ((.21, .28), (.27, .34), (.31, .24), (.40, .30)):
            x, y = point(x_ratio, y_ratio)
            pygame.draw.circle(self.screen, (35, 76, 48), (x, y), 8)
            pygame.draw.circle(self.screen, (58, 111, 61), (x - 4, y - 5), 6)
        for x_ratio, y_ratio in ((.61, .19), (.68, .15), (.75, .22), (.79, .14)):
            x, y = point(x_ratio, y_ratio)
            pygame.draw.polygon(self.screen, (74, 73, 67), [
                (x - 11, y + 9), (x, y - 11), (x + 11, y + 9),
            ])
            pygame.draw.polygon(self.screen, (196, 195, 174), [
                (x - 3, y - 4), (x, y - 11), (x + 4, y - 3),
            ])

        locations = self._campaign_location_points(map_rect)
        route = [locations[number] for number in sorted(LEVELS)]
        pygame.draw.lines(self.screen, (66, 53, 38), False, route, 11)
        pygame.draw.lines(self.screen, (211, 171, 87), False, route, 6)
        for start, end in zip(route, route[1:]):
            for step in (.25, .50, .75):
                dash = (
                    round(start[0] + (end[0] - start[0]) * step),
                    round(start[1] + (end[1] - start[1]) * step),
                )
                pygame.draw.circle(self.screen, (247, 218, 140), dash, 2)

        location_names = {
            1: "BRIARWATCH",
            2: "KINGSROAD",
            3: "CROWNHEART",
            4: "THREE HOLDS",
            5: "FROSTFALL",
        }
        self.level_location_rects = []
        for number, center in locations.items():
            hit_rect = pygame.Rect(0, 0, 56, 56)
            hit_rect.center = center
            self.level_location_rects.append((hit_rect, number))
            selected = number == self.selected_level_page
            hovered = hit_rect.collidepoint(mouse)
            if selected:
                pygame.draw.circle(self.screen, (36, 32, 26), center, 24)
                pygame.draw.circle(self.screen, GOLD, center, 23, 4)
            elif hovered:
                pygame.draw.circle(self.screen, CREAM, center, 20, 3)
            pygame.draw.circle(
                self.screen,
                GREEN if selected else (105, 56, 46),
                center, 17,
            )
            pygame.draw.circle(self.screen, (36, 31, 26), center, 17, 3)
            number_surface = self.font.render(str(number), True, CREAM)
            self.screen.blit(
                number_surface, number_surface.get_rect(center=center)
            )
            name = self.small.render(location_names[number], True, CREAM)
            name_rect = name.get_rect(
                center=(center[0], center[1] + (34 if number != 5 else -34))
            ).inflate(12, 5)
            pygame.draw.rect(
                self.screen, (31, 34, 28), name_rect, border_radius=6
            )
            self.screen.blit(name, name.get_rect(center=name_rect.center))

    def draw_level_select(self):
        """Draw every level as a location on one shared campaign map."""
        w, h = self.screen.get_size()
        config = LEVELS[self.selected_level_page]
        self.screen.fill((24, 37, 28))
        heading = self.title.render("THE VERDANT CAMPAIGN", True, CREAM)
        self.screen.blit(heading, heading.get_rect(midleft=(28, 34)))
        if w >= 1000:
            campaign_hint = self.small.render(
                "Choose a location along the road to conquest", True,
                (190, 180, 153),
            )
            self.screen.blit(
                campaign_hint, campaign_hint.get_rect(midright=(w - 28, 34))
            )

        content = pygame.Rect(28, 64, w - 56, h - 110)
        compact = w < 900
        if compact:
            map_rect = pygame.Rect(
                content.x, content.y, content.width,
                max(250, round(content.height * .52)),
            )
            details = pygame.Rect(
                content.x, map_rect.bottom + 12, content.width,
                content.bottom - map_rect.bottom - 12,
            )
        else:
            map_width = round(content.width * .66)
            map_rect = pygame.Rect(
                content.x, content.y, map_width, content.height
            )
            details = pygame.Rect(
                map_rect.right + 16, content.y,
                content.right - map_rect.right - 16, content.height,
            )
        self._draw_campaign_map(map_rect)

        pygame.draw.rect(self.screen, (43, 41, 35), details, border_radius=16)
        pygame.draw.rect(
            self.screen, (132, 106, 65), details, 3, border_radius=16
        )
        inset = 22
        detail_width = details.width - inset * 2
        y = details.y + 18
        level_label = self.small.render(
            f"LOCATION {config.number}  •  {config.name}", True, GOLD
        )
        self.screen.blit(level_label, (details.x + inset, y))
        y += 25
        title_font = self.title if details.width >= 360 else self.font
        title = title_font.render(config.display_title, True, CREAM)
        title_rect = title.get_rect(topleft=(details.x + inset, y))
        self.screen.blit(title, title_rect)
        y = title_rect.bottom + 14
        pygame.draw.line(
            self.screen, (118, 94, 58),
            (details.x + inset, y), (details.right - inset, y), 1,
        )
        y += 14
        difficulty = self.font.render(
            f"DIFFICULTY  •  {config.difficulty_label}", True, GOLD
        )
        self.screen.blit(difficulty, (details.x + inset, y))
        y += 30
        story_text = config.story_text or config.description
        for line in self._wrapped_lines(story_text, self.small, detail_width):
            self.screen.blit(
                self.small.render(line, True, (202, 192, 163)),
                (details.x + inset, y),
            )
            y += 20
        y += 9
        unit_names = {
            "swordsman": "Swordsmen", "archer": "Archers",
            "shield": "Shields",
        }
        unit_roster = "  •  ".join(
            unit_names[kind] for kind in config.player_units
        )
        facts = (
            (f"MAP  {config.map_size} × {config.map_size}  •  "
             f"UNITS  {unit_roster}"),
        ) if compact else (
            f"MAP  {config.map_size} × {config.map_size}",
            f"UNITS  {unit_roster}",
            "OBJECTIVE  " + config.description,
        )
        for fact in facts:
            for line in self._wrapped_lines(fact, self.small, detail_width):
                self.screen.blit(
                    self.small.render(line, True, (190, 180, 153)),
                    (details.x + inset, y),
                )
                y += 19
            y += 3
        tag_x, tag_y = details.x + inset, y + 5
        for tag in (() if compact else config.mechanic_tags):
            tag_surface = self.small.render(tag.upper(), True, (235, 211, 145))
            tag_rect = tag_surface.get_rect().inflate(16, 8)
            if tag_x + tag_rect.width > details.right - inset:
                tag_x, tag_y = details.x + inset, tag_y + 28
            tag_rect.topleft = tag_x, tag_y
            pygame.draw.rect(
                self.screen, (74, 63, 45), tag_rect, border_radius=8
            )
            pygame.draw.rect(
                self.screen, (126, 100, 61), tag_rect, 1, border_radius=8
            )
            self.screen.blit(
                tag_surface, tag_surface.get_rect(center=tag_rect.center)
            )
            tag_x = tag_rect.right + 8
        self.difficulty_buttons = []
        if config.number >= 3:
            mode = Button(
                (details.x + inset, details.bottom - 108, detail_width, 38),
                (
                    "Opponent AI  •  HARD"
                    if self.campaign_hard_mode
                    else "Opponent AI  •  STANDARD"
                ),
            )
            mode.draw(
                self.screen, pygame.mouse.get_pos(), self.button_font,
                self.button_cost_font,
            )
            self.difficulty_buttons = [(mode, "campaign")]
        play = Button(
            (details.x + inset, details.bottom - 60, detail_width, 42),
            f"Deploy to Location {config.number}",
        )
        play.draw(
            self.screen, pygame.mouse.get_pos(), self.button_font,
            self.button_cost_font,
        )
        self.level_buttons = [(play, config.number)]
        self.level_nav_buttons = []
        self.level_dot_rects = []
        hint = self.small.render(
            (
                "Click a location  •  1–5 choose  •  H difficulty  •  "
                "Enter deploy  •  Esc return"
            ),
            True, (190, 180, 153),
        )
        self.screen.blit(hint, hint.get_rect(center=(w // 2, h - 20)))
        if config.number == 5:
            self.selector_layout = {
                "title": title_rect.copy(), "play": play.rect.copy(), "page": 5,
            }
        else:
            self.selector_layout = {
                "map": map_rect, "details": details,
                "play": play.rect.copy(), "page": config.number,
            }

    def _draw_editor_button(self, rect, text, action, active=False, enabled=True):
        button = Button(rect, text)
        button.draw(
            self.screen, pygame.mouse.get_pos(), self.small,
            self.button_cost_font, enabled,
        )
        if active:
            pygame.draw.rect(self.screen, GOLD, button.rect, 3, border_radius=7)
        self.editor_buttons.append((button, action))
        return button

    def _draw_editor_slider(
        self, x, y, width, label, value, key,
        minimum=0, maximum=100, step=1, values=None, display=None,
    ):
        """Draw and register one draggable randomizer control."""
        value_label = str(value) if display is None else display
        self.screen.blit(self.small.render(label, True, GOLD), (x, y))
        rendered_value = self.small.render(value_label, True, CREAM)
        self.screen.blit(
            rendered_value,
            rendered_value.get_rect(topright=(x + width, y)),
        )
        track = pygame.Rect(x + 7, y + 27, width - 14, 6)
        pygame.draw.rect(self.screen, (73, 68, 55), track, border_radius=3)
        if values is not None:
            index = values.index(value)
            progress = index / max(1, len(values) - 1)
        else:
            progress = (value - minimum) / max(1, maximum - minimum)
        fill = track.copy()
        fill.width = round(track.width * progress)
        pygame.draw.rect(self.screen, GOLD, fill, border_radius=3)
        knob = (track.x + round(track.width * progress), track.centery)
        pygame.draw.circle(self.screen, (35, 31, 25), knob, 8)
        pygame.draw.circle(self.screen, CREAM, knob, 6)
        self.editor_sliders.append({
            "rect": track.inflate(18, 22),
            "track": track,
            "key": key,
            "minimum": minimum,
            "maximum": maximum,
            "step": step,
            "values": values,
        })

    def _set_editor_slider_from_x(self, slider, x):
        """Apply a slider position to its randomizer setting."""
        track = slider["track"]
        progress = clamp((x - track.x) / track.width, 0.0, 1.0)
        values = slider["values"]
        if values is not None:
            index = round(progress * (len(values) - 1))
            value = values[index]
        else:
            raw = slider["minimum"] + progress * (
                slider["maximum"] - slider["minimum"]
            )
            step = slider["step"]
            value = round(raw / step) * step
            value = int(clamp(value, slider["minimum"], slider["maximum"]))
        self._set_editor_randomizer_value(slider["key"], value)

    def _set_editor_randomizer_value(self, key, value):
        """Store one randomizer option, resizing the live draft when needed."""
        if key == "map_size":
            if value != self.editor_draft.map_size:
                self.editor_draft.resize(value)
                self.editor_revision += 1
        elif key == "hold_count":
            self.editor_random_hold_count = value
        elif key == "hold_connections":
            self.editor_random_hold_connections = value
        elif key == "path_amount":
            self.editor_random_path_amount = value
        elif key.startswith("terrain:"):
            terrain_kind = key.split(":", 1)[1]
            other_total = sum(
                weight
                for kind, weight in self.editor_random_terrain_weights.items()
                if kind != terrain_kind
            )
            if value == 0 and other_total == 0:
                self.editor_notice = "At least one terrain ratio must stay above zero"
                return
            self.editor_random_terrain_weights[terrain_kind] = value
        self.editor_notice = "Randomizer settings updated — click Randomize"

    def _draw_editor_map(self, rect):
        draft = self.editor_draft
        cache_key = (
            self.editor_revision, draft.map_size, rect.width, rect.height
        )
        if cache_key != self._editor_map_cache_key:
            overview = pygame.Surface((draft.map_size, draft.map_size))
            colors = {
                "plains": (91, 132, 65),
                "forest": (35, 77, 44),
                "mountain": (101, 101, 94),
                "path": (181, 145, 80),
            }
            for (x, y), cell in draft.terrain.items():
                overview.set_at((x, y), colors[cell.kind])
            self._editor_map_cache = pygame.transform.scale(
                overview, rect.size
            )
            self._editor_map_cache_key = cache_key
        self.screen.blit(self._editor_map_cache, rect)
        pygame.draw.rect(self.screen, (204, 177, 111), rect, 3)

        def overview_point(position):
            return (
                rect.x + round(position[0] / draft.map_size * rect.width),
                rect.y + round(position[1] / draft.map_size * rect.height),
            )

        for hold in draft.holds:
            center = overview_point((hold.x + .5, hold.y + .5))
            pygame.draw.circle(self.screen, (34, 30, 25), center, 9)
            pygame.draw.circle(self.screen, GOLD, center, 7, 2)
            pygame.draw.circle(self.screen, CREAM, center, 2)
        for position, color, letter in (
            (draft.green_start, GREEN, "V"),
            (draft.red_start, RED, "C"),
        ):
            center = overview_point(position)
            pygame.draw.circle(self.screen, (31, 28, 24), center, 13)
            pygame.draw.circle(self.screen, color, center, 11)
            marker = self.small.render(letter, True, CREAM)
            self.screen.blit(marker, marker.get_rect(center=center))

    def draw_level_editor(self):
        """Draw the custom battlefield editor and its contextual controls."""
        w, h = self.screen.get_size()
        self.screen.fill((22, 31, 26))
        self.editor_buttons = []
        self.editor_sliders = []
        self._draw_editor_button((20, 15, 88, 34), "Back", "back")
        title = self.title.render("LEVEL FORGE", True, CREAM)
        self.screen.blit(title, (126, 12))
        subtitle = self.small.render(
            "Paint the battlefield, place objectives, tune the battle, then play it.",
            True, (190, 180, 153),
        )
        self.screen.blit(subtitle, (390, 26))

        panel_w = int(clamp(round(w * .30), 350, 410))
        panel = pygame.Rect(w - panel_w - 18, 62, panel_w, h - 80)
        left = pygame.Rect(18, 62, panel.x - 32, h - 80)
        map_side = max(120, min(left.width - 24, left.height - 58))
        self.editor_canvas = left
        self.editor_map_rect = pygame.Rect(0, 0, map_side, map_side)
        self.editor_map_rect.centerx = left.centerx
        self.editor_map_rect.y = left.y + 30

        pygame.draw.rect(self.screen, (39, 43, 34), left, border_radius=14)
        pygame.draw.rect(self.screen, (111, 91, 58), left, 2, border_radius=14)
        map_label = self.small.render(
            f"CUSTOM OVERVIEW  •  {self.editor_draft.map_size} × "
            f"{self.editor_draft.map_size}  •  {len(self.editor_draft.holds)} holds",
            True, GOLD,
        )
        self.screen.blit(map_label, (left.x + 14, left.y + 8))
        self._draw_editor_map(self.editor_map_rect)
        tool_name = self.editor_tool.replace("_", " ").title()
        hint = self.small.render(
            f"Tool: {tool_name}  •  Drag to paint  •  Brush {self.editor_brush_size}",
            True, (196, 187, 158),
        )
        self.screen.blit(
            hint, hint.get_rect(center=(left.centerx, left.bottom - 15))
        )

        pygame.draw.rect(self.screen, (43, 41, 35), panel, border_radius=14)
        pygame.draw.rect(self.screen, (132, 106, 65), panel, 2, border_radius=14)
        inset, gap = 14, 7
        inner_x, inner_w = panel.x + inset, panel.width - inset * 2
        tab_y = panel.y + 14
        tabs = (
            ("PAINT", "paint"), ("RANDOM", "randomizer"),
            ("SETTINGS", "settings"), ("ARMIES", "armies"),
        )
        tab_w = (inner_w - gap * (len(tabs) - 1)) // len(tabs)
        for index, (label, tab) in enumerate(tabs):
            self._draw_editor_button(
                (inner_x + index * (tab_w + gap), tab_y, tab_w, 34),
                label, f"tab:{tab}", self.editor_tab == tab,
            )
        content_y = tab_y + 48
        if self.editor_tab == "paint":
            tools = (
                ("Plains", "plains"), ("Forest", "forest"),
                ("Mountain", "mountain"), ("Path / Road", "path"),
                ("Hold", "hold"), ("Verdant Start", "green_start"),
                ("Crimson Start", "red_start"),
            )
            tool_w = (inner_w - gap) // 2
            for index, (label, tool) in enumerate(tools):
                row, column = divmod(index, 2)
                self._draw_editor_button(
                    (inner_x + column * (tool_w + gap),
                     content_y + row * 42, tool_w, 35),
                    label, f"tool:{tool}", self.editor_tool == tool,
                )
            y = content_y + 4 * 42 + 7
            self.screen.blit(
                self.small.render("BRUSH SIZE", True, GOLD), (inner_x, y)
            )
            y += 24
            brush_w = (inner_w - gap * 2) // 3
            for index, size in enumerate((1, 3, 7)):
                self._draw_editor_button(
                    (inner_x + index * (brush_w + gap), y, brush_w, 34),
                    str(size), f"brush:{size}", self.editor_brush_size == size,
                )
            y += 52
            info = (
                "Terrain and paths use the selected brush. Holds toggle on "
                "click. Start markers set each king's keep."
            )
            for line in self._wrapped_lines(info, self.small, inner_w):
                self.screen.blit(
                    self.small.render(line, True, (188, 179, 151)),
                    (inner_x, y),
                )
                y += 19
        elif self.editor_tab == "randomizer":
            y = content_y
            slider_gap = 47
            randomizer_sliders = (
                (
                    "MAP SIZE", self.editor_draft.map_size, "map_size",
                    {"values": EDITOR_MAP_SIZES,
                     "display": f"{self.editor_draft.map_size} × {self.editor_draft.map_size}"},
                ),
                (
                    "HOLD NUMBER", self.editor_random_hold_count, "hold_count",
                    {"minimum": 0, "maximum": 12},
                ),
                (
                    "HOLDS CONNECTED TO PATH",
                    self.editor_random_hold_connections, "hold_connections",
                    {"step": 5,
                     "display": f"{self.editor_random_hold_connections}%"},
                ),
                (
                    "PATH AMOUNT", self.editor_random_path_amount, "path_amount",
                    {"step": 5, "display": f"{self.editor_random_path_amount}%"},
                ),
            )
            for label, value, key, options in randomizer_sliders:
                self._draw_editor_slider(
                    inner_x, y, inner_w, label, value, key, **options
                )
                y += slider_gap
            self.screen.blit(
                self.small.render("TERRAIN RATIO WEIGHTS", True, GOLD),
                (inner_x, y),
            )
            y += 23
            for label, terrain_kind in (
                ("Plains", "plains"), ("Forest", "forest"),
                ("Mountain", "mountain"),
            ):
                weight = self.editor_random_terrain_weights[terrain_kind]
                self._draw_editor_slider(
                    inner_x, y, inner_w, label.upper(), weight,
                    f"terrain:{terrain_kind}", step=5,
                )
                y += 42
        elif self.editor_tab == "settings":
            draft = self.editor_draft
            rows = (
                ("MAP SIZE", draft.map_size, "size"),
                ("VERDANT INCOME / SEC", int(draft.green_income), "income:green"),
                ("CRIMSON INCOME / SEC", int(draft.red_income), "income:red"),
            )
            y = content_y
            for label, value, action in rows:
                self.screen.blit(self.small.render(label, True, GOLD), (inner_x, y))
                y += 24
                self._draw_editor_button((inner_x, y, 54, 34), "−", f"{action}:-")
                value_surface = self.font.render(str(value), True, CREAM)
                self.screen.blit(
                    value_surface,
                    value_surface.get_rect(center=(inner_x + inner_w // 2, y + 17)),
                )
                self._draw_editor_button(
                    (inner_x + inner_w - 54, y, 54, 34), "+", f"{action}:+"
                )
                y += 57
            self.screen.blit(self.small.render("FOG OF WAR", True, GOLD), (inner_x, y))
            y += 25
            self._draw_editor_button(
                (inner_x, y, inner_w, 38),
                "Enabled" if draft.fog_of_war else "Disabled",
                "fog", draft.fog_of_war,
            )
            y += 54
            self.screen.blit(self.small.render("ENEMY AI", True, GOLD), (inner_x, y))
            y += 25
            self._draw_editor_button(
                (inner_x, y, inner_w, 38),
                "Hard" if draft.hard_mode else "Standard",
                "difficulty", draft.hard_mode,
            )
            y += 54
            info = (
                "Resizing preserves your design by scaling terrain, holds, "
                "and starting positions to the new battlefield."
            )
            for line in self._wrapped_lines(info, self.small, inner_w):
                self.screen.blit(
                    self.small.render(line, True, (188, 179, 151)),
                    (inner_x, y),
                )
                y += 19
        else:
            draft = self.editor_draft
            y = content_y
            self.screen.blit(self.small.render("AVAILABLE TO VERDANT", True, GOLD), (inner_x, y))
            y += 25
            unit_labels = {
                "swordsman": "Swords", "archer": "Archers", "shield": "Shields",
            }
            unit_w = (inner_w - gap * 2) // 3
            for index, kind in enumerate(UNIT_KINDS):
                self._draw_editor_button(
                    (inner_x + index * (unit_w + gap), y, unit_w, 35),
                    unit_labels[kind], f"available:{kind}",
                    kind in draft.available_units,
                )
            y += 53
            self.screen.blit(
                self.small.render("STARTING UNITS", True, GOLD), (inner_x, y)
            )
            y += 24
            label_w = 150
            for team, team_label, counts in (
                ("green", "VERDANT", draft.green_starting_counts),
                ("red", "CRIMSON", draft.red_starting_counts),
            ):
                team_color = GREEN if team == "green" else RED
                self.screen.blit(
                    self.small.render(team_label, True, team_color), (inner_x, y)
                )
                y += 22
                for kind in UNIT_KINDS:
                    self.screen.blit(
                        self.small.render(unit_labels[kind], True, (205, 195, 166)),
                        (inner_x + 5, y + 8),
                    )
                    self._draw_editor_button(
                        (inner_x + label_w, y, 38, 32), "−",
                        f"count:{team}:{kind}:-",
                    )
                    count_surface = self.font.render(str(counts[kind]), True, CREAM)
                    self.screen.blit(
                        count_surface,
                        count_surface.get_rect(center=(inner_x + label_w + 65, y + 16)),
                    )
                    self._draw_editor_button(
                        (inner_x + label_w + 92, y, 38, 32), "+",
                        f"count:{team}:{kind}:+",
                    )
                    y += 36
                y += 8

        bottom_y = panel.bottom - 48
        actions = (
            ("Randomize", "randomize"), ("Reset", "reset"),
            ("Save", "save"), ("Play", "play"),
        )
        action_w = (inner_w - gap * (len(actions) - 1)) // len(actions)
        for index, (label, action) in enumerate(actions):
            self._draw_editor_button(
                (inner_x + index * (action_w + gap), bottom_y, action_w, 34),
                label, action,
            )
        notice = self.small.render(self.editor_notice, True, (196, 187, 158))
        self.screen.blit(
            notice,
            notice.get_rect(bottomleft=(inner_x, bottom_y - 8)),
        )

    def _editor_cell_at(self, position):
        if not self.editor_map_rect.collidepoint(position):
            return None
        relative_x = (position[0] - self.editor_map_rect.x) / self.editor_map_rect.width
        relative_y = (position[1] - self.editor_map_rect.y) / self.editor_map_rect.height
        return (
            min(self.editor_draft.map_size - 1, int(relative_x * self.editor_draft.map_size)),
            min(self.editor_draft.map_size - 1, int(relative_y * self.editor_draft.map_size)),
        )

    def _apply_editor_tool(self, cell):
        if cell is None:
            return
        draft, tool = self.editor_draft, self.editor_tool
        x, y = cell
        changed = False
        if tool in TERRAIN_KINDS:
            radius = self.editor_brush_size // 2
            for paint_x in range(max(0, x - radius), min(draft.map_size, x + radius + 1)):
                for paint_y in range(max(0, y - radius), min(draft.map_size, y + radius + 1)):
                    old = draft.terrain[(paint_x, paint_y)]
                    draft.terrain[(paint_x, paint_y)] = TerrainCell(tool, old.variation)
                    changed = True
        elif tool == "hold":
            existing = next((hold for hold in draft.holds if (hold.x, hold.y) == cell), None)
            if existing:
                draft.holds.remove(existing)
                self.editor_notice = "Hold removed"
            elif len(draft.holds) < 12:
                draft.holds.append(EditorHold(x, y))
                self.editor_notice = "Hold placed"
            else:
                self.editor_notice = "Maximum of 12 holds reached"
                return
            changed = True
        elif tool in ("green_start", "red_start"):
            position = (
                clamp(x + .5, 2.5, draft.map_size - 2.5),
                clamp(y + .5, 2.5, draft.map_size - 2.5),
            )
            if tool == "green_start":
                draft.green_start = position
                self.editor_notice = "Verdant starting keep moved"
            else:
                draft.red_start = position
                self.editor_notice = "Crimson starting keep moved"
            changed = True
        if changed:
            self.editor_revision += 1

    def _handle_editor_action(self, action):
        draft = self.editor_draft
        if action == "back":
            self.state = "menu"
        elif action.startswith("tab:"):
            self.editor_tab = action.split(":", 1)[1]
        elif action.startswith("tool:"):
            self.editor_tool = action.split(":", 1)[1]
        elif action.startswith("brush:"):
            self.editor_brush_size = int(action.split(":", 1)[1])
        elif action.startswith("size:"):
            direction = -1 if action.endswith(":-") else 1
            index = EDITOR_MAP_SIZES.index(draft.map_size)
            new_index = int(clamp(index + direction, 0, len(EDITOR_MAP_SIZES) - 1))
            if new_index != index:
                draft.resize(EDITOR_MAP_SIZES[new_index])
                self.editor_revision += 1
                self.editor_notice = f"Map resized to {draft.map_size} × {draft.map_size}"
        elif action.startswith("income:"):
            _, team, change = action.split(":")
            attribute = "green_income" if team == "green" else "red_income"
            value = getattr(draft, attribute) + (-5 if change == "-" else 5)
            setattr(draft, attribute, float(clamp(value, 0, 100)))
        elif action == "fog":
            draft.fog_of_war = not draft.fog_of_war
            self.editor_notice = (
                "Fog of war enabled" if draft.fog_of_war else "Fog of war disabled"
            )
        elif action == "difficulty":
            draft.hard_mode = not draft.hard_mode
            self.editor_notice = (
                "Hard enemy AI enabled"
                if draft.hard_mode else "Standard enemy AI enabled"
            )
        elif action.startswith("available:"):
            kind = action.split(":", 1)[1]
            if kind in draft.available_units and len(draft.available_units) == 1:
                self.editor_notice = "At least one unit must stay available"
            elif kind in draft.available_units:
                draft.available_units.remove(kind)
            else:
                draft.available_units.add(kind)
        elif action.startswith("count:"):
            _, team, kind, change = action.split(":")
            counts = (
                draft.green_starting_counts
                if team == "green" else draft.red_starting_counts
            )
            counts[kind] = int(clamp(
                counts[kind] + (-1 if change == "-" else 1), 0, 30
            ))
        elif action == "randomize":
            self.editor_draft = make_random_editor_draft(
                draft,
                hold_count=self.editor_random_hold_count,
                hold_connection_ratio=(
                    self.editor_random_hold_connections / 100
                ),
                path_amount=self.editor_random_path_amount / 100,
                terrain_weights=self.editor_random_terrain_weights,
            )
            self.editor_revision += 1
            self.editor_notice = (
                f"Randomized {draft.map_size} × {draft.map_size} battlefield"
            )
        elif action == "reset":
            self.editor_draft = make_default_editor_draft()
            self.editor_revision += 1
            self.editor_notice = "Expanded 200 × 200 canvas restored"
        elif action == "save":
            try:
                CUSTOM_LEVEL_FILE.write_text(
                    json.dumps(draft.to_dict(), indent=2), encoding="utf-8"
                )
                self.editor_notice = "Custom level saved"
            except OSError:
                self.editor_notice = "Could not save custom level"
        elif action == "play":
            self.start_custom_level()
            self.state = "playing"
            self.update_visibility()

    def handle_level_editor_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.state = "menu"
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button, action in self.editor_buttons:
                if button.rect.collidepoint(event.pos):
                    self._handle_editor_action(action)
                    return
            for slider in self.editor_sliders:
                if slider["rect"].collidepoint(event.pos):
                    self.editor_slider_dragging = slider
                    self._set_editor_slider_from_x(slider, event.pos[0])
                    return
            cell = self._editor_cell_at(event.pos)
            if cell is not None:
                self._apply_editor_tool(cell)
                self.editor_dragging = self.editor_tool in TERRAIN_KINDS
        elif event.type == pygame.MOUSEMOTION and self.editor_dragging:
            if event.buttons[0]:
                self._apply_editor_tool(self._editor_cell_at(event.pos))
        elif event.type == pygame.MOUSEMOTION and self.editor_slider_dragging:
            if event.buttons[0]:
                self._set_editor_slider_from_x(
                    self.editor_slider_dragging, event.pos[0]
                )
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.editor_dragging = False
            self.editor_slider_dragging = None

    def handle_level_select_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.state = "menu"
                return
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                change = -1 if event.key == pygame.K_LEFT else 1
                self.selected_level_page = int(clamp(
                    self.selected_level_page + change, min(LEVELS), max(LEVELS)
                ))
                return
            if event.key in (
                pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5
            ):
                self.selected_level_page = event.key - pygame.K_0
                return
            if event.key == pygame.K_h and self.selected_level_page >= 3:
                self.campaign_hard_mode = not self.campaign_hard_mode
                return
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_level(self.selected_level_page)
                self.state = "playing"
                self.update_visibility()
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button, action in self.difficulty_buttons:
                if button.rect.collidepoint(event.pos) and action == "campaign":
                    self.campaign_hard_mode = not self.campaign_hard_mode
                    return
            for marker, number in self.level_location_rects:
                if marker.collidepoint(event.pos):
                    self.selected_level_page = number
                    return
            for button, number in self.level_buttons:
                if button.rect.collidepoint(event.pos):
                    self.start_level(number)
                    self.state = "playing"
                    self.update_visibility()
                    return

    def draw_game(self):
        self.draw_terrain()
        self.draw_checkpoints()
        for u in self.units: self.draw_unit(u)
        self.draw_effects(); self.draw_fog()
        self.draw_checkpoint_edge_markers()
        if self.drag_start and self.drag_now:
            rect = pygame.Rect(self.drag_start, (self.drag_now[0] - self.drag_start[0], self.drag_now[1] - self.drag_start[1])); rect.normalize()
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA); overlay.fill((102, 192, 112, 45)); self.screen.blit(overlay, rect)
            pygame.draw.rect(self.screen, (134, 211, 142), rect, 1)
        self.draw_hud()
        self.draw_checkpoint_objective_bar()
        if self.message_time > 0:
            label = self.font.render(self.message, True, CREAM)
            panel_padding = 10
            box = label.get_rect(
                midtop=(
                    self.screen.get_width() // 2,
                    CHECKPOINT_OBJECTIVE_BAR_HEIGHT + panel_padding
                    if self.level.has_checkpoints else panel_padding,
                )
            ).inflate(panel_padding * 2, panel_padding * 2)
            box.top = (
                CHECKPOINT_OBJECTIVE_BAR_HEIGHT + panel_padding
                if self.level.has_checkpoints else panel_padding
            )
            pygame.draw.rect(self.screen, (28, 27, 24), box, border_radius=8)
            self.screen.blit(label, label.get_rect(center=box.center))
        if self.winner:
            shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA); shade.fill((12, 14, 12, 190)); self.screen.blit(shade, (0, 0))
            color = GOLD if self.winner == "VICTORY" else (213, 91, 78)
            label = self.big.render(self.winner, True, color)
            self.screen.blit(label, label.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 25)))
            result = (
                (
                    "The enemy army has fallen"
                    if self.level_number == 1
                    else "The Crimson King has fallen"
                )
                if self.winner == "VICTORY"
                else "The Verdant King has fallen"
            )
            result_label = self.font.render(result, True, CREAM)
            self.screen.blit(
                result_label,
                result_label.get_rect(
                    center=(
                        self.screen.get_width() // 2,
                        self.screen.get_height() // 2 + 25,
                    )
                ),
            )
            sub = self.small.render("Press R to fight again  •  Esc for menu", True, CREAM)
            self.screen.blit(
                sub,
                sub.get_rect(
                    center=(
                        self.screen.get_width() // 2,
                        self.screen.get_height() // 2 + 60,
                    )
                ),
            )

    def draw_pause(self):
        shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        shade.fill((12, 14, 12, 190))
        self.screen.blit(shade, (0, 0))
        label = self.title.render("PAUSED", True, GOLD)
        self.screen.blit(
            label,
            label.get_rect(
                center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 66)
            ),
        )
        self.pause_fog_btn.rect.center = (
            self.screen.get_width() // 2, self.screen.get_height() // 2 + 2
        )
        self.pause_fog_btn.text = (
            "Fog of War: ON" if self.fog_of_war_enabled else "Fog of War: OFF"
        )
        self.pause_fog_btn.draw(
            self.screen, pygame.mouse.get_pos(), self.button_font,
            self.button_cost_font,
        )
        sub = self.font.render("Esc to resume  •  M for menu", True, CREAM)
        self.screen.blit(
            sub,
            sub.get_rect(
                center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 58)
            ),
        )

    def handle_menu_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.play_btn.rect.collidepoint(event.pos):
                self.state = "level_select"
            elif self.editor_btn.rect.collidepoint(event.pos):
                self.state = "level_editor"
            elif self.fog_btn.rect.collidepoint(event.pos):
                self.toggle_fog_of_war()
        elif event.type == pygame.KEYDOWN and event.key in (
            pygame.K_RETURN, pygame.K_SPACE
        ):
            self.state = "level_select"

    def handle_pause_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.pause_fog_btn.rect.collidepoint(event.pos):
                self.toggle_fog_of_war()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.state = "playing"
            elif event.key == pygame.K_m:
                self.state = "menu"

    def camera_input(self, dt):
        keys = pygame.key.get_pressed()
        speed = 25 * dt * (13 / self.zoom)
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        self.camera[0] += dx * speed
        self.camera[1] += dy * speed
        self.clamp_camera()

    def handle_game_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in SELECTION_SHORTCUTS:
                kind = SELECTION_SHORTCUTS[event.key]
                if kind is None or kind in self.level.player_units:
                    self.select_kind(kind)
            elif event.key == pygame.K_SPACE:
                green_king = self.team_king("green")
                if green_king is not None:
                    self.camera[:] = [green_king.x, green_king.y]
                    self.clamp_camera()
            elif event.key == pygame.K_r and self.winner: self.reset()
            elif event.key == pygame.K_ESCAPE:
                self.state = "menu" if self.winner else "paused"
        elif event.type == pygame.MOUSEWHEEL:
            if self.level_number == 1:
                return
            old_world = self.screen_to_world(pygame.mouse.get_pos())
            w, h = self.screen.get_size()
            fit_zoom = max(w / MAP_SIZE, (h - HUD_H) / MAP_SIZE)
            old_zoom = self.zoom
            self.zoom = clamp(self.zoom * (1.13 ** event.y), fit_zoom, 30)
            if self.zoom != old_zoom:
                self._terrain_tile_cache.clear()
            new_world = self.screen_to_world(pygame.mouse.get_pos())
            self.camera[0] += old_world[0] - new_world[0]; self.camera[1] += old_world[1] - new_world[1]
            self.clamp_camera()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                for rect, checkpoint in getattr(
                    self, "checkpoint_bar_entries", []
                ):
                    if rect.collidepoint(event.pos):
                        if checkpoint.discovered or not self.fog_of_war_enabled:
                            self.camera[:] = [checkpoint.x, checkpoint.y]
                            self.clamp_camera()
                        return
                for button, kind in getattr(self, "hud_buttons", []):
                    if button.rect.collidepoint(event.pos): self.recruit(kind); return
                if event.pos[1] < self.screen.get_height() - HUD_H:
                    self.drag_start = self.drag_now = event.pos
            elif event.button == 3 and event.pos[1] < self.screen.get_height() - HUD_H:
                self.issue_order(self.screen_to_world(event.pos))
        elif event.type == pygame.MOUSEMOTION and self.drag_start:
            self.drag_now = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag_start:
            rect = pygame.Rect(self.drag_start, (event.pos[0] - self.drag_start[0], event.pos[1] - self.drag_start[1])); rect.normalize()
            additive = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if not additive:
                for u in self.units: u.selected = False
            if rect.width < 6 and rect.height < 6:
                world = self.screen_to_world(event.pos)
                friends = [u for u in self.units if u.is_player_commandable]
                hit = min(friends, key=lambda u: dist((u.x, u.y), world), default=None)
                hit_radius = .9
                if hit:
                    hit_radius *= (
                        UNIT_RENDER_SCALES[hit.kind]
                        / UNIT_RENDER_SCALES["swordsman"]
                    )
                if hit and dist((hit.x, hit.y), world) < hit_radius:
                    hit.selected = True
            else:
                for u in self.units:
                    if u.is_player_commandable and rect.collidepoint(self.world_to_screen(u.x, u.y)): u.selected = True
            self.drag_start = self.drag_now = None

    def run(self):
        running = True
        while running:
            dt = min(.05, self.clock.tick(FPS) / 1000)
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                elif self.state == "menu":
                    self.handle_menu_event(event)
                elif self.state == "level_select":
                    self.handle_level_select_event(event)
                elif self.state == "level_editor":
                    self.handle_level_editor_event(event)
                elif self.state == "paused":
                    self.handle_pause_event(event)
                else: self.handle_game_event(event)
            if self.state == "playing":
                self.camera_input(dt); self.update(dt); self.draw_game()
            elif self.state == "paused":
                self.draw_game(); self.draw_pause()
            elif self.state == "level_select":
                self.draw_level_select()
            elif self.state == "level_editor":
                self.draw_level_editor()
            else:
                self.draw_menu()
            self.update_soundtrack()
            pygame.display.flip()
        self.soundtrack.shutdown()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
