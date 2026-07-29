import math
import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    GUARD_LEASH_DISTANCE,
    WORLD_MAX,
    WORLD_MIN,
    Game,
    dist,
)


class SharedSeparationTests(unittest.TestCase):
    def game(self):
        game = Game(enemy_rng=random.Random(17))
        game.state = "playing"
        game.enemy_ai.recruitment_timer = 999
        game.units.clear()
        return game

    @staticmethod
    def advance_units(game, units, dt, seconds=2.0):
        for _ in range(round(seconds / dt)):
            game.rebuild_unit_spatial_hash()
            game._movement_snapshot_active = True
            try:
                for unit in units:
                    game.update_unit(unit, dt)
            finally:
                game._movement_snapshot_active = False

    def test_green_and_red_units_share_separation(self):
        for team in ("green", "red"):
            with self.subTest(team=team):
                game = self.game()
                units = [
                    game.add_unit("swordsman", team, 20, 20),
                    game.add_unit("swordsman", team, 20, 20),
                ]
                self.advance_units(game, units, 1 / 60)
                self.assertGreater(dist(
                    (units[0].x, units[0].y), (units[1].x, units[1].y)
                ), .95)

    def test_mixed_teams_resolve_overlap_outside_melee(self):
        game = self.game()
        green = game.add_unit("archer", "green", 20, 20)
        red = game.add_unit("archer", "red", 20, 20)
        green.attack_timer = red.attack_timer = 999

        self.advance_units(game, (green, red), 1 / 60)

        self.assertGreater(dist((green.x, green.y), (red.x, red.y)), .95)

    def test_exact_overlap_is_deterministic(self):
        def result():
            game = self.game()
            units = [
                game.add_unit("swordsman", "green", 20, 20),
                game.add_unit("swordsman", "red", 20, 20),
            ]
            self.advance_units(game, units, 1 / 60, .5)
            return tuple((unit.x, unit.y) for unit in units)

        self.assertEqual(result(), result())
        self.assertTrue(all(
            math.isfinite(value) for position in result() for value in position
        ))

    def test_slight_overlap_is_allowed_and_order_keeps_progressing(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20)
        game.add_unit("shield", "red", 20, 20.99)
        mover.target_pos = (30, 20)

        game.update_unit(mover, .1)

        self.assertGreater(mover.x, 20)
        self.assertAlmostEqual(mover.y, 20)

    def test_kings_and_stationary_guards_stay_fixed(self):
        game = self.game()
        king = game.add_unit("king", "green", 20, 20)
        king.home_position = (20, 20)
        guard = game.add_unit("knight", "green", 20, 20)
        guard.home_position = (20, 20)

        self.advance_units(game, (king, guard), 1 / 60)

        self.assertEqual((king.x, king.y), king.home_position)
        self.assertEqual((guard.x, guard.y), guard.home_position)

    def test_moving_guard_respects_leash_and_returns_home(self):
        game = self.game()
        guard = game.add_unit("knight", "green", 20, 20)
        guard.home_position = (20, 20)
        target = game.add_unit("archer", "red", 24, 20)
        blocker = game.add_unit("king", "red", 22, 20)
        blocker.health = blocker.max_health

        for _ in range(240):
            game.update_unit(guard, 1 / 120)
            self.assertLessEqual(
                dist(guard.home_position, (guard.x, guard.y)),
                GUARD_LEASH_DISTANCE + 1e-9,
            )
        target.health = blocker.health = 0
        for _ in range(480):
            game.update_unit(guard, 1 / 120)
        self.assertEqual((guard.x, guard.y), guard.home_position)

    def test_archer_lock_and_no_fire_after_moving_are_preserved(self):
        game = self.game()
        archer = game.add_unit("archer", "green", 20, 20)
        target = game.add_unit("shield", "red", 25.05, 20)
        game.visible.add((25, 20))
        archer.target = target
        archer.target_pos = (target.x, target.y)
        initial_health = target.health

        game.update_unit(archer, .1)

        self.assertTrue(archer.moved_this_update)
        self.assertEqual(target.health, initial_health)
        archer.movement_lock_timer = 1
        before = (archer.x, archer.y)
        game.update_unit(archer, .1)
        self.assertEqual((archer.x, archer.y), before)

    def test_map_clamping_survives_separation(self):
        game = self.game()
        units = [
            game.add_unit("swordsman", "green", WORLD_MIN, WORLD_MIN),
            game.add_unit("swordsman", "red", WORLD_MIN, WORLD_MIN),
            game.add_unit("swordsman", "green", WORLD_MAX, WORLD_MAX),
            game.add_unit("swordsman", "red", WORLD_MAX, WORLD_MAX),
        ]
        for unit in units:
            unit.target_pos = (
                WORLD_MIN - 10 if unit.x == WORLD_MIN else WORLD_MAX + 10,
                WORLD_MIN - 10 if unit.y == WORLD_MIN else WORLD_MAX + 10,
            )

        self.advance_units(game, units, 1 / 30)

        self.assertTrue(all(
            WORLD_MIN <= coordinate <= WORLD_MAX
            for unit in units for coordinate in (unit.x, unit.y)
        ))

    def test_dense_group_is_consistent_at_30_60_and_120_fps(self):
        def simulate(dt):
            game = self.game()
            units = [
                game.add_unit(
                    "swordsman",
                    "green" if index % 2 else "red",
                    20 + (index % 3) * .35,
                    20 + (index // 3) * .35,
                )
                for index in range(9)
            ]
            starts = [(unit.x, unit.y) for unit in units]
            for unit in units:
                unit.target_pos = (30, 20)
            self.advance_units(game, units, dt, 3)
            progress = sum(
                current[0] - start[0]
                for current, start in zip(
                    ((unit.x, unit.y) for unit in units), starts
                )
            ) / len(units)
            minimum_gap = min(
                dist((first.x, first.y), (second.x, second.y))
                for index, first in enumerate(units)
                for second in units[index + 1:]
            )
            return progress, minimum_gap

        results = [simulate(dt) for dt in (1 / 30, 1 / 60, 1 / 120)]
        for progress, minimum_gap in results:
            self.assertGreater(progress, 1.0)
            self.assertGreater(minimum_gap, .75)
        self.assertLess(max(value[0] for value in results) -
                        min(value[0] for value in results), .35)
        self.assertLess(max(value[1] for value in results) -
                        min(value[1] for value in results), .2)


if __name__ == "__main__":
    unittest.main()
