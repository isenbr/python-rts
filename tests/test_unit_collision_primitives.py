import math
import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    Game,
    UNIT_SEPARATION_RADIUS,
    UNIT_SOFT_OVERLAP,
    UnitSpatialHash,
)


class UnitCollisionPrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(7))
        self.game.units.clear()

    def add(self, kind, team, x, y):
        return self.game.add_unit(kind, team, x, y)

    def rebuild(self):
        self.game.rebuild_unit_spatial_hash()

    def test_query_checks_all_intersecting_cells(self):
        center = self.add("swordsman", "green", 2.25, 2.25)
        across_x = self.add("archer", "green", 2.35, 2.25)
        across_y = self.add("shield", "red", 2.25, 2.35)
        self.rebuild()

        self.assertEqual(
            self.game.nearby_units(center, .2),
            sorted((across_x, across_y), key=lambda unit: unit.uid),
        )

    def test_units_outside_query_radius_are_ignored(self):
        center = self.add("swordsman", "green", 10, 10)
        inside = self.add("archer", "green", 11, 10)
        self.add("shield", "green", 12.01, 10)
        self.rebuild()

        self.assertEqual(self.game.nearby_units(center, 2), [inside])

    def test_exact_overlap_vector_is_finite_and_deterministic(self):
        first = self.add("swordsman", "green", 10, 10)
        second = self.add("swordsman", "red", 10, 10)
        self.rebuild()

        first_vector = self.game.unit_separation_vector(first)
        second_vector = self.game.unit_separation_vector(second)
        self.assertTrue(all(math.isfinite(value) for value in first_vector))
        self.assertEqual(
            first_vector,
            self.game.unit_separation_vector(first),
        )
        self.assertAlmostEqual(first_vector[0], -second_vector[0])
        self.assertAlmostEqual(first_vector[1], -second_vector[1])
        self.assertAlmostEqual(
            math.hypot(*first_vector),
            UNIT_SEPARATION_RADIUS - UNIT_SOFT_OVERLAP,
        )

    def test_dead_units_are_excluded(self):
        center = self.add("swordsman", "green", 10, 10)
        dead = self.add("archer", "red", 10.5, 10)
        dead.health = 0
        self.rebuild()

        self.assertEqual(self.game.nearby_units(center), [])

    def test_map_edge_query_does_not_wrap_or_fail(self):
        corner = self.add("king", "green", .5, .5)
        neighbor = self.add("knight", "green", .6, .6)
        far = self.add("swordsman", "red", 119.5, 119.5)
        self.rebuild()

        self.assertEqual(self.game.nearby_units(corner, .2), [neighbor])
        self.assertNotIn(far, self.game.nearby_units(corner, 1))

    def test_friendly_enemy_kings_and_guards_are_detected(self):
        center = self.add("swordsman", "green", 20, 20)
        friendly_guard = self.add("knight", "green", 20.5, 20)
        enemy_king = self.add("king", "red", 21, 20)
        self.rebuild()

        self.assertEqual(
            self.game.nearby_units(center, 1.1),
            [friendly_guard, enemy_king],
        )

    def test_moderate_group_queries_remain_local(self):
        grid = UnitSpatialHash()
        units = [
            self.add("swordsman", "green" if index % 2 else "red", x * 5, y * 5)
            for index, (x, y) in enumerate(
                (divmod(value, 20) for value in range(400))
            )
        ]
        grid.rebuild(units)
        for unit in units:
            grid.neighbors((unit.x, unit.y), 1.2, exclude=unit)

        self.assertLess(grid.candidate_checks, len(units) ** 2 // 10)

    def test_calculation_does_not_mutate_strategic_target(self):
        mover = self.add("swordsman", "green", 10, 10)
        self.add("shield", "red", 10.2, 10)
        mover.target_pos = (50, 60)
        self.rebuild()

        self.game.unit_separation_vector(mover)

        self.assertEqual(mover.target_pos, (50, 60))


if __name__ == "__main__":
    unittest.main()
