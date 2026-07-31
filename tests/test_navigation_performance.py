import math
import os
import random
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    AIState,
    UNIT_ASTAR_MAX_EXPANSIONS,
    UNIT_SEPARATION_RADIUS,
    UNIT_SOFT_OVERLAP,
    WORLD_MAX,
    WORLD_MIN,
    Game,
    dist,
)
from simulate_performance import ARMY_SIZES, simulate_scaling


class NavigationPerformanceTests(unittest.TestCase):
    def test_progressively_larger_unobstructed_armies_stay_local(self):
        first = simulate_scaling(seconds=1.0)
        second = simulate_scaling(seconds=1.0)
        structural_keys = (
            "units",
            "average_nearby_candidates",
            "maximum_nearby_candidates",
            "paths_per_simulated_second",
            "expanded_astar_nodes",
            "minimum_progress",
            "all_coordinates_finite",
            "all_units_in_bounds",
        )
        self.assertEqual(
            [{key: row[key] for key in structural_keys} for row in first],
            [{key: row[key] for key in structural_keys} for row in second],
        )
        self.assertEqual([row["units"] for row in first], list(ARMY_SIZES))
        for row in first:
            # Candidate growth is governed by local density, not army size.
            self.assertLess(row["average_nearby_candidates"], 8)
            self.assertLess(row["maximum_nearby_candidates"], 12)
            self.assertEqual(row["paths_per_simulated_second"], 0)
            self.assertEqual(row["expanded_astar_nodes"], 0)
            self.assertGreater(row["minimum_progress"], .8)
            self.assertTrue(row["all_coordinates_finite"])
            self.assertTrue(row["all_units_in_bounds"])

    def test_cached_detour_is_reused(self):
        game = Game(enemy_rng=random.Random(73))
        game.state = "playing"
        game.units.clear()
        mover = game.add_unit("swordsman", "green", 20, 20)
        for y in range(18, 23):
            game.add_unit("king", "red", 25, y)
        mover.target_pos = (32, 20)
        for _ in range(8):
            game.navigation_time += .05
            game.update_unit(mover, .05)
        self.assertTrue(mover.nav_waypoints)
        self.assertEqual(game.path_calculation_count, 1)
        self.assertGreater(game.path_expanded_nodes, 0)

    def test_astar_expansion_limit_fails_safely(self):
        game = Game(enemy_rng=random.Random(73))
        game.state = "playing"
        game.units.clear()
        mover = game.add_unit("swordsman", "green", 20, 20)
        for y in range(10, 31):
            game.add_unit("king", "red", 25, y)
        with mock.patch("main.UNIT_ASTAR_MAX_EXPANSIONS", 3):
            waypoints, _ = game._astar(mover, (40, 20))
        self.assertIsNone(waypoints)
        self.assertEqual(game.path_limit_failures, 1)
        self.assertEqual(game.path_max_expanded_nodes, 3)
        self.assertLessEqual(game.path_max_expanded_nodes,
                             UNIT_ASTAR_MAX_EXPANSIONS)


class LongMatchCorrectnessTests(unittest.TestCase):
    def test_long_match_navigation_and_lifecycle_invariants(self):
        game = Game(enemy_rng=random.Random(7))
        game.state = "playing"
        game.update_visibility()
        movers = [unit for unit in game.units if unit.is_player_commandable]
        for unit in movers:
            unit.target_pos = (game.team_king("red").x,
                               game.team_king("red").y)
        starts = {unit.uid: (unit.x, unit.y) for unit in movers}
        removed_uid = movers[0].uid
        maximum_penetration = 0.0
        for step in range(1200):
            if step == 100:
                movers[0].health = 0
            game.update(.05)
            self.assertTrue(all(
                math.isfinite(value)
                for unit in game.units for value in (unit.x, unit.y)
            ))
            self.assertTrue(all(
                WORLD_MIN <= value <= WORLD_MAX
                for unit in game.units for value in (unit.x, unit.y)
            ))
            if step >= 100:
                self.assertNotIn(
                    removed_uid, game.unit_spatial_hash.positions
                )
            living = [unit for unit in game.units if unit.health > 0]
            for unit in living:
                for other in game.nearby_units(
                    unit, UNIT_SEPARATION_RADIUS
                ):
                    if other.uid <= unit.uid:
                        continue
                    maximum_penetration = max(
                        maximum_penetration,
                        UNIT_SEPARATION_RADIUS - UNIT_SOFT_OVERLAP
                        - dist((unit.x, unit.y), (other.x, other.y)),
                    )
            if game.winner:
                break
        progressed = [
            dist(starts[unit.uid], (unit.x, unit.y))
            # Terrain-aware routes can legitimately change the deterministic
            # battle winner. Removed unit objects retain their final position,
            # which is sufficient for this movement-progress invariant.
            for unit in movers[1:]
        ]
        self.assertTrue(progressed)
        self.assertGreater(max(progressed), 10)
        self.assertLess(maximum_penetration, 1.0)
        self.assertGreater(len(game.enemy_ai.state_history), 1)
        self.assertTrue(any(
            state in (AIState.RALLYING, AIState.ATTACKING, AIState.DEFENDING)
            for _, state in game.enemy_ai.state_history
        ))
        if not game.winner:
            red_king = game.team_king("red")
            red_king.health = 0
            game.update(.05)
            self.assertEqual(game.winner, "VICTORY")
        else:
            self.assertIn(game.winner, ("VICTORY", "DEFEAT"))


if __name__ == "__main__":
    unittest.main()
