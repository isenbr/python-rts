"""Verdant Crown: a small, code-only medieval RTS powered by pygame-ce."""
from __future__ import annotations

import math
import random
import heapq
from dataclasses import dataclass, field
from enum import Enum, auto
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
FOG_UNEXPLORED_ALPHA = 235
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
PURCHASABLE_UNIT_KINDS = UNIT_KINDS
OBJECTIVE_UNIT_KINDS = ("king",)
AUTONOMOUS_GUARD_KINDS = ("knight",)
ALL_UNIT_KINDS = (
    *PURCHASABLE_UNIT_KINDS,
    *OBJECTIVE_UNIT_KINDS,
    *AUTONOMOUS_GUARD_KINDS,
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
KING_RECOVERY_THREAT_RADIUS = 5.0
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
}
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
        "none", 2000.0, 0.0,
    ),
    2: LevelConfig(
        2, "THE LONG ROAD", 60,
        "Swordsmen and archers. The enemy sends one swordsman at 200 gold.",
        ("swordsman", "archer"), (), (), "simple", 400.0, 0.0,
    ),
    3: LevelConfig(
        3, "THE VERDANT WAR", 120,
        "The complete battle with every troop and the adaptive enemy army.",
        UNIT_KINDS, PLAYER_STARTING_UNITS, ENEMY_STARTING_UNITS,
        "full", 400.0, 500.0,
    ),
}


