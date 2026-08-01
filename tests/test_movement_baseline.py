import math
import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import Game, TerrainCell, UNIT_SEPARATION_RADIUS, UNIT_SOFT_OVERLAP
from tests.movement_helpers import (
    made_progress_toward_destination,
    pairwise_unit_separation,
    penetration_beyond_soft_overlap,
)


class MovementBaselineTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(7))
        self.game.state = "playing"
        self.game.enemy_ai.recruitment_timer = 999
        self.game.units.clear()
        self.game.terrain = {
            position: TerrainCell("plains", 0)
            for position in self.game.terrain
        }

    def test_green_units_converging_through_one_point_avoid_excess_penetration(self):
        destination = (30.0, 30.0)
        units = [
            self.game.add_unit("swordsman", "green", x, y)
            for x, y in ((28, 30), (32, 30), (30, 28), (30, 32))
        ]
        for unit in units:
            unit.target_pos = destination

        for _ in range(40):
            for unit in units:
                self.game.update_unit(unit, .1)

        penetrations = [
            penetration_beyond_soft_overlap(first, second)
            for first, second, _ in pairwise_unit_separation(units)
        ]
        self.assertLessEqual(max(penetrations), 1e-9)

    def test_green_and_red_units_do_not_stack_at_a_shared_destination(self):
        green = self.game.add_unit("swordsman", "green", 20, 20)
        red = self.game.add_unit("swordsman", "red", 22, 20)
        destination = (21, 20)

        self.game.move_unit_toward(green, destination, 1)
        self.game.move_unit_toward(red, destination, 1)

        self.assertLessEqual(
            penetration_beyond_soft_overlap(green, red),
            1e-9,
        )

    def test_direct_movement_stops_exactly_at_a_nearby_destination(self):
        mover = self.game.add_unit("swordsman", "green", 20, 20)

        moved = self.game.move_unit_toward(mover, (20.25, 20), 1)

        self.assertTrue(moved)
        self.assertEqual((mover.x, mover.y), (20.25, 20))

    def test_non_positive_dt_does_not_move_or_change_an_order(self):
        mover = self.game.add_unit("swordsman", "green", 20, 20)
        mover.target_pos = (30, 20)

        for dt in (0, -1):
            with self.subTest(dt=dt):
                moved = self.game.move_unit_toward(
                    mover, mover.target_pos, dt
                )
                self.assertFalse(moved)
                self.assertEqual((mover.x, mover.y), (20, 20))
                self.assertEqual(mover.target_pos, (30, 20))

    def test_stationary_unit_line_causes_a_detour_with_forward_progress(self):
        # Local separation has no deterministic left/right signal at a
        # perfectly symmetric wall. The pathfinding stage owns this detour.
        mover = self.game.add_unit("swordsman", "green", 20, 20)
        blockers = [
            self.game.add_unit("shield", "green", 25, y)
            for y in (18, 19, 20, 21, 22)
        ]
        destination = (30, 20)
        start = (mover.x, mover.y)
        max_lateral_offset = 0.0

        for _ in range(120):
            mover.target_pos = destination
            self.game.update_unit(mover, .1)
            max_lateral_offset = max(max_lateral_offset, abs(mover.y - start[1]))

        self.assertTrue(
            made_progress_toward_destination(
                start, (mover.x, mover.y), destination
            )
        )
        self.assertGreaterEqual(
            max_lateral_offset,
            UNIT_SEPARATION_RADIUS - UNIT_SOFT_OVERLAP,
        )
        self.assertTrue(all((unit.x, unit.y) == (25, y) for unit, y in zip(
            blockers, (18, 19, 20, 21, 22)
        )))

    def test_exact_coordinate_overlap_is_finite_and_deterministic(self):
        def separated_positions():
            game = Game(enemy_rng=random.Random(7))
            game.state = "playing"
            game.units.clear()
            first = game.add_unit("swordsman", "red", 20, 20)
            second = game.add_unit("swordsman", "red", 20, 20)
            game.update_unit(first, .25)
            game.update_unit(second, .25)
            return (first.x, first.y), (second.x, second.y)

        first_run = separated_positions()
        second_run = separated_positions()
        self.assertEqual(first_run, second_run)
        self.assertTrue(all(
            math.isfinite(coordinate)
            for position in first_run
            for coordinate in position
        ))


if __name__ == "__main__":
    unittest.main()
