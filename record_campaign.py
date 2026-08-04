#!/usr/bin/env python3
"""State-aware player used to record the five-level campaign."""

from __future__ import annotations

import argparse
import os
import random
import time

if "--headless" in os.sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main


SIM_STEP = 0.05
RENDER_FPS = 30
SIM_STEPS_PER_FRAME = 10
MAX_LEVEL_SECONDS = {1: 180, 2: 600, 3: 2400, 4: 1800, 5: 1800}
SHOWCASE_SECONDS = {1: 180, 2: 380, 3: 650, 4: 520, 5: 650}


class CampaignBot:
    """Recruit and issue ordinary player orders using live game state."""

    TARGET_SHARES = {
        1: {"swordsman": 1.0},
        2: {"swordsman": 0.35, "archer": 0.65},
        3: {"swordsman": 0.20, "archer": 0.40, "shield": 0.40},
        4: {"swordsman": 0.15, "archer": 0.55, "shield": 0.30},
        5: {"swordsman": 0.20, "archer": 0.40, "shield": 0.40},
    }

    RALLY_VALUE = {1: 0, 2: 8000, 3: 12000, 4: 10000, 5: 6500}

    def __init__(self, game: main.Game, level: int):
        self.game = game
        self.level = level
        self.elapsed = 0.0
        self.next_recruit = 0.0
        self.next_order = 0.0
        self.assault_started = False
        self.current_checkpoint_uid = None
        self.objective = None
        self.status = "Gathering the Verdant army"
        self.next_report = 100.0
        self.march_x = None
        self.assault_uids = set()
        self.home_threat_seen = False
        self.flank_index = 0

    def army(self):
        return [
            unit for unit in self.game.units
            if unit.team == "green" and unit.is_player_commandable
        ]

    def army_value(self):
        return sum(main.UNIT_COSTS.get(unit.kind, 300) for unit in self.army())

    def assault_value(self):
        return sum(
            main.UNIT_COSTS.get(unit.kind, 300)
            for unit in self.army()
            if unit.uid in self.assault_uids
        )

    def threats_to_king(self):
        king = self.game.team_king("green")
        if king is None:
            return []
        return sorted(
            (
                unit for unit in self.game.units
                if self.game.teams_hostile("green", unit.team)
                and unit.health > 0
                and main.dist((unit.x, unit.y), (king.x, king.y)) <= 20
            ),
            key=lambda unit: main.dist((unit.x, unit.y), (king.x, king.y)),
        )

    def choose_recruit(self):
        available = list(self.game.level.player_units)
        investment = {kind: 0 for kind in self.game.level.player_units}
        for unit in self.army():
            if unit.kind in investment:
                investment[unit.kind] += main.UNIT_COSTS[unit.kind]
        shares = self.TARGET_SHARES[self.level]

        def projected_error(kind):
            projected = dict(investment)
            projected[kind] += main.UNIT_COSTS[kind]
            total = sum(projected.values()) or 1
            return sum(
                abs(projected[candidate] / total - shares[candidate])
                for candidate in projected
            )

        preferred = min(
            available, key=lambda kind: (projected_error(kind), kind)
        )
        if self.game.essence < main.UNIT_COSTS[preferred]:
            return None
        return preferred

    def recruit(self):
        # Spend available gold through the same recruit method as HUD buttons.
        while True:
            kind = self.choose_recruit()
            if kind is None or not self.game.recruit(kind):
                break

    def checkpoint_target(self):
        current = self.game.checkpoint_by_uid(self.current_checkpoint_uid)
        red_owned = [cp for cp in self.game.checkpoints if cp.owner == "red"]
        if current is not None and current.owner == "red":
            return current
        remaining = red_owned or [
            cp for cp in self.game.checkpoints if cp.owner != "green"
        ]
        if current is not None and current.owner != "green" and not red_owned:
            return current
        if not remaining:
            self.current_checkpoint_uid = None
            return None
        army = self.army()
        if army:
            origin = (
                sum(unit.x for unit in army) / len(army),
                sum(unit.y for unit in army) / len(army),
            )
        else:
            king = self.game.team_king("green")
            origin = (king.x, king.y)
        target = min(
            remaining,
            key=lambda cp: (main.dist(origin, (cp.x, cp.y)), cp.uid),
        )
        self.current_checkpoint_uid = target.uid
        return target

    def choose_objective(self):
        value = self.army_value()
        reset_value = (
            int(
                self.RALLY_VALUE[self.level]
                * (0.5 if self.level == 4 else 0.75)
            )
            if self.level >= 4 else 3500
        )
        committed_value = (
            self.assault_value()
            if self.level >= 4 and self.assault_started else value
        )
        if (
            self.level >= 3
            and self.assault_started
            and committed_value < reset_value
        ):
            self.assault_started = False
            self.march_x = None
            self.assault_uids.clear()
            self.flank_index = 0
        waiting_for_first_defense = (
            self.level == 3 and self.game.enemy_ai.failed_waves < 1
        ) or (self.level >= 4 and not self.home_threat_seen)
        threats = self.threats_to_king()
        if threats:
            self.home_threat_seen = True
        should_defend = (
            self.level < 4
            and (
                self.level >= 3
                or value < self.RALLY_VALUE[self.level]
                or waiting_for_first_defense
            )
        ) or (self.level >= 4 and not self.assault_started)
        if threats and should_defend:
            king = self.game.team_king("green")
            self.status = "Defending the Verdant King"
            if self.level >= 3:
                return threats[0].x, threats[0].y
            # Hold a line inside the royal guards' leash. Ground-ordering here
            # lets attack-move acquire raiders without chasing each one back
            # across the map and feeding the next wave.
            return king.x - 2, king.y

        if not self.assault_started and (
            value < self.RALLY_VALUE[self.level] or waiting_for_first_defense
        ):
            king = self.game.team_king("green")
            self.status = f"Rallying army — {value:,} gold fielded"
            return (king.x - 2, king.y) if self.level == 2 else (king.x, king.y)
        self.assault_started = True
        if self.level >= 4 and not self.assault_uids:
            reserve_value = 2000 if self.level == 4 else 2500
            commit_target = max(0, self.army_value() - reserve_value)
            committed_value = 0
            for unit in sorted(self.army(), key=lambda candidate: candidate.uid):
                unit_value = main.UNIT_COSTS.get(unit.kind, 300)
                if committed_value >= commit_target:
                    break
                self.assault_uids.add(unit.uid)
                committed_value += unit_value

        if self.level == 1:
            enemies = [
                unit for unit in self.game.units
                if self.game.teams_hostile("green", unit.team) and unit.health > 0
            ]
            if enemies:
                self.status = "Breaking the Crimson ambush"
                return (
                    sum(unit.x for unit in enemies) / len(enemies),
                    sum(unit.y for unit in enemies) / len(enemies),
                )

        if self.level == 5:
            checkpoint = self.checkpoint_target()
            if checkpoint is not None:
                self.status = (
                    f"Assaulting {checkpoint.native_faction.replace('_', ' ').title()} hold"
                )
                return checkpoint.x, checkpoint.y

        if self.level == 4:
            flank = [(45.0, 40.0), (112.0, 40.0)]
            committed = [
                unit for unit in self.army()
                if unit.uid in self.assault_uids
            ]
            if committed and self.flank_index < len(flank):
                center = (
                    sum(unit.x for unit in committed) / len(committed),
                    sum(unit.y for unit in committed) / len(committed),
                )
                if main.dist(center, flank[self.flank_index]) < 8:
                    self.flank_index += 1
            if self.flank_index < len(flank):
                self.status = "Flanking the Crimson host"
                return flank[self.flank_index]

        red_king = self.game.team_king("red")
        if red_king is not None:
            if self.level == 3:
                green_king = self.game.team_king("green")
                if self.march_x is None:
                    self.march_x = green_king.x + 24
                army = self.army()
                center_x = sorted(unit.x for unit in army)[len(army) // 2]
                if center_x >= self.march_x - 5:
                    self.march_x = min(red_king.x, self.march_x + 20)
                if self.march_x < red_king.x:
                    self.status = "Advancing the Verdant battle line"
                    return self.march_x, main.MAP_CENTER
            self.status = "Marching on the Crimson King"
            return red_king.x, red_king.y
        return main.RED_KING_POSITION

    def issue_order(self):
        if not self.army():
            return
        self.objective = self.choose_objective()
        if self.level >= 4 and self.assault_started and self.assault_uids:
            for unit in self.game.units:
                unit.selected = (
                    unit.is_player_commandable
                    and unit.uid in self.assault_uids
                )
        else:
            self.game.select_kind()
        self.game.issue_order(self.objective)
        if self.level >= 4 and self.assault_started:
            threats = self.threats_to_king()
            if threats:
                for unit in self.game.units:
                    unit.selected = (
                        unit.is_player_commandable
                        and unit.uid not in self.assault_uids
                    )
                self.game.issue_order((threats[0].x, threats[0].y))

    def update(self, dt):
        self.elapsed += dt
        if self.elapsed + 1e-9 >= self.next_recruit:
            self.recruit()
            self.next_recruit = self.elapsed + 0.5
        if self.elapsed + 1e-9 >= self.next_order:
            self.issue_order()
            self.next_order = self.elapsed + 8.0
        if self.elapsed + 1e-9 >= self.next_report:
            army = self.army()
            print(
                f"progress level={self.level} time={self.elapsed:.0f} "
                f"army={len(army)} value={self.army_value()} "
                f"x={min((u.x for u in army), default=0):.0f}-"
                f"{max((u.x for u in army), default=0):.0f} "
                f"status={self.status} "
                f"holds={[cp.owner for cp in self.game.checkpoints]}",
                flush=True,
            )
            self.next_report += 100.0

    def update_camera(self):
        army = self.army()
        if not army:
            return
        # Follow the forward half of the army so battles stay visible while
        # reinforcements continue to arrive from the keep.
        objective = self.objective or (army[0].x, army[0].y)
        ranked = sorted(
            army,
            key=lambda unit: main.dist((unit.x, unit.y), objective),
        )
        focus_units = ranked[: max(1, (len(ranked) + 1) // 2)]
        focus = (
            sum(unit.x for unit in focus_units) / len(focus_units),
            sum(unit.y for unit in focus_units) / len(focus_units),
        )
        self.game.camera[:] = focus
        self.game.clamp_camera()


def level_summary(game, bot):
    counts = {
        kind: sum(
            unit.team == "green" and unit.kind == kind
            for unit in game.units
        )
        for kind in main.UNIT_KINDS
    }
    holds = sum(cp.owner == "green" for cp in game.checkpoints)
    red_counts = {
        kind: sum(unit.team == "red" and unit.kind == kind for unit in game.units)
        for kind in (*main.UNIT_KINDS, "king", "knight")
    }
    green_king = game.team_king("green")
    red_king = game.team_king("red")
    army_units = [
        unit for unit in game.units
        if unit.team == "green" and unit.is_player_commandable
    ]
    green_span = (
        f"{min((unit.x for unit in army_units), default=0):.0f}-"
        f"{max((unit.x for unit in army_units), default=0):.0f}"
    )
    return (
        f"level={bot.level} result={game.winner or 'TIMEOUT'} "
        f"time={bot.elapsed:.1f}s army={counts} red={red_counts} "
        f"kings={getattr(green_king, 'health', 0):.0f}/"
        f"{getattr(red_king, 'health', 0):.0f} "
        f"green_x={green_span} ai={getattr(game.enemy_ai.state, 'name', '?')} "
        f"holds={holds}/{len(game.checkpoints)}"
    )


def run_level(game, level, render, time_limit=None):
    seed = 8675309 + level * 1009
    game.start_level(level, terrain_seed=seed)
    game.state = "playing"
    game.fog_of_war_enabled = True
    game.zoom = {1: 30.0, 2: 12.0, 3: 13.0, 4: 10.0, 5: 10.0}[level]
    game.clamp_camera()
    game.update_visibility()
    bot = CampaignBot(game, level)
    clock = pygame.time.Clock()
    time_limit = time_limit or MAX_LEVEL_SECONDS[level]
    sim_step = SIM_STEP
    while game.winner is None and bot.elapsed < time_limit:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
        steps = SIM_STEPS_PER_FRAME if render else 1
        for _ in range(steps):
            bot.update(sim_step)
            game.update(sim_step)
            if game.winner:
                break
        if render:
            bot.update_camera()
            if game.message_time <= 0:
                game.message = f"Codex Commander • {bot.status}"
                game.message_time = 0.3
            game.draw_game()
            pygame.display.flip()
            clock.tick(RENDER_FPS)
    print(level_summary(game, bot), flush=True)
    if render:
        if game.winner is None:
            game.message = "Gameplay segment complete"
            game.message_time = 3.0
        for _ in range(RENDER_FPS * 3):
            game.draw_game()
            pygame.display.flip()
            clock.tick(RENDER_FPS)
    return game.winner


def show_level_card(game, level):
    game.state = "level_select"
    game.selected_level_page = level
    clock = pygame.time.Clock()
    for _ in range(RENDER_FPS * 2):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
        game.draw_level_select()
        pygame.display.flip()
        clock.tick(RENDER_FPS)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--showcase", action="store_true")
    parser.add_argument(
        "--levels", nargs="+", type=int, default=[1, 2, 3, 4, 5]
    )
    return parser.parse_args()


def main_loop():
    args = parse_args()
    random.seed(17)
    game = main.Game(enemy_rng=random.Random(73), terrain_seed=8675309)
    for level in args.levels:
        attempt = 0
        while True:
            attempt += 1
            if not args.headless:
                show_level_card(game, level)
            if attempt > 1:
                print(f"retry level={level} attempt={attempt}", flush=True)
            limit = SHOWCASE_SECONDS[level] if args.showcase else None
            result = run_level(game, level, not args.headless, limit)
            if result == "VICTORY" or args.showcase:
                break
    if not args.headless:
        time.sleep(1)
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main_loop())