def configure_map(size):
    """Update the shared world geometry before constructing a level."""
    global MAP_SIZE, MAP_CENTER, WORLD_MAX
    global GREEN_KING_POSITION, RED_KING_POSITION, CAMERA_START
    MAP_SIZE = size
    MAP_CENTER = MAP_SIZE / 2
    WORLD_MAX = MAP_SIZE - .5
    GREEN_KING_POSITION = (round(MAP_SIZE * .09), MAP_CENTER)
    RED_KING_POSITION = (round(MAP_SIZE * .885), MAP_CENTER)
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
        return self.team == "green" and self.is_purchasable_army_unit

    @property
    def is_enemy_ai_commandable(self):
        return self.team == "red" and self.is_purchasable_army_unit


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
            matchup = sum(
                cls.MATCHUP_MULTIPLIER[kind][opponent]
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
            if unit.kind not in PURCHASABLE_UNIT_KINDS
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
    # Casualties normally end a wave.  They may be ignored only when a new,
    # non-stale assessment measures an advantage strictly above this margin.
    # This deliberately sits above the ordinary "stronger" threshold.
    CASUALTY_ADVANTAGE_MARGIN = 1.5

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

    def _living_red_units(self):
        return [
            unit for unit in self.game.units
            if unit.is_enemy_ai_commandable and unit.health > 0
        ]

    def _squad_units(self):
        by_uid = {unit.uid: unit for unit in self._living_red_units()}
        return [by_uid[uid] for uid in sorted(self.squad) if uid in by_uid]

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
        advance_x, advance_y = self._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            (self.game.team_king("green").x, self.game.team_king("green").y),
        )
        side_x, side_y = -advance_y, advance_x
        forward_offset = self.FORMATION_FORWARD_OFFSETS[role]
        anchor_x, anchor_y = anchor or self.rally_point
        return clamp_to_map((
            anchor_x - advance_x * forward_offset + side_x * lateral,
            anchor_y - advance_y * forward_offset + side_y * lateral,
        ))

    def _assign_available_units(self):
        living_units = self._living_red_units()
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
                }[unit.kind]
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
        for uids in (self.squad, self.defenders, self.reserve):
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
        objective = self.game.team_king("green")
        if objective is None or objective.health <= 0:
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
        objective = self.game.team_king("green")
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
            counts[kind] += 1
        return counts

    def last_seen_player_composition(self):
        """Return deterministic per-kind unit counts and invested essence."""
        counts = {kind: 0 for kind in UNIT_KINDS}
        essence = {kind: 0 for kind in UNIT_KINDS}
        for sighting in self.last_seen_player_army.values():
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
        assigned_uids = self.squad | self.reserve | self.defenders
        for unit in self._living_red_units():
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
            invested[unit.kind] += UNIT_COSTS[unit.kind]
        return invested

    def production_target_shares(self):
        """Return strategic counter shares, always measured by essence cost."""
        if not self.learned_counter_essence:
            return {
                kind: 1 / len(ENEMY_PRODUCTION_KINDS)
                for kind in ENEMY_PRODUCTION_KINDS
            }
        total = sum(self.learned_counter_essence.values())
        if total <= 0:
            return {
                kind: 1 / len(ENEMY_PRODUCTION_KINDS)
                for kind in ENEMY_PRODUCTION_KINDS
            }
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
        self.reserve = set(sorted(
            (self.reserve | survivors) & living
        )[:self.DEFENSIVE_RESERVE_SIZE])
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
        squad_essence = self._group_essence(members)
        cost_ready = squad_essence >= self.TARGET_GROUP_ESSENCE
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
                    "bootstrap_ready"
                    if cost_ready
                    else "bootstrap_wait"
                ),
                "observation_revision": self.combat_observation_revision,
            }
            passed = cost_ready
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
            passed = cost_ready and (
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
                    "essence_wait" if not cost_ready
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
            "launch_gate": self.last_launch_gate.copy()
            if self.last_launch_gate else None,
        })
        self.transition_to(AIState.ATTACKING)
        self.combat_opponent_uids.clear()
        self.last_combat_decision_at = float("-inf")
        self.last_combat_decision = None
        for unit in members:
            unit.target = None
        self._advance_wave()

    def _advance_wave(self):
        """Advance toward the objective while allowing local combat to take priority."""
        self.recovery_guards.clear()
        members = self._squad_units()
        if not members:
            return
        advance_x, advance_y = self._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            (self.game.team_king("green").x, self.game.team_king("green").y),
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
        objective = (self.game.team_king("green").x, self.game.team_king("green").y)
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
            self.AWARENESS_RADIUS, self.game.effective_attack_range(unit)
        )

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
        if self.state == AIState.RECOVERING and unit.uid in self.squad:
            if unit.uid in self.recovery_guards:
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
            unit.target = None
            return None

        candidates = [
            opponent for opponent in self.game.nearby_units(
                unit, max(self.AWARENESS_RADIUS,
                          self.game.effective_attack_range(unit))
            )
            if self._is_valid_target(unit, opponent)
        ]
        current = unit.target if self._is_valid_target(unit, unit.target) else None
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
        if self.state == AIState.DEFENDING:
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
        red_units = self._living_red_units()

        if self.state == AIState.BUILDING and red_units:
            self.transition_to(AIState.RALLYING)
            self.rally_elapsed = 0.0

        if self.state == AIState.RALLYING:
            self.rally_elapsed += self.decision_interval
            self._assign_available_units()
            strength_gate_passed = self._launch_strength_gate()
            timed_out = self.rally_elapsed >= self.MAX_RALLY_WAIT
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
            # 2. Only a fresh advantage above CASUALTY_ADVANTAGE_MARGIN can
            #    override the casualty trigger.
            # 3. A weaker assessment retreats.
            # 4. Uncertain, missing, or stale evidence falls back to retreat
            #    when casualties have already made retreat necessary.
            if hard_safety_reason is not None:
                # A wiped-out wave can resolve a real encounter. Other hard
                # safety exits (such as an unreachable objective) cannot.
                self._begin_recovery(
                    casualty_victor
                    if hard_safety_reason == "no_viable_combat_units"
                    else None
                )
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


