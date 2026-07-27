"""Verdant Crown: a small, code-only medieval RTS powered by pygame-ce."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import pygame

pygame.init()
pygame.display.set_caption("Verdant Crown")

WIDTH, HEIGHT = 1280, 720
MAP_SIZE, HUD_H = 200, 126
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
GROUND_COLOR = (76, 109, 60)
TERRAIN_DETAIL_MIN_ZOOM = 7
UNIT_COSTS = {"swordsman": 200, "archer": 500}


def clamp(value, low, high):
    return max(low, min(high, value))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


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
    target: object = None
    attack_timer: float = 0
    flash: float = 0
    selected: bool = False
    uid: int = 0
    tactical_pos: Optional[tuple[float, float]] = None
    tactical_timer: float = 0

    def __post_init__(self):
        if self.kind == "swordsman":
            self.max_health, self.speed, self.damage = 100, 1, 5
            self.cooldown, self.attack_range = .5, 1.02
        else:
            self.max_health, self.speed, self.damage = 20, 2, 30
            self.cooldown, self.attack_range = 1, 5
        self.health = self.max_health


@dataclass
class Base:
    team: str
    x: float
    y: float
    health: float = 250
    max_health: float = 250
    attack_timer: float = 0
    flash: float = 0


class AIState(Enum):
    BUILDING = auto()
    RALLYING = auto()
    ATTACKING = auto()
    DEFENDING = auto()
    RECOVERING = auto()


class EnemyAI:
    """Owns red-team strategy without changing per-unit combat or movement."""

    AWARENESS_RADIUS = 10.0
    ARCHER_PROTECTION_RADIUS = 4.0
    BASE_DEFENSE_RADIUS = 14.0
    SWITCH_MARGIN = 18.0
    ARCHER_DANGER_RADIUS = 3.25
    ARCHER_SAFE_RADIUS = 4.25
    SEPARATION_RADIUS = 1.15
    TACTICAL_RECHECK = .45
    RALLY_LEASH = 5.0
    RALLY_DISTANCE = 8.0
    MIN_SQUAD_STRENGTH = 4
    MAX_RALLY_WAIT = 18.0
    FORMATION_TOLERANCE = 3.0
    FORMATION_READY_FRACTION = .6
    FRONT_SPACING = 1.45
    LINE_SPACING = 2.25
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
    SCOUTING_RADIUS = 10.0
    KEEP_VISION_RADIUS = 16.0
    MIN_FRONTLINE = 2
    FRONTLINE_RATIO = .5
    SCORE_HYSTERESIS = 8.0
    LOSS_MEMORY_DURATION = 24.0

    # Production score weights. Keeping these named makes balance changes explicit.
    BASE_SWORD_SCORE = 42.0
    BASE_ARCHER_SCORE = 38.0
    EXPOSED_ARCHER_SWORD_BONUS = 18.0
    PLAYER_SWORD_ARCHER_BONUS = 15.0
    FRONTLINE_SHORTAGE_BONUS = 42.0
    PROTECTED_ARCHER_BONUS = 14.0
    MISSING_BACKLINE_BONUS = 20.0
    UNPROTECTED_ARCHER_PENALTY = 34.0
    EMERGENCY_SWORD_BONUS = 65.0
    RECENT_SWORD_LOSS_BONUS = 5.0
    RECENT_ARCHER_LOSS_BONUS = 7.0
    FAILED_WAVE_FRONTLINE_BONUS = 6.0
    SAVE_FOR_ARCHER_MARGIN = 6.0
    SERIOUS_THREAT_SCORE = 4.0
    STATE_PRODUCTION_WEIGHTS = {
        AIState.BUILDING: {"swordsman": 8.0, "archer": 4.0},
        AIState.RALLYING: {"swordsman": 5.0, "archer": 8.0},
        AIState.ATTACKING: {"swordsman": 8.0, "archer": 3.0},
        AIState.DEFENDING: {"swordsman": 16.0, "archer": -4.0},
        AIState.RECOVERING: {"swordsman": 12.0, "archer": 2.0},
    }

    VALID_TRANSITIONS = {
        AIState.BUILDING: {AIState.RALLYING, AIState.ATTACKING, AIState.DEFENDING},
        AIState.RALLYING: {AIState.BUILDING, AIState.ATTACKING, AIState.DEFENDING},
        AIState.ATTACKING: {AIState.RALLYING, AIState.DEFENDING, AIState.RECOVERING},
        AIState.DEFENDING: {
            AIState.BUILDING, AIState.RALLYING, AIState.ATTACKING, AIState.RECOVERING
        },
        AIState.RECOVERING: {AIState.BUILDING, AIState.RALLYING, AIState.DEFENDING},
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
        self.formation_roles: dict[int, str] = {}
        self.rally_elapsed = 0.0
        self.recovery_elapsed = 0.0
        self.wave_start_strength = 0
        self.wave_number = 0
        self.wave_history: list[dict] = []
        self.reserve: set[int] = set()
        self.defenders: set[int] = set()
        self.pre_defense_state = AIState.BUILDING
        self.defense_clear_elapsed = 0.0
        self.emergency_recruited = False
        self.last_threat_score = 0.0
        self.state_history = [(0.0, self.state)]
        self.elapsed = 0.0
        self.player_knowledge: dict[int, tuple[str, float]] = {}
        self.recent_losses: list[tuple[float, str]] = []
        self._known_red_uids: dict[int, str] = {
            unit.uid: unit.kind for unit in self._living_red_units()
        }
        self.failed_waves = 0
        self.last_production_choice: Optional[str] = None
        self.production_history: list[dict] = []
        self.last_production_scores = {"swordsman": 0.0, "archer": 0.0}

    def transition_to(self, state):
        if state == self.state:
            return
        if state not in self.VALID_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid enemy AI transition: {self.state.name} -> {state.name}")
        self.state = state
        self.state_history.append((self.elapsed, state))

    @property
    def rally_point(self):
        """A fixed staging point between the Crimson Hold and the battlefield."""
        direction_x, direction_y = self._unit_vector(
            (self.game.enemy_base.x, self.game.enemy_base.y),
            (self.game.player_base.x, self.game.player_base.y),
        )
        return (
            self.game.enemy_base.x + direction_x * self.RALLY_DISTANCE,
            self.game.enemy_base.y + direction_y * self.RALLY_DISTANCE,
        )

    def _living_red_units(self):
        return [
            unit for unit in self.game.units
            if unit.team == "red" and unit.health > 0
        ]

    def _squad_units(self):
        by_uid = {unit.uid: unit for unit in self._living_red_units()}
        return [by_uid[uid] for uid in sorted(self.squad) if uid in by_uid]

    def _cleanup_squad(self):
        living = {unit.uid for unit in self._living_red_units()}
        self.squad.intersection_update(living)
        self.reserve.intersection_update(living)
        self.defenders.intersection_update(living)
        self.formation_roles = {
            uid: role for uid, role in self.formation_roles.items() if uid in living
        }

    def _formation_destination(self, unit, ordered_units=None):
        ordered_units = ordered_units or self._squad_units()
        role = self.formation_roles[unit.uid]
        role_units = [member for member in ordered_units if self.formation_roles[member.uid] == role]
        index = role_units.index(unit)
        lateral = (index - (len(role_units) - 1) / 2) * self.FRONT_SPACING
        advance_x, advance_y = self._unit_vector(
            (self.game.enemy_base.x, self.game.enemy_base.y),
            (self.game.player_base.x, self.game.player_base.y),
        )
        side_x, side_y = -advance_y, advance_x
        rear_offset = self.LINE_SPACING if role == "rear" else 0.0
        rally_x, rally_y = self.rally_point
        return (
            rally_x - advance_x * rear_offset + side_x * lateral,
            rally_y - advance_y * rear_offset + side_y * lateral,
        )

    def _assign_available_units(self):
        available = [
            unit for unit in self._living_red_units()
            if unit.uid not in self.squad and unit.uid not in self.reserve
        ]
        # Keep a small home guard once there are enough troops to form a full wave.
        desired_reserve = min(
            self.DEFENSIVE_RESERVE_SIZE,
            max(0, len(self._living_red_units()) - self.MIN_SQUAD_STRENGTH),
        )
        reserve_needed = max(0, desired_reserve - len(self.reserve))
        base_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        for unit in sorted(
            available,
            key=lambda member: (dist((member.x, member.y), base_pos), member.uid),
        )[:reserve_needed]:
            self.reserve.add(unit.uid)
            unit.target = None
            unit.target_pos = self._reserve_position(unit)
        available = [unit for unit in available if unit.uid not in self.reserve]
        for unit in sorted(available, key=lambda member: member.uid):
            self.squad.add(unit.uid)
            self.formation_roles[unit.uid] = (
                "frontline" if unit.kind == "swordsman" else "rear"
            )
            unit.target = None
        squad_units = self._squad_units()
        for unit in squad_units:
            if self.state in (AIState.BUILDING, AIState.RALLYING):
                unit.target_pos = self._formation_destination(unit, squad_units)

    def _reserve_position(self, unit):
        index = sorted(self.reserve).index(unit.uid) if unit.uid in self.reserve else 0
        return (
            self.game.enemy_base.x - 3.0,
            self.game.enemy_base.y + (index - (len(self.reserve) - 1) / 2) * 1.8,
        )

    def _player_threats(self):
        base_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        radius = (
            self.DEFENSE_EXIT_RADIUS
            if self.state == AIState.DEFENDING else self.DEFENSE_ZONE_RADIUS
        )
        threats = []
        for unit in self.game.units:
            if unit.team != "green" or unit.health <= 0:
                continue
            distance = dist((unit.x, unit.y), base_pos)
            attacking_base = unit.target is self.game.enemy_base
            destination_near_base = (
                unit.target_pos is not None
                and dist(unit.target_pos, base_pos) <= self.DEFENSE_ZONE_RADIUS
            )
            approaching = (
                distance <= self.DEFENSE_APPROACH_RADIUS
                and (attacking_base or destination_near_base)
            )
            if distance <= radius or approaching:
                danger = 2.0 if unit.kind == "swordsman" else 1.5
                danger *= max(.25, unit.health / unit.max_health)
                if attacking_base:
                    danger += 2.5
                elif destination_near_base:
                    danger += .75
                # Units in the hysteresis band count only if they are still advancing.
                if distance > self.DEFENSE_ZONE_RADIUS and not (
                    attacking_base or destination_near_base
                ):
                    danger *= .35
                threats.append((unit, danger))
        return threats

    def _update_strategic_knowledge(self):
        """Remember only player units actually observed by red scouts or the keep."""
        observers = self._living_red_units()
        base_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        for unit in self.game.units:
            if unit.team != "green" or unit.health <= 0:
                continue
            observed = dist((unit.x, unit.y), base_pos) <= self.KEEP_VISION_RADIUS
            observed = observed or any(
                dist((unit.x, unit.y), (scout.x, scout.y)) <= self.SCOUTING_RADIUS
                for scout in observers
            )
            if observed:
                self.player_knowledge[unit.uid] = (unit.kind, self.elapsed)
        self.player_knowledge = {
            uid: sighting for uid, sighting in self.player_knowledge.items()
            if self.elapsed - sighting[1] <= self.PLAYER_KNOWLEDGE_TTL
        }

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
        counts = {"swordsman": 0, "archer": 0}
        for kind, _ in self.player_knowledge.values():
            counts[kind] += 1
        return counts

    def production_scores(self, threat_score=None):
        """Return deterministic weighted utility for each recruitable unit."""
        threat_score = self.last_threat_score if threat_score is None else threat_score
        own = {"swordsman": 0, "archer": 0}
        assigned = {"swordsman": 0, "archer": 0}
        assigned_uids = self.squad | self.reserve | self.defenders
        for unit in self._living_red_units():
            own[unit.kind] += 1
            if unit.uid in assigned_uids:
                assigned[unit.kind] += 1
        known = self.known_player_composition()
        known_total = sum(known.values())
        scores = {
            "swordsman": self.BASE_SWORD_SCORE,
            "archer": self.BASE_ARCHER_SCORE,
        }
        for kind in scores:
            scores[kind] += self.STATE_PRODUCTION_WEIGHTS[self.state][kind]

        # Unknown armies use the neutral base weights; sightings add soft counters.
        if known_total:
            scores["swordsman"] += (
                known["archer"] / known_total * self.EXPOSED_ARCHER_SWORD_BONUS
            )
            scores["archer"] += (
                known["swordsman"] / known_total * self.PLAYER_SWORD_ARCHER_BONUS
            )

        total = sum(own.values())
        required_frontline = max(
            self.MIN_FRONTLINE,
            math.ceil((total + 1) * self.FRONTLINE_RATIO),
        )
        frontline_shortage = max(0, required_frontline - own["swordsman"])
        scores["swordsman"] += frontline_shortage * self.FRONTLINE_SHORTAGE_BONUS
        if own["swordsman"] >= required_frontline:
            scores["archer"] += self.PROTECTED_ARCHER_BONUS
            if total >= self.MIN_SQUAD_STRENGTH and own["archer"] == 0:
                scores["archer"] += self.MISSING_BACKLINE_BONUS
        else:
            scores["archer"] -= self.UNPROTECTED_ARCHER_PENALTY

        if threat_score >= self.SERIOUS_THREAT_SCORE:
            scores["swordsman"] += self.EMERGENCY_SWORD_BONUS
        loss_counts = {
            kind: sum(loss_kind == kind for _, loss_kind in self.recent_losses)
            for kind in ("swordsman", "archer")
        }
        scores["swordsman"] += loss_counts["swordsman"] * self.RECENT_SWORD_LOSS_BONUS
        scores["archer"] += loss_counts["archer"] * self.RECENT_ARCHER_LOSS_BONUS
        scores["swordsman"] += self.failed_waves * self.FAILED_WAVE_FRONTLINE_BONUS

        # Assigned composition matters explicitly: an attack with no assigned screen
        # should replenish melee even if unassigned archers are waiting at home.
        if assigned["archer"] and not assigned["swordsman"]:
            scores["swordsman"] += self.FRONTLINE_SHORTAGE_BONUS
        if self.last_production_choice:
            scores[self.last_production_choice] += self.SCORE_HYSTERESIS
        self.last_production_scores = scores
        return scores

    def choose_production(self, threat_score=None):
        scores = self.production_scores(threat_score)
        essence = self.game.enemy_essence
        affordable = [
            kind for kind in ("swordsman", "archer")
            if essence >= UNIT_COSTS[kind]
        ]
        if not affordable:
            return None
        best = max(("swordsman", "archer"), key=lambda kind: (scores[kind], kind))
        if best == "archer" and essence < UNIT_COSTS["archer"]:
            serious = (threat_score if threat_score is not None else self.last_threat_score)
            if (
                serious < self.SERIOUS_THREAT_SCORE
                and scores["archer"] >= scores["swordsman"] + self.SAVE_FOR_ARCHER_MARGIN
            ):
                return None
            best = "swordsman"
        return best if best in affordable else max(
            affordable, key=lambda kind: (scores[kind], kind)
        )

    def _run_production(self, threat_score):
        if self.recruitment_timer > 0:
            return None
        kind = self.choose_production(threat_score)
        if kind is None:
            # Reconsider savings frequently without allowing per-frame oscillation.
            self.recruitment_timer = self.PRODUCTION_INTERVAL / 3
            return None
        if self.game.recruit(kind, "red"):
            self.last_production_choice = kind
            self.production_history.append({
                "time": self.elapsed,
                "state": self.state.name,
                "kind": kind,
                "scores": self.last_production_scores.copy(),
            })
            self._known_red_uids[self.game.units[-1].uid] = kind
            self.recruitment_timer = self.PRODUCTION_INTERVAL
            return kind
        self.recruitment_timer = self.PRODUCTION_INTERVAL / 3
        return None

    def _defensive_target_score(self, target):
        base_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        distance = dist((target.x, target.y), base_pos)
        score = 120.0 - distance * 6.0
        if target.target is self.game.enemy_base:
            score += 90.0
        if target.target_pos is not None:
            score += max(0.0, 30.0 - dist(target.target_pos, base_pos) * 2.0)
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
        base_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        nearby = [
            unit for unit in red_units
            if unit.uid not in self.defenders and unit.uid not in self.reserve
            and unit.uid not in self.squad
            and dist((unit.x, unit.y), base_pos) <= self.DEFENDER_ASSIGN_RADIUS
        ]
        selected.extend(sorted(
            nearby, key=lambda unit: (dist((unit.x, unit.y), base_pos), unit.uid)
        ))
        if threat_score >= self.RECALL_THREAT_THRESHOLD:
            attackers = [
                unit for unit in red_units
                if unit.uid in self.squad and unit.uid not in self.defenders
            ]
            needed = max(1, math.ceil(threat_score / 2) - len(selected))
            selected.extend(sorted(
                attackers,
                key=lambda unit: (dist((unit.x, unit.y), base_pos), unit.uid),
            )[:needed])
        self.defenders.update(unit.uid for unit in selected)

        ordered_threats = sorted(
            (entry[0] for entry in threats),
            key=lambda target: (-self._defensive_target_score(target), target.uid),
        )
        advance = self._unit_vector(
            base_pos, (self.game.player_base.x, self.game.player_base.y)
        )
        for index, unit in enumerate(selected):
            unit.target = None
            if unit.kind == "archer":
                # Fire from the far side of the keep, away from the incoming line.
                side = (index % 3 - 1) * 1.8
                unit.target_pos = (
                    self.game.enemy_base.x - advance[0] * self.ARCHER_DEFENSE_OFFSET,
                    self.game.enemy_base.y - advance[1] * self.ARCHER_DEFENSE_OFFSET + side,
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

    def _launch_wave(self):
        members = self._squad_units()
        if not members:
            return
        self.wave_number += 1
        self.wave_start_strength = len(members)
        composition = {
            kind: sum(unit.kind == kind for unit in members)
            for kind in ("swordsman", "archer")
        }
        self.wave_history.append({
            "wave": self.wave_number,
            "launched_at": self.elapsed,
            "wait": self.rally_elapsed,
            "composition": composition,
        })
        self.transition_to(AIState.ATTACKING)
        for unit in members:
            unit.target = None
            unit.target_pos = (self.game.player_base.x, self.game.player_base.y)

    def _advance_wave(self):
        """Advance toward the objective while allowing local combat to take priority."""
        members = self._squad_units()
        if not members:
            return
        advance_x, advance_y = self._unit_vector(
            (self.game.enemy_base.x, self.game.enemy_base.y),
            (self.game.player_base.x, self.game.player_base.y),
        )
        front = min(unit.x * advance_x + unit.y * advance_y for unit in members)
        for unit in members:
            if unit.target is not None:
                continue
            progress = unit.x * advance_x + unit.y * advance_y
            # Faster rear units wait when they would split far ahead of the wave.
            if progress > front + self.WAVE_COHESION_TOLERANCE:
                unit.target_pos = (unit.x, unit.y)
            else:
                rear_offset = (
                    self.LINE_SPACING
                    if self.formation_roles.get(unit.uid) == "rear"
                    else 0.0
                )
                unit.target_pos = (
                    self.game.player_base.x - advance_x * rear_offset,
                    self.game.player_base.y - advance_y * rear_offset,
                )

    def _begin_recovery(self):
        if self.wave_start_strength and len(self._squad_units()) < self.wave_start_strength:
            self.failed_waves += 1
        self.transition_to(AIState.RECOVERING)
        self.recovery_elapsed = 0.0
        for unit in self._squad_units():
            unit.target = None
            unit.target_pos = self.rally_point

    def _finish_recovery(self):
        self.squad.clear()
        self.formation_roles.clear()
        self.wave_start_strength = 0
        self.rally_elapsed = 0.0
        next_state = AIState.RALLYING if self._living_red_units() else AIState.BUILDING
        self.transition_to(next_state)

    def _is_valid_target(self, unit, target):
        if target is None or getattr(target, "health", 0) <= 0:
            return False
        if getattr(target, "team", unit.team) == unit.team:
            return False
        target_range = unit.attack_range + (2.5 if isinstance(target, Base) else 0)
        return dist((unit.x, unit.y), (target.x, target.y)) <= max(
            self.AWARENESS_RADIUS, target_range
        )

    def _threatens(self, target, protected):
        if target.target is protected:
            return True
        if target.target_pos is None:
            return False
        return dist(target.target_pos, (protected.x, protected.y)) <= protected.attack_range + 1.0

    def target_score(self, unit, target):
        """Score only locally observable targets; larger values are more desirable."""
        distance = dist((unit.x, unit.y), (target.x, target.y))
        score = 100.0 - distance * 5.0

        if isinstance(target, Base):
            return score - 20.0

        # Active attackers are urgent, especially when they threaten this unit.
        if target.target is unit:
            score += 45.0
        elif self._threatens(target, unit):
            score += 28.0
        if target.attack_range >= distance:
            score += 14.0

        # Finishing a unit is valuable, but does not outweigh every immediate danger.
        health_ratio = target.health / target.max_health
        score += (1.0 - health_ratio) * 30.0
        if target.health <= unit.damage:
            score += 32.0

        if unit.kind == "swordsman" and target.kind == "archer":
            score += 34.0
        elif unit.kind == "archer":
            if target.kind == "archer":
                score += 12.0
            if target.damage >= unit.health or target.kind == "swordsman" and distance <= 5.0:
                score += 22.0

        # Locally protect fragile allied archers.
        allied_archers = [
            ally for ally in self.game.units
            if ally.team == unit.team and ally.kind == "archer" and ally.health > 0
            and dist((unit.x, unit.y), (ally.x, ally.y)) <= self.AWARENESS_RADIUS
        ]
        if any(
            dist((target.x, target.y), (ally.x, ally.y)) <= self.ARCHER_PROTECTION_RADIUS
            or self._threatens(target, ally)
            for ally in allied_archers
        ):
            score += 32.0

        # Units approaching or attacking the red keep receive defensive priority.
        if (
            dist((target.x, target.y), (self.game.enemy_base.x, self.game.enemy_base.y))
            <= self.BASE_DEFENSE_RADIUS
            or target.target is self.game.enemy_base
        ):
            score += 70.0
        return score

    def choose_target(self, unit):
        candidates = [
            opponent for opponent in self.game.units
            if opponent.team != unit.team and self._is_valid_target(unit, opponent)
        ]
        if self._is_valid_target(unit, self.game.player_base):
            candidates.append(self.game.player_base)

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
            anchor = (self.game.enemy_base.x, self.game.enemy_base.y)
            radius = self.BASE_DEFENSE_RADIUS
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
        return clamp(x, .5, MAP_SIZE - .5), clamp(y, .5, MAP_SIZE - .5)

    def _separation_vector(self, unit):
        sx = sy = 0.0
        for other in self.game.units:
            if other is unit or other.team != unit.team or other.health <= 0:
                continue
            dx, dy = unit.x - other.x, unit.y - other.y
            distance = math.hypot(dx, dy)
            if distance >= self.SEPARATION_RADIUS:
                continue
            if distance <= 1e-9:
                # Stable uid-based direction makes exact overlaps deterministic.
                angle = (unit.uid * 2.399963229728653) % math.tau
                dx, dy, distance = math.cos(angle), math.sin(angle), 1e-6
            strength = self.SEPARATION_RADIUS - distance
            sx += dx / distance * strength
            sy += dy / distance * strength
        return sx, sy

    def tactical_destination(self, unit, dt):
        """Return a short-lived local steering goal for enemy units only."""
        unit.tactical_timer = max(0.0, unit.tactical_timer - dt)
        opponents = [
            other for other in self.game.units
            if other.team != unit.team and other.health > 0
        ]

        if unit.kind == "archer":
            melee = [other for other in opponents if other.kind == "swordsman"]
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
                <= unit.attack_range + (2.3 if isinstance(target, Base) else 0)
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

        elif unit.kind == "swordsman":
            allied_archers = [
                ally for ally in self.game.units
                if ally.team == unit.team and ally.kind == "archer" and ally.health > 0
                and dist((unit.x, unit.y), (ally.x, ally.y)) <= self.AWARENESS_RADIUS
            ]
            screen = None
            for archer in allied_archers:
                threats = [
                    foe for foe in opponents
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
                > unit.attack_range
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

        separation_x, separation_y = self._separation_vector(unit)
        if abs(separation_x) + abs(separation_y) > 1e-9:
            unit.tactical_pos = self._constrain_tactical_position(
                unit, (unit.x + separation_x, unit.y + separation_y)
            )
            unit.tactical_timer = self.TACTICAL_RECHECK
            return unit.tactical_pos
        unit.tactical_pos = None
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
                danger for unit, danger in threats if unit.kind == "swordsman"
            )
            has_melee_defender = any(
                unit.uid in self.defenders and unit.kind == "swordsman"
                for unit in self._living_red_units()
            )
            if (
                melee_threat >= self.EMERGENCY_MELEE_THREAT
                and not has_melee_defender
                and not self.emergency_recruited
                and self.game.enemy_essence >= UNIT_COSTS["swordsman"]
            ):
                if self.game.recruit("swordsman", "red"):
                    recruit = self.game.units[-1]
                    self.reserve.add(recruit.uid)
                    self.defenders.add(recruit.uid)
                    self.emergency_recruited = True
                    self._known_red_uids[recruit.uid] = recruit.kind
                    self.last_production_choice = "swordsman"
                    self.production_history.append({
                        "time": self.elapsed,
                        "state": self.state.name,
                        "kind": "swordsman",
                        "scores": self.production_scores(threat_score).copy(),
                        "emergency": True,
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
            strong_enough = len(self.squad) >= self.MIN_SQUAD_STRENGTH
            timed_out = self.rally_elapsed >= self.MAX_RALLY_WAIT
            if self.squad and ((strong_enough and self._formation_ready()) or timed_out):
                self._launch_wave()
        elif self.state == AIState.ATTACKING:
            living_strength = len(self.squad)
            losses = self.wave_start_strength - living_strength
            loss_fraction = losses / max(1, self.wave_start_strength)
            if living_strength == 0 or loss_fraction >= self.RECOVERY_LOSS_FRACTION:
                self._begin_recovery()
            else:
                self._advance_wave()
        elif self.state == AIState.RECOVERING:
            self.recovery_elapsed += self.decision_interval
            if self.recovery_elapsed >= self.RECOVERY_DURATION:
                self._finish_recovery()


class Button:
    def __init__(self, rect, text, sub="", disabled_text=(130, 126, 116), disabled_sub=(110, 105, 97)):
        self.rect = pygame.Rect(rect)
        self.text, self.sub = text, sub
        self.disabled_text = disabled_text
        self.disabled_sub = disabled_sub

    def draw(self, surf, mouse, label_font, cost_font, enabled=True):
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
    def __init__(self, enemy_rng=None, ai_decision_interval=.25):
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
        self.enemy_rng = enemy_rng
        self.ai_decision_interval = ai_decision_interval
        self.reset()

    def reset(self):
        self.units: list[Unit] = []
        self.player_base = Base("green", 18, 100)
        self.enemy_base = Base("red", 177, 100)
        self.essence = 400.0
        self.enemy_essence = 500.0
        self.uid = 0
        self.camera = [20.5, 100.5]
        self.zoom = 13.0
        self.explored = set()
        self.visible = set()
        self._fog_revision = 0
        self._fog_cache_key = None
        self._fog_cache_surface = None
        self.drag_start = None
        self.drag_now = None
        self.arrows = []
        self.particles = []
        self.message = "Destroy the Crimson Hold"
        self.message_time = 4
        self.winner = None
        self.essence_tick = 0
        self.reveal_tick = 0
        self.terrain = self.make_terrain()
        self.add_unit("swordsman", "green", 24, 99)
        self.add_unit("swordsman", "green", 24, 102)
        self.add_unit("archer", "green", 26, 100.5)
        for y in (98, 100, 102):
            self.add_unit("swordsman", "red", 171, y)
        self.add_unit("archer", "red", 169, 100)
        self.enemy_ai = EnemyAI(self, self.enemy_rng, self.ai_decision_interval)

    def make_terrain(self):
        rng = random.Random(TERRAIN_SEED)
        terrain = {}
        self.terrain_tones = {}
        self.terrain_details = {}
        quiet_zones = (
            (self.player_base.x, self.player_base.y, 4.5),
            (24.5, 100.5, 3.5),
            (self.enemy_base.x, self.enemy_base.y, 4.5),
            (170.5, 100.5, 3.5),
        )
        for x in range(MAP_SIZE):
            for y in range(MAP_SIZE):
                self.terrain_tones[(x, y)] = rng.choices(
                    (-3, -2, -1, 0, 1, 2, 3),
                    (1, 4, 8, 13, 8, 4, 1),
                )[0]
                if any((x + .5 - qx) ** 2 + (y + .5 - qy) ** 2 < radius ** 2
                       for qx, qy, radius in quiet_zones):
                    continue
                roll = rng.random()
                if roll < .018:
                    kind = "tuft"
                elif roll < .026:
                    kind = "stone"
                elif roll < .035:
                    kind = "dirt"
                else:
                    continue
                self.terrain_details[(x, y)] = (
                    kind,
                    rng.uniform(.2, .8),
                    rng.uniform(.2, .8),
                    rng.uniform(-.35, .35),
                )
        for x in range(5, 195):
            y = int(100 + math.sin(x / 17) * 2)
            terrain[(x, y)] = "road"
            terrain[(x, y + 1)] = "road"
            self.terrain_details.pop((x, y), None)
            self.terrain_details.pop((x, y + 1), None)
        return terrain

    def add_unit(self, kind, team, x, y):
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

    def recruit(self, kind, team="green"):
        cost = UNIT_COSTS[kind]
        wallet = self.essence if team == "green" else self.enemy_essence
        if wallet < cost:
            if team == "green":
                self.message, self.message_time = "Not enough essence", 1.5
            return False
        if team == "green":
            self.essence -= cost
            base, direction = self.player_base, 1
        else:
            self.enemy_essence -= cost
            base, direction = self.enemy_base, -1
        count = sum(u.team == team for u in self.units)
        y = base.y + 1.5 + (count % 4) * 1.25
        u = self.add_unit(kind, team, base.x + direction * 4, y)
        return True

    def select_kind(self, kind=None):
        for u in self.units:
            u.selected = u.team == "green" and (kind is None or u.kind == kind)

    def issue_order(self, world):
        selected = [u for u in self.units if u.selected and u.team == "green"]
        if not selected:
            return
        visible_enemies = [u for u in self.units if u.team == "red" and self.is_visible(u.x, u.y)]
        candidates = visible_enemies + ([self.enemy_base] if self.is_visible(self.enemy_base.x, self.enemy_base.y) else [])
        clicked = min(candidates, key=lambda e: dist((e.x, e.y), world), default=None)
        if clicked and dist((clicked.x, clicked.y), world) < 1.5:
            for u in selected:
                u.target, u.target_pos = clicked, (clicked.x, clicked.y)
            return
        cols = math.ceil(math.sqrt(len(selected)))
        for i, u in enumerate(selected):
            offset = ((i % cols - (cols - 1) / 2) * 1.15, (i // cols) * 1.15)
            u.target = None
            u.target_pos = (clamp(world[0] + offset[0], .5, 199.5), clamp(world[1] + offset[1], .5, 199.5))

    def currently_visible_enemy(self, enemy):
        return self.is_visible(enemy.x, enemy.y)

    def is_visible(self, x, y):
        return (int(x), int(y)) in self.visible

    def update_visibility(self):
        previous_visible = self.visible.copy()
        previous_explored_count = len(self.explored)
        self.visible.clear()
        sources = [(self.player_base.x, self.player_base.y, 12)]
        sources += [(u.x, u.y, 8) for u in self.units if u.team == "green"]
        for sx, sy, radius in sources:
            for x in range(max(0, int(sx - radius)), min(MAP_SIZE, int(sx + radius) + 1)):
                for y in range(max(0, int(sy - radius)), min(MAP_SIZE, int(sy + radius) + 1)):
                    if (x - sx) ** 2 + (y - sy) ** 2 <= radius ** 2:
                        self.visible.add((x, y))
        self.explored.update(self.visible)
        if self.visible != previous_visible or len(self.explored) != previous_explored_count:
            self._fog_revision += 1

    def find_target(self, unit):
        opponents = [u for u in self.units if u.team != unit.team and u.health > 0]
        enemy_base = self.enemy_base if unit.team == "green" else self.player_base
        if unit.team == "green":
            opponents = [u for u in opponents if self.currently_visible_enemy(u)]
        in_range = [e for e in opponents if dist((unit.x, unit.y), (e.x, e.y)) <= unit.attack_range]
        if dist((unit.x, unit.y), (enemy_base.x, enemy_base.y)) <= unit.attack_range + 2.5:
            in_range.append(enemy_base)
        return min(in_range, key=lambda e: dist((unit.x, unit.y), (e.x, e.y)), default=None)

    def attack(self, attacker, target):
        target.health -= attacker.damage
        target.flash = .12
        attacker.attack_timer = attacker.cooldown
        if attacker.kind == "archer":
            self.arrows.append([attacker.x, attacker.y, target.x, target.y, .22, attacker.team])
        else:
            mx, my = (attacker.x + target.x) / 2, (attacker.y + target.y) / 2
            self.particles.append([mx, my, .25, attacker.team])

    def update_unit(self, u, dt):
        u.attack_timer = max(0, u.attack_timer - dt)
        u.flash = max(0, u.flash - dt)
        target = u.target
        if target is not None and getattr(target, "health", 0) <= 0:
            u.target = target = None
        auto = self.enemy_ai.choose_target(u) if u.team == "red" else self.find_target(u)
        if auto is not None:
            target = auto
            u.target = auto
        tactical_pos = (
            self.enemy_ai.tactical_destination(u, dt) if u.team == "red" else None
        )
        if tactical_pos is not None:
            dx, dy = tactical_pos[0] - u.x, tactical_pos[1] - u.y
            d = math.hypot(dx, dy)
            if d < .08:
                u.tactical_pos = None
                # Negligible local corrections must not consume the whole update.
                # Otherwise stable formations continually recompute tiny
                # separation moves and never resume their strategic order.
            else:
                step = min(d, u.speed * dt)
                u.x = clamp(u.x + dx / d * step, .5, MAP_SIZE - .5)
                u.y = clamp(u.y + dy / d * step, .5, MAP_SIZE - .5)
                return
        if target is not None:
            target_range = u.attack_range + (2.3 if isinstance(target, Base) else 0)
            d = dist((u.x, u.y), (target.x, target.y))
            if d <= target_range:
                if u.attack_timer <= 0:
                    self.attack(u, target)
                return
            u.target_pos = (target.x, target.y)
        if u.target_pos:
            dx, dy = u.target_pos[0] - u.x, u.target_pos[1] - u.y
            d = math.hypot(dx, dy)
            if d < .08:
                u.target_pos = None
            else:
                step = min(d, u.speed * dt)
                u.x = clamp(u.x + dx / d * step, .5, 199.5)
                u.y = clamp(u.y + dy / d * step, .5, 199.5)

    def update(self, dt):
        if self.state != "playing" or self.winner:
            return
        self.message_time = max(0, self.message_time - dt)
        self.essence += 20 * dt
        self.enemy_essence += 20 * dt
        self.enemy_ai.update(dt)
        for u in list(self.units):
            self.update_unit(u, dt)
        self.units[:] = [u for u in self.units if u.health > 0]
        living_targets = self.units + [self.player_base, self.enemy_base]
        for unit in self.units:
            if unit.target is not None and (
                unit.target not in living_targets
                or getattr(unit.target, "health", 0) <= 0
            ):
                unit.target = None
        for a in self.arrows:
            a[4] -= dt
        self.arrows[:] = [a for a in self.arrows if a[4] > 0]
        for p in self.particles:
            p[2] -= dt
        self.particles[:] = [p for p in self.particles if p[2] > 0]
        self.reveal_tick -= dt
        if self.reveal_tick <= 0:
            self.update_visibility()
            self.reveal_tick = .12
        if self.enemy_base.health <= 0:
            self.winner = "VICTORY"
        elif self.player_base.health <= 0:
            self.winner = "DEFEAT"

    def draw_terrain(self):
        w, h = self.screen.get_size()
        view_h = h - HUD_H
        self.screen.fill((70, 101, 55))
        left, top = self.screen_to_world((0, 0))
        right, bottom = self.screen_to_world((w, view_h))
        x0, x1 = math.floor(left) - 1, math.ceil(right) + 1
        y0, y1 = math.floor(top) - 1, math.ceil(bottom) + 1
        tile = max(1, int(self.zoom + 1))
        for x in range(x0, x1):
            for y in range(y0, y1):
                sx, sy = self.world_to_screen(x, y)
                tone = self.terrain_tones.get((x, y), 0)
                color = tuple(channel + tone for channel in GROUND_COLOR)
                kind = self.terrain.get((x, y))
                if kind == "road": color = (137, 118, 77)
                pygame.draw.rect(self.screen, color, (int(sx), int(sy), tile, tile))
                detail = self.terrain_details.get((x, y))
                if self.zoom >= TERRAIN_DETAIL_MIN_ZOOM and detail:
                    detail_kind, ox, oy, angle = detail
                    cx = round(sx + self.zoom * ox)
                    cy = round(sy + self.zoom * oy)
                    if detail_kind == "tuft":
                        length = max(2, round(self.zoom * .24))
                        color = (55, 91, 48)
                        pygame.draw.line(self.screen, color, (cx, cy), (cx - 1, cy - length), 1)
                        pygame.draw.line(self.screen, color, (cx, cy), (cx + 2, cy - length + 1), 1)
                    elif detail_kind == "stone":
                        radius = max(1, round(self.zoom * .11))
                        pygame.draw.circle(self.screen, (96, 99, 84), (cx, cy), radius)
                        pygame.draw.circle(self.screen, (123, 124, 103), (cx - 1, cy - 1), 1)
                    else:
                        width = max(3, round(self.zoom * .38))
                        height = max(2, round(self.zoom * .17))
                        patch = pygame.Surface((width, height), pygame.SRCALPHA)
                        pygame.draw.ellipse(patch, (111, 92, 57, 75), patch.get_rect())
                        rotated = pygame.transform.rotate(patch, math.degrees(angle))
                        self.screen.blit(rotated, rotated.get_rect(center=(cx, cy)))
        border = self.world_to_screen(0, 0)
        pygame.draw.rect(self.screen, (39, 54, 35), (border[0], border[1], MAP_SIZE * self.zoom, MAP_SIZE * self.zoom), max(2, int(self.zoom * .15)))

    def draw_base(self, base):
        if base.team == "red" and not self.is_visible(base.x, base.y):
            return
        color = GREEN if base.team == "green" else RED
        sx, sy = self.world_to_screen(base.x - 2.5, base.y - 2.5)
        size = 5 * self.zoom
        r = pygame.Rect(int(sx), int(sy), int(size), int(size))
        pygame.draw.rect(self.screen, (43, 39, 34), r, border_radius=max(2, int(self.zoom * .25)))
        inset = r.inflate(-int(self.zoom * .7), -int(self.zoom * .7))
        pygame.draw.rect(self.screen, color if base.flash <= 0 else CREAM, inset, border_radius=3)
        # Corner towers and keep roof.
        for px, py in ((r.left, r.top), (r.right, r.top), (r.left, r.bottom), (r.right, r.bottom)):
            pygame.draw.circle(self.screen, (67, 63, 54), (px, py), max(3, int(self.zoom * .42)))
        roof = [(r.centerx, r.top + int(size * .16)), (r.left + int(size * .22), r.centery), (r.right - int(size * .22), r.centery)]
        pygame.draw.polygon(self.screen, (39, 76, 45) if base.team == "green" else (105, 38, 34), roof)
        # Health bar.
        bar = pygame.Rect(r.left, r.top - 10, r.width, 6)
        pygame.draw.rect(self.screen, (42, 32, 31), bar, border_radius=3)
        fill = bar.copy(); fill.width = int(bar.width * max(0, base.health / base.max_health))
        pygame.draw.rect(self.screen, color, fill, border_radius=3)

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

    def draw_unit(self, u):
        if u.team == "red" and not self.is_visible(u.x, u.y):
            return
        sx, sy = self.world_to_screen(u.x, u.y)
        size = max(8, int(self.zoom * 1.55))
        rect = pygame.Rect(0, 0, size, size)
        rect.center = (round(sx), round(sy))
        color = GREEN if u.team == "green" else RED
        if u.flash > 0: color = CREAM
        if u.selected:
            pygame.draw.circle(self.screen, GOLD, rect.center, int(size * .68), max(1, size // 9))
        pygame.draw.rect(self.screen, (32, 31, 28), rect.inflate(2, 2), border_radius=max(2, size // 4))
        pygame.draw.rect(self.screen, color, rect, border_radius=max(2, size // 4))
        if u.kind == "swordsman":
            blade_start = (rect.left + size * .34, rect.bottom - size * .3)
            blade_end = (rect.right - size * .16, rect.top + size * .16)
            pygame.draw.line(self.screen, (225, 223, 202), blade_start, blade_end, max(2, size // 7))
            pygame.draw.line(
                self.screen,
                (92, 65, 39),
                (rect.left + size * .2, rect.centery + size * .05),
                (rect.centerx + size * .06, rect.bottom - size * .2),
                max(2, size // 9),
            )
            pygame.draw.line(
                self.screen,
                (92, 65, 39),
                (rect.left + size * .25, rect.centery - size * .04),
                (rect.centerx + size * .02, rect.centery + size * .2),
                max(2, size // 10),
            )
        else:
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

    def draw_fog(self):
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
        pygame.draw.circle(self.screen, (92, 188, 205), (34, top + 29), 12)
        self.screen.blit(self.font.render(f"{int(self.essence):,} essence", True, CREAM), (55, top + 18))
        self.screen.blit(self.small.render("+20 each second", True, (172, 158, 128)), (55, top + 44))
        sword_btn = Button((245, top + 16, 180, 62), "Raise Swordsman", "200 essence  •  [S]")
        archer_btn = Button(
            (440, top + 16, 180, 62),
            "Raise Archer",
            "500 essence  •  [A]",
            disabled_text=(190, 184, 169),
            disabled_sub=(168, 160, 145),
        )
        sword_btn.draw(self.screen, pygame.mouse.get_pos(), self.button_font, self.button_cost_font, self.essence >= 200)
        archer_btn.draw(self.screen, pygame.mouse.get_pos(), self.button_font, self.button_cost_font, self.essence >= 500)
        self.hud_buttons = [(sword_btn, "swordsman"), (archer_btn, "archer")]
        counts = {k: sum(u.team == "green" and u.kind == k for u in self.units) for k in ("swordsman", "archer")}
        selected = sum(u.selected for u in self.units)
        info = f"Army: {counts['swordsman']} swordsmen  •  {counts['archer']} archers  •  {selected} selected"
        self.screen.blit(self.small.render(info, True, (190, 180, 153)), (245, top + 86))
        controls = "[1] All swords   [2] All archers   [3] All army   •   Right-click: order"
        label = self.small.render(controls, True, (165, 155, 132))
        self.screen.blit(label, (w - label.get_width() - 20, top + 90))
        # Base vitality at right.
        self.screen.blit(self.small.render("VERDANT KEEP", True, (165, 198, 165)), (w - 210, top + 18))
        self.screen.blit(self.font.render(f"{max(0, int(self.player_base.health))} / 250", True, CREAM), (w - 210, top + 39))

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
        lore = self.font.render("Raise your banners. Break the Crimson Hold.", True, (191, 181, 152))
        self.screen.blit(lore, (w // 2 - lore.get_width() // 2, 294))
        self.play_btn.rect.center = (w // 2, h // 2 + 110)
        self.play_btn.draw(self.screen, pygame.mouse.get_pos(), self.button_font, self.button_cost_font)
        hint = self.small.render("Mouse + keyboard  •  Press Play to begin", True, (200, 190, 160))
        self.screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 80))

    def draw_game(self):
        self.draw_terrain()
        self.draw_base(self.player_base); self.draw_base(self.enemy_base)
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
            sub = self.font.render("Press R to fight again  •  Esc for menu", True, CREAM)
            self.screen.blit(sub, sub.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 35)))

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
        keys = pygame.key.get_pressed(); mx, my = pygame.mouse.get_pos(); w, h = self.screen.get_size()
        speed = 25 * dt * (13 / self.zoom)
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT] or mx > w - 5) - (keys[pygame.K_a] or keys[pygame.K_LEFT] or mx < 5)
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN] or my > h - HUD_H - 5) - (keys[pygame.K_w] or keys[pygame.K_UP] or my < 5)
        self.camera[0] = clamp(self.camera[0] + dx * speed, 0, MAP_SIZE)
        self.camera[1] = clamp(self.camera[1] + dy * speed, 0, MAP_SIZE)

    def handle_game_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1: self.select_kind("swordsman")
            elif event.key == pygame.K_2: self.select_kind("archer")
            elif event.key == pygame.K_3: self.select_kind()
            elif event.key == pygame.K_s: self.recruit("swordsman")
            elif event.key == pygame.K_a: self.recruit("archer")
            elif event.key == pygame.K_SPACE: self.camera[:] = [self.player_base.x, self.player_base.y]
            elif event.key == pygame.K_r and self.winner: self.reset()
            elif event.key == pygame.K_ESCAPE:
                self.state = "menu" if self.winner else "paused"
        elif event.type == pygame.MOUSEWHEEL:
            old_world = self.screen_to_world(pygame.mouse.get_pos())
            self.zoom = clamp(self.zoom * (1.13 ** event.y), 5, 30)
            new_world = self.screen_to_world(pygame.mouse.get_pos())
            self.camera[0] += old_world[0] - new_world[0]; self.camera[1] += old_world[1] - new_world[1]
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
                friends = [u for u in self.units if u.team == "green"]
                hit = min(friends, key=lambda u: dist((u.x, u.y), world), default=None)
                if hit and dist((hit.x, hit.y), world) < .9: hit.selected = True
            else:
                for u in self.units:
                    if u.team == "green" and rect.collidepoint(self.world_to_screen(u.x, u.y)): u.selected = True
            self.drag_start = self.drag_now = None

    def run(self):
        running = True
        while running:
            dt = min(.05, self.clock.tick(FPS) / 1000)
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                elif self.state == "menu":
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.play_btn.rect.collidepoint(event.pos):
                        self.reset(); self.state = "playing"; self.update_visibility()
                    elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.reset(); self.state = "playing"; self.update_visibility()
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
            else:
                self.draw_menu()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
