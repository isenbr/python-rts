#!/usr/bin/env python3
"""Run a configurable unit matchup in a visible Pygame window."""

import argparse
import random
from collections import Counter

import pygame

from main import FPS, UNIT_COSTS, UNIT_KINDS, Game, dist


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", choices=UNIT_KINDS, required=True)
    parser.add_argument("--right", choices=UNIT_KINDS, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--budget",
        type=int,
        default=6000,
        help="Essence available to each side (default: 6000).",
    )
    group.add_argument(
        "--counts",
        nargs=2,
        type=int,
        metavar=("LEFT", "RIGHT"),
        help="Use exact unit counts instead of an equal essence budget.",
    )
    parser.add_argument(
        "--archer-min-range",
        type=float,
        default=0,
        help="Minimum distance at which an archer may shoot (default: 0).",
    )
    parser.add_argument(
        "--shield-cooldown",
        type=float,
        default=None,
        help="Override the shield attack cooldown in seconds.",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--speed",
        type=float,
        default=1,
        help="Initial simulation speed multiplier (default: 1).",
    )
    args = parser.parse_args()
    if args.counts and min(args.counts) <= 0:
        parser.error("--counts values must be positive")
    if args.budget is not None and args.budget <= 0:
        parser.error("--budget must be positive")
    if args.archer_min_range < 0:
        parser.error("--archer-min-range cannot be negative")
    if args.shield_cooldown is not None and args.shield_cooldown <= 0:
        parser.error("--shield-cooldown must be positive")
    if args.speed <= 0:
        parser.error("--speed must be positive")
    return args


class VisualMatchup:
    FIXED_STEP = 1 / 60
    SPEEDS = (0.25, 0.5, 1, 2, 4, 8)

    def __init__(self, args):
        self.args = args
        self.paused = False
        self.speed = min(self.SPEEDS, key=lambda value: abs(value - args.speed))
        self.elapsed = 0.0
        self.accumulator = 0.0
        self.result = None
        self.reset()

    def counts(self):
        if self.args.counts:
            return tuple(self.args.counts)
        return (
            self.args.budget // UNIT_COSTS[self.args.left],
            self.args.budget // UNIT_COSTS[self.args.right],
        )

    def reset(self):
        self.game = Game(enemy_rng=random.Random(self.args.seed))
        self.game.state = "playing"
        self.game.units.clear()
        self.game.enemy_ai._known_red_uids.clear()
        self.game.enemy_ai.update = lambda dt: None
        self.game.enemy_ai.tactical_destination = lambda unit, dt: None
        self._install_minimum_range()
        self.game.enemy_ai.choose_target = lambda unit: self.game.find_target(unit)
        self.elapsed = 0.0
        self.accumulator = 0.0
        self.result = None
        self.paused = False
        self._add_armies()
        self.game.camera[:] = [54, 60]
        self.game.zoom = 18
        self.game.update_visibility()

    def _install_minimum_range(self):
        minimum = self.args.archer_min_range
        if minimum <= 0:
            return
        original_find_target = self.game.find_target
        original_attack = self.game.attack

        def find_target(unit):
            if unit.kind != "archer":
                return original_find_target(unit)
            candidates = [
                enemy
                for enemy in self.game.units
                if enemy.team != unit.team
                and enemy.health > 0
                and (
                    unit.team != "green"
                    or self.game.currently_visible_enemy(enemy)
                )
                and minimum
                <= dist((unit.x, unit.y), (enemy.x, enemy.y))
                <= unit.attack_range
            ]
            return min(
                candidates,
                key=lambda enemy: dist(
                    (unit.x, unit.y), (enemy.x, enemy.y)
                ),
                default=None,
            )

        def attack(attacker, target):
            if (
                attacker.kind == "archer"
                and dist((attacker.x, attacker.y), (target.x, target.y))
                < minimum
            ):
                return
            original_attack(attacker, target)

        self.game.find_target = find_target
        self.game.attack = attack

    def _add_armies(self):
        left_count, right_count = self.counts()
        center_y = 60
        spacing = min(1.0, 18 / max(left_count, right_count))
        for index in range(left_count):
            y = center_y + (index - (left_count - 1) / 2) * spacing
            unit = self.game.add_unit(self.args.left, "green", 48, y)
            unit.target_pos = (60, center_y)
            self._apply_unit_overrides(unit)
        for index in range(right_count):
            y = center_y + (index - (right_count - 1) / 2) * spacing
            unit = self.game.add_unit(self.args.right, "red", 60, y)
            unit.target_pos = (48, center_y)
            self._apply_unit_overrides(unit)

    def _apply_unit_overrides(self, unit):
        if unit.kind == "shield" and self.args.shield_cooldown is not None:
            unit.cooldown = self.args.shield_cooldown

    def update(self, real_dt):
        if self.paused or self.result:
            return
        self.accumulator += real_dt * self.speed
        while self.accumulator >= self.FIXED_STEP and not self.result:
            self._step(self.FIXED_STEP)
            self.accumulator -= self.FIXED_STEP

    def _step(self, dt):
        for unit in list(self.game.units):
            if unit.health > 0:
                self.game.update_unit(unit, dt)
        self.game.units[:] = [
            unit for unit in self.game.units if unit.health > 0
        ]
        self.game.update_visibility()
        self.elapsed += dt
        teams = {unit.team for unit in self.game.units}
        if len(teams) < 2:
            survivors = Counter(unit.kind for unit in self.game.units)
            winner = next(iter(survivors), "draw") if survivors else "draw"
            self.result = winner, survivors

    def change_speed(self, direction):
        index = self.SPEEDS.index(self.speed)
        index = max(0, min(len(self.SPEEDS) - 1, index + direction))
        self.speed = self.SPEEDS[index]

    def draw(self):
        left_count, right_count = self.counts()
        if self.result:
            winner, survivors = self.result
            status = (
                f"RESULT: {winner.title()} win | Survivors {dict(survivors)} "
                f"| {self.elapsed:.2f}s"
            )
        else:
            state = "PAUSED" if self.paused else "RUNNING"
            status = (
                f"{left_count} {self.args.left.title()} vs "
                f"{right_count} {self.args.right.title()} | {state} "
                f"| {self.speed:g}x | {self.elapsed:.2f}s"
            )
        self.game.message = status
        self.game.message_time = 1
        self.game.draw_game()
        controls = self.game.small.render(
            "Space: pause  R: restart  [ / ]: speed  Esc: quit",
            True,
            (238, 230, 201),
        )
        panel = controls.get_rect(
            bottomright=(
                self.game.screen.get_width() - 16,
                self.game.screen.get_height() - 10,
            )
        ).inflate(16, 8)
        pygame.draw.rect(
            self.game.screen, (28, 27, 24), panel, border_radius=6
        )
        self.game.screen.blit(controls, controls.get_rect(center=panel.center))
        pygame.display.flip()

    def run(self):
        clock = pygame.time.Clock()
        while True:
            real_dt = min(clock.tick(FPS) / 1000, 0.1)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type != pygame.KEYDOWN:
                    continue
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_r:
                    self.reset()
                elif event.key == pygame.K_LEFTBRACKET:
                    self.change_speed(-1)
                elif event.key == pygame.K_RIGHTBRACKET:
                    self.change_speed(1)
            self.update(real_dt)
            self.draw()


if __name__ == "__main__":
    VisualMatchup(parse_args()).run()
