import math
import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import Game, TerrainCell


class TerrainRoutingTests(unittest.TestCase):
    def game(self):
        game = Game(enemy_rng=random.Random(91))
        game.state = "playing"
        game.units.clear()
        game.terrain = {
            position: TerrainCell("plains", 0) for position in game.terrain
        }
        return game

    @staticmethod
    def fill(game, kind, cells):
        for cell in cells:
            game.terrain[cell] = TerrainCell(kind, 0)

    def test_modest_path_detour_arrives_sooner_and_is_selected(self):
        game = self.game()
        self.fill(game, "path", ((x, 19) for x in range(20, 31)))
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)

        waypoints, _ = game._astar(mover, (30.5, 20.5))

        self.assertTrue(any(y == 19.5 for _, y in waypoints))
        routed = (
            math.sqrt(2) / 2 + 8 / 2 + math.sqrt(2)
        )
        self.assertLess(routed, 10.0)

    def test_excessively_long_path_detour_is_rejected(self):
        game = self.game()
        self.fill(game, "path", ((x, 15) for x in range(20, 31)))
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)

        waypoints, _ = game._astar(mover, (30.5, 20.5))

        self.assertEqual(waypoints, [(30.5, 20.5)])

    def test_avoids_slow_band_when_detour_is_quicker(self):
        for kind in ("mountain", "forest"):
            with self.subTest(kind=kind):
                game = self.game()
                self.fill(
                    game, kind,
                    ((x, y) for x in range(23, 32) for y in range(19, 22)),
                )
                mover = game.add_unit("swordsman", "green", 20.5, 20.5)
                waypoints, _ = game._astar(mover, (34.5, 20.5))
                self.assertTrue(any(y not in (20.5,) for _, y in waypoints))

    def test_crosses_slow_terrain_when_it_is_still_quickest(self):
        game = self.game()
        self.fill(game, "mountain", ((25, y) for y in range(120)))
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)

        waypoints, _ = game._astar(mover, (30.5, 20.5))

        self.assertEqual(waypoints, [(30.5, 20.5)])

    def test_smoothing_retains_beneficial_path_lane(self):
        game = self.game()
        self.fill(game, "path", ((x, 19) for x in range(20, 31)))
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)

        waypoints, _ = game._astar(mover, (30.5, 20.5))

        self.assertGreater(len(waypoints), 1)
        self.assertIn((29.5, 19.5), waypoints)

    def test_diagonal_and_terrain_cost_compose(self):
        game = self.game()
        game.terrain[(21, 21)] = TerrainCell("path", 0)
        self.assertAlmostEqual(
            game._terrain_step_cost((20, 20), (21, 21)), math.sqrt(2) / 2
        )

    def test_identical_terrain_and_order_produce_identical_waypoints(self):
        def route():
            game = self.game()
            self.fill(game, "path", ((x, 19) for x in range(20, 31)))
            mover = game.add_unit("swordsman", "green", 20.5, 20.5)
            return game._astar(mover, (30.5, 20.5))[0]

        self.assertEqual(route(), route())

    def test_static_terrain_route_is_cached(self):
        game = self.game()
        self.fill(game, "path", ((x, 19) for x in range(20, 31)))
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)
        mover.target_pos = (30.5, 20.5)
        for _ in range(8):
            game.navigation_time += .05
            game.update_unit(mover, .05)
        self.assertEqual(game.path_calculation_count, 1)
        self.assertTrue(mover.nav_waypoints)

    def test_reset_invalidates_previous_terrain_route(self):
        game = self.game()
        self.fill(game, "path", ((x, 19) for x in range(20, 31)))
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)
        game.navigate_unit_toward(mover, (30.5, 20.5), .05)
        old_revision = mover.nav_terrain_revision
        self.assertTrue(mover.nav_waypoints)

        game.reset()
        game.units.clear()
        game.terrain = {
            position: TerrainCell("plains", 0) for position in game.terrain
        }
        game.navigate_unit_toward(mover, (30.5, 20.5), .05)

        self.assertNotEqual(mover.nav_terrain_revision, old_revision)
        self.assertEqual(mover.nav_waypoints, [])


if __name__ == "__main__":
    unittest.main()