class Game:
    def __init__(
        self, enemy_rng=None, ai_decision_interval=.25, terrain_seed=None
    ):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.big = pygame.font.Font(None, 72)
        self.title = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 25)
        self.small = pygame.font.Font(None, 19)
        self.button_font = pygame.font.Font(None, 25)
        self.button_cost_font = pygame.font.Font(None, 18)
        self.state = "menu"
        self.play_btn = Button((WIDTH // 2 - 100, HEIGHT // 2 + 85, 200, 62), "Play!")
        self.level_buttons = []
        self.level_number = 3
        self.level = LEVELS[self.level_number]
        self.enemy_rng = enemy_rng
        self.ai_decision_interval = ai_decision_interval
        self.terrain_seed = TERRAIN_SEED if terrain_seed is None else terrain_seed
        self.reset()

    def reset(self, level_number=None):
        if level_number is not None:
            self.level_number = level_number
        self.level = LEVELS[self.level_number]
        configure_map(self.level.map_size)
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
        self.message = (
            "Defeat all enemy units"
            if self.level_number == 1
            else "Defeat the Crimson King"
        )
        self.message_time = 4
        self.winner = None
        self.essence_tick = 0
        self.reveal_tick = 0
        self.terrain = self.make_terrain()
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
        self.enemy_ai = EnemyAI(self, self.enemy_rng, self.ai_decision_interval)
        self._movement_snapshot_active = False
        self._path_searches_this_update = 0
        self.rebuild_unit_spatial_hash()

    def start_level(self, level_number, terrain_seed=None):
        """Begin a fresh battlefield, preserving its seed for later retries."""
        if terrain_seed is None:
            terrain_seed = random.SystemRandom().getrandbits(64)
        self.terrain_seed = terrain_seed
        self.reset(level_number)

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
        return terrain

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
                    unit.team != team
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
        visible_enemies = [u for u in self.units if u.team == "red" and self.is_visible(u.x, u.y)]
        candidates = visible_enemies
        clicked = min(candidates, key=lambda e: dist((e.x, e.y), world), default=None)
        if clicked and dist((clicked.x, clicked.y), world) < 1.5:
            for u in selected:
                self.clear_navigation(u)
                u.target, u.target_pos = clicked, (clicked.x, clicked.y)
                u.order_pos = None
                u.target_auto_acquired = False
            return
        cols = math.ceil(math.sqrt(len(selected)))
        for i, u in enumerate(selected):
            offset = ((i % cols - (cols - 1) / 2) * 1.15, (i // cols) * 1.15)
            self.clear_navigation(u)
            u.target = None
            u.target_auto_acquired = False
            u.order_pos = clamp_to_map(
                (world[0] + offset[0], world[1] + offset[1])
            )
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

    def is_visible(self, x, y):
        return (int(x), int(y)) in self.visible

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
                if unit.team == team and unit.is_purchasable_army_unit
                and unit.health > 0
            ]
            cells = set()
            for sx, sy, sight_budget in sources:
                cells.update(self._vision_mask((sx, sy), sight_budget))
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
            if candidate.team != unit.team and candidate.health > 0
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

    def nearby_king_recovery_threat(self, king):
        """Choose the nearest enemy close enough to interrupt king recovery."""
        candidates = [
            unit for unit in self.units
            if unit.team != king.team
            and unit.health > 0
            and dist((king.x, king.y), (unit.x, unit.y))
            <= KING_RECOVERY_THREAT_RADIUS
        ]
        return min(
            candidates,
            key=lambda unit: (
                dist((king.x, king.y), (unit.x, unit.y)),
                unit.uid,
            ),
            default=None,
        )

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
    def is_valid_guard_target(guard, target):
        if (
            target is None
            or target.team == guard.team
            or target.health <= 0
        ):
            return False
        home = guard.home_position or (guard.x, guard.y)
        return dist(home, (target.x, target.y)) <= GUARD_LEASH_DISTANCE

    @staticmethod
    def guard_chase_destination(guard, target):
        """Clamp a pursuit point to the guard's leash circle."""
        home = guard.home_position or (guard.x, guard.y)
        dx, dy = target.x - home[0], target.y - home[1]
        distance = math.hypot(dx, dy)
        if distance <= GUARD_LEASH_DISTANCE:
            return target.x, target.y
        return (
            home[0] + dx / distance * GUARD_LEASH_DISTANCE,
            home[1] + dy / distance * GUARD_LEASH_DISTANCE,
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
        if attacker.kind == "archer":
            arrow_multiplier = {
                "shield": ARCHER_DAMAGE_VS_SHIELD_MULTIPLIER,
                "king": ARCHER_DAMAGE_VS_KING_MULTIPLIER,
                "knight": ARCHER_DAMAGE_VS_KNIGHT_MULTIPLIER,
            }.get(getattr(target, "kind", None), 1.0)
            damage *= arrow_multiplier
            attacker_terrain = self.terrain_kind_at((attacker.x, attacker.y))
            target_terrain = self.terrain_kind_at((target.x, target.y))
            if attacker_terrain == "mountain" and target_terrain != "mountain":
                damage *= 1.2
            damage *= TERRAIN_METADATA[target_terrain][
                "ranged_damage_taken_multiplier"
            ]
        target_terrain = self.terrain_kind_at((target.x, target.y))
        damage *= TERRAIN_METADATA[target_terrain]["damage_taken_multiplier"]
        target.health -= damage
        target.flash = .12
        attacker.attack_timer = attacker.cooldown
        if attacker.kind == "archer":
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
            _, multiplier = self.terrain_cell_and_speed_multiplier(
                (sample_x, sample_y)
            )
            effective_speed = min(
                base_speed * multiplier,
                unit.speed * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER,
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
        preferred_x = preferred_y = 0.0
        if distance >= .08:
            preferred_x = dx / distance * unit.speed
            preferred_y = dy / distance * unit.speed

        preferred_step = min(
            distance, unit.speed * max(0.0, dt)
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
                    unit.speed
                    * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER
                    * overlap_response,
                ),
                unit.speed * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER,
            )
            separation_x = separation_x / separation_amount * separation_speed
            separation_y = separation_y / separation_amount * separation_speed

        velocity_x = preferred_x + separation_x
        velocity_y = preferred_y + separation_y
        velocity = math.hypot(velocity_x, velocity_y)
        if velocity <= 1e-12 or dt <= 0:
            return False
        max_speed = unit.speed * UNIT_MAX_SEPARATION_SPEED_MULTIPLIER
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
        u.moved_this_update = False
        if u.health <= 0:
            u.selected = False
            u.target = None
            u.target_pos = None
            u.order_pos = None
            u.target_auto_acquired = False
            u.tactical_pos = None
            self.clear_navigation(u)
            return
        if u.is_king_objective or u.is_autonomous_guard:
            u.selected = False
            u.tactical_pos = None
            if u.home_position is None:
                u.home_position = (u.x, u.y)
            if u.is_king_objective:
                if u.health <= u.max_health * KING_RECOVERY_HEALTH_RATIO:
                    u.king_recovering = True
                at_home = dist((u.x, u.y), u.home_position) < .08
                if (
                    at_home
                    and u.health < u.max_health
                    and not self._movement_snapshot_active
                ):
                    u.health = min(u.max_health, u.health + KING_HOME_HEAL_RATE * dt)
                if u.health >= u.max_health:
                    u.king_recovering = False
        elif not (u.is_player_commandable or u.is_enemy_ai_commandable):
            u.selected = False
            u.target = None
            u.target_pos = None
        u.attack_timer = max(0, u.attack_timer - dt)
        if u.movement_lock_timer <= dt + 1e-9:
            u.movement_lock_timer = 0
        else:
            u.movement_lock_timer -= dt
        u.flash = max(0, u.flash - dt)
        movement_locked = u.kind == "archer" and u.movement_lock_timer > 0
        target = u.target
        if target is not None and getattr(target, "health", 0) <= 0:
            dead_target_position = (target.x, target.y)
            was_auto = u.target_auto_acquired
            self.release_combat_target(u)
            target = None
            if (
                not (was_auto and u.order_pos is not None)
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
            recovery_threat = (
                self.nearby_king_recovery_threat(u)
                if u.is_king_objective and u.king_recovering
                else None
            )
            if u.is_king_objective and u.king_recovering and recovery_threat is None:
                u.target = None
                u.target_pos = u.home_position
                if dist((u.x, u.y), u.home_position) < .08:
                    u.x, u.y = u.home_position
                    u.target_pos = None
                    self.clear_navigation(u)
                else:
                    self.navigate_unit_toward(u, u.home_position, dt)
                    if (u.x, u.y) == u.home_position:
                        u.target_pos = None
                return
            target = recovery_threat or self.autonomous_guard_target(u)
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
        if u.is_enemy_ai_commandable:
            auto = self.enemy_ai.choose_target(u)
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
                    and (u.kind != "archer" or not u.moved_this_update)
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
            return
        self.message_time = max(0, self.message_time - dt)
        self.navigation_time += max(0.0, dt)
        self._path_searches_this_update = 0
        self.essence += 20 * dt
        self.enemy_essence += 20 * dt
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
                was_auto = unit.target_auto_acquired
                self.release_combat_target(unit)
                if (
                    not (was_auto and unit.order_pos is not None)
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
            if u.team == "red" and not self.is_visible(u.x, u.y):
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
        color = GREEN if u.team == "green" else RED
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
            pygame.draw.circle(self.screen, GOLD, (int(sx), int(sy)), max(2, int(self.zoom * .13)))
        for x, y, life, team in self.particles:
            sx, sy = self.world_to_screen(x, y)
            radius = max(2, int(self.zoom * (1 - life / .25) * .4))
            pygame.draw.circle(self.screen, CREAM, (int(sx), int(sy)), radius, 1)
        for slash in self.king_slashes:
            if slash.team == "red" and not self.is_visible(slash.x, slash.y):
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
        if self.level_number == 1:
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
        self.screen.blit(self.small.render("+20 gold each second", True, (172, 158, 128)), (55, top + 44))
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
        self.play_btn.rect.center = (w // 2, h // 2 + 110)
        self.play_btn.draw(self.screen, pygame.mouse.get_pos(), self.button_font, self.button_cost_font)
        hint = self.small.render("Mouse + keyboard  •  Press Play to begin", True, (200, 190, 160))
        self.screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 80))

    def draw_level_select(self):
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

    def draw_game(self):
        self.draw_terrain()
        for u in self.units: self.draw_unit(u)
        self.draw_effects(); self.draw_fog()
        if self.drag_start and self.drag_now:
            rect = pygame.Rect(self.drag_start, (self.drag_now[0] - self.drag_start[0], self.drag_now[1] - self.drag_start[1])); rect.normalize()
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA); overlay.fill((102, 192, 112, 45)); self.screen.blit(overlay, rect)
            pygame.draw.rect(self.screen, (134, 211, 142), rect, 1)
        self.draw_hud()
        if self.message_time > 0:
            label = self.font.render(self.message, True, CREAM)
            panel_padding = 10
            box = label.get_rect(
                midtop=(self.screen.get_width() // 2, panel_padding)
            ).inflate(panel_padding * 2, panel_padding * 2)
            box.top = panel_padding
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
                center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 24)
            ),
        )
        sub = self.font.render("Esc to resume  •  M for menu", True, CREAM)
        self.screen.blit(
            sub,
            sub.get_rect(
                center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 28)
            ),
        )

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
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.play_btn.rect.collidepoint(event.pos):
                        self.state = "level_select"
                    elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.state = "level_select"
                elif self.state == "level_select":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.state = "menu"
                    elif event.type == pygame.KEYDOWN and event.key in (
                        pygame.K_1, pygame.K_2, pygame.K_3,
                    ):
                        self.start_level(event.key - pygame.K_0)
                        self.state = "playing"
                        self.update_visibility()
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        for button, number in self.level_buttons:
                            if button.rect.collidepoint(event.pos):
                                self.start_level(number)
                                self.state = "playing"
                                self.update_visibility()
                                break
                elif self.state == "paused":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.state = "playing"
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                        self.state = "menu"
                else: self.handle_game_event(event)
            if self.state == "playing":
                self.camera_input(dt); self.update(dt); self.draw_game()
            elif self.state == "paused":
                self.draw_game(); self.draw_pause()
            elif self.state == "level_select":
                self.draw_level_select()
            else:
                self.draw_menu()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
