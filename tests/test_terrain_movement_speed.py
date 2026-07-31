import math
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main
from main import (
    GUARD_LEASH_DISTANCE,
    WORLD_MAX,
    Game,
    TerrainCell,
    dist,
)


class TerrainMovementSpeedTests(unittest.TestCase):
    def game(self, kind="plains", variation=0):
        game = Game(terrain_seed=3)
        game.state = "playing"
        game.units.clear()
        game.terrain = {
            cell: TerrainCell(kind, variation) for cell in game.terrain
        }
        return game

    def travel(self, kind, dt=1 / 60, seconds=1, unit_kind="swordsman",
               variation=0, diagonal=False):
        game = self.game(kind, variation)
        unit = game.add_unit(unit_kind, "green", 20.5, 20.5)
        if unit.is_king_objective or unit.is_autonomous_guard:
            unit.home_position = (20.5, 20.5)
        target = (40.5, 40.5) if diagonal else (40.5, 20.5)
        start = (unit.x, unit.y)
        for _ in range(round(seconds / dt)):
            game.move_unit_toward(unit, target, dt)
        return dist(start, (unit.x, unit.y)), unit

    def test_exact_terrain_ratios_and_plains_baseline(self):
        distances = {
            kind: self.travel(kind)[0]
            for kind in ("mountain", "forest", "path", "plains")
        }
        self.assertAlmostEqual(distances["plains"], 1.0)
        self.assertAlmostEqual(distances["mountain"], distances["plains"] * .5)
        self.assertAlmostEqual(distances["forest"], distances["plains"] * .75)
        self.assertAlmostEqual(distances["path"], distances["plains"] * 2)

    def test_uniform_terrain_is_frame_rate_independent(self):
        for kind in ("mountain", "forest", "path", "plains"):
            results = [self.travel(kind, dt)[0] for dt in (1 / 30, 1 / 60, 1 / 120)]
            with self.subTest(kind=kind):
                self.assertLess(max(results) - min(results), 1e-9)

    def test_large_update_splits_at_tile_boundary(self):
        game = self.game("plains")
        game.terrain[(21, 20)] = TerrainCell("path", 0)
        unit = game.add_unit("swordsman", "green", 20.5, 20.5)

        game.move_unit_toward(unit, (30.5, 20.5), 1)

        self.assertAlmostEqual(unit.x, 22.0)
        self.assertAlmostEqual(unit.y, 20.5)

    def test_diagonal_uses_scalar_without_extra_speed(self):
        for kind in ("mountain", "forest", "path", "plains"):
            cardinal = self.travel(kind)[0]
            diagonal = self.travel(kind, diagonal=True)[0]
            with self.subTest(kind=kind):
                self.assertAlmostEqual(diagonal, cardinal, places=9)

    def test_every_unit_kind_receives_multiplier_without_changing_base_speed(self):
        for kind in (*main.ALL_UNIT_KINDS,):
            plains_distance, plains = self.travel("plains", unit_kind=kind)
            mountain_distance, mountain = self.travel("mountain", unit_kind=kind)
            with self.subTest(kind=kind):
                self.assertEqual(plains.speed, mountain.speed)
                self.assertAlmostEqual(mountain_distance, plains_distance * .5)

    def test_visual_variations_do_not_change_speed(self):
        for kind in ("mountain", "forest", "path", "plains"):
            results = [self.travel(kind, variation=value)[0] for value in range(4)]
            with self.subTest(kind=kind):
                self.assertTrue(all(math.isclose(results[0], value) for value in results))

    def test_stationary_units_remain_stationary_on_every_terrain(self):
        for kind in ("mountain", "forest", "path", "plains"):
            game = self.game(kind)
            unit = game.add_unit("swordsman", "green", 20.5, 20.5)
            game.move_unit_toward(unit, (unit.x, unit.y), 10)
            self.assertEqual((unit.x, unit.y), (20.5, 20.5))

    def test_map_edge_and_guard_leash_still_clamp(self):
        game = self.game("path")
        edge = game.add_unit("swordsman", "green", WORLD_MAX - .1, 20.5)
        game.move_unit_toward(edge, (WORLD_MAX + 20, 20.5), 10)
        self.assertEqual(edge.x, WORLD_MAX)
        guard = game.add_unit("knight", "green", 20.5, 20.5)
        guard.home_position = (20.5, 20.5)
        game.move_unit_toward(guard, (100, 20.5), 100)
        self.assertLessEqual(
            dist(guard.home_position, (guard.x, guard.y)),
            GUARD_LEASH_DISTANCE + 1e-9,
        )

    def test_new_order_and_cached_waypoint_both_use_terrain(self):
        game = self.game("mountain")
        direct = game.add_unit("swordsman", "green", 20.5, 20.5)
        direct.target_pos = (30.5, 20.5)
        game.update_unit(direct, 1)
        self.assertAlmostEqual(direct.x, 21.0)

        cached = game.add_unit("swordsman", "green", 30.5, 30.5)
        cached.nav_destination = (40.5, 30.5)
        cached.nav_destination_key = (None, False)
        cached.nav_waypoints = [(35.5, 30.5)]
        cached.nav_last_progress_position = (30.5, 30.5)
        game._direct_unit_corridor_clear = lambda *args: False
        game.navigate_unit_toward(cached, (40.5, 30.5), 1)
        self.assertAlmostEqual(cached.x, 31.0)


if __name__ == "__main__":
    unittest.main()
