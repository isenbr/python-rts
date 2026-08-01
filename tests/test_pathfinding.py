import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import Game, TerrainCell, WORLD_MAX, WORLD_MIN, dist


class PathfindingTests(unittest.TestCase):
    def game(self):
        game = Game(enemy_rng=random.Random(41))
        game.state = "playing"
        game.enemy_ai.recruitment_timer = 999
        game.units.clear()
        game.terrain = {
            position: TerrainCell("plains", 0)
            for position in game.terrain
        }
        return game

    @staticmethod
    def step(game, mover, seconds, dt=.1):
        for _ in range(round(seconds / dt)):
            game.navigation_time += dt
            game.rebuild_unit_spatial_hash()
            game._movement_snapshot_active = True
            try:
                game.update_unit(mover, dt)
            finally:
                game._movement_snapshot_active = False

    def test_walks_around_stationary_wall(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20)
        for y in range(17, 24):
            game.add_unit("shield", "green", 25, y)
        mover.target_pos = (31, 20)
        self.step(game, mover, 15)
        self.assertGreater(mover.x, 29)
        self.assertGreater(max(game.path_calculation_lengths), 1)

    def test_navigates_narrow_valid_gap(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20.5)
        for y in (17.5, 18.5, 22.5, 23.5):
            game.add_unit("shield", "green", 25.5, y)
        mover.target_pos = (31, 20.5)
        self.step(game, mover, 14)
        self.assertGreater(mover.x, 29)

    def test_diagonal_does_not_cut_blocked_corner(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20.5, 20.5)
        game.add_unit("king", "green", 21.5, 20.5)
        game.add_unit("king", "red", 20.5, 21.5)
        waypoints, _ = game._astar(mover, (23.5, 23.5))
        self.assertIsNotNone(waypoints)
        self.assertFalse(waypoints and waypoints[0] == (21.5, 21.5))

    def test_combat_target_stops_at_attack_range(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20)
        enemy = game.add_unit("shield", "red", 28, 20)
        mover.target = enemy
        mover.target_pos = (enemy.x, enemy.y)
        self.step(game, mover, 10)
        self.assertLessEqual(dist((mover.x, mover.y), (enemy.x, enemy.y)),
                             mover.attack_range + .08)
        self.assertGreater(dist((mover.x, mover.y), (enemy.x, enemy.y)), .5)

    def test_replans_when_blocker_enters_path(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20)
        blocker = game.add_unit("shield", "green", 25, 24)
        mover.target_pos = (32, 20)
        self.step(game, mover, 1)
        before = game.path_calculation_count
        blocker.x, blocker.y = 25, 20
        self.step(game, mover, 1)
        self.assertGreater(game.path_calculation_count, before)
        self.assertTrue(mover.nav_waypoints)

    def test_cached_path_is_reused(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20)
        for y in range(18, 23):
            game.add_unit("shield", "green", 25, y)
        mover.target_pos = (31, 20)
        self.step(game, mover, .4, .05)
        self.assertEqual(game.path_calculation_count, 1)

    def test_failed_path_waits_for_recalculation_interval(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", WORLD_MIN, 60.5)
        for y in range(120):
            game.add_unit("king", "green", 1.5, y + .5)
        mover.target_pos = (5.5, 60.5)

        self.step(game, mover, .4, .05)

        self.assertEqual(game.path_calculation_count, 1)
        self.assertEqual(mover.nav_waypoints, [])

    def test_recovers_after_route_temporarily_unavailable(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", WORLD_MIN, 60.5)
        blockers = [
            game.add_unit("king", "green", 1.5, y + .5)
            for y in range(120)
        ]
        mover.target_pos = (5.5, 60.5)
        self.step(game, mover, 1)
        self.assertEqual(mover.target_pos, (5.5, 60.5))
        for blocker in blockers:
            blocker.health = 0
        self.step(game, mover, 6)
        self.assertGreater(mover.x, 4)

    def test_new_order_replaces_cached_path(self):
        game = self.game()
        mover = game.add_unit("swordsman", "green", 20, 20)
        game.add_unit("shield", "green", 25, 20)
        mover.target_pos = (31, 20)
        self.step(game, mover, .1)
        old_destination = mover.nav_destination
        mover.selected = True
        game.issue_order((20, 30))
        self.assertIsNone(mover.nav_destination)
        self.step(game, mover, .1)
        self.assertNotEqual(mover.nav_destination, old_destination)

    def test_paths_are_deterministic(self):
        def path():
            game = self.game()
            mover = game.add_unit("swordsman", "green", 20, 20)
            for y in range(18, 23):
                game.add_unit("shield", "red", 25, y)
            return game._astar(mover, (31, 20))[0]
        self.assertEqual(path(), path())

    def test_destinations_near_all_edges_are_clamped(self):
        for destination in (
            (WORLD_MIN, WORLD_MIN), (WORLD_MIN, WORLD_MAX),
            (WORLD_MAX, WORLD_MIN), (WORLD_MAX, WORLD_MAX),
        ):
            with self.subTest(destination=destination):
                game = self.game()
                mover = game.add_unit("swordsman", "green", 60, 60)
                mover.target_pos = destination
                self.step(game, mover, .1)
                points = mover.nav_waypoints + ([mover.nav_destination]
                                                 if mover.nav_destination else [])
                self.assertTrue(all(
                    WORLD_MIN <= coordinate <= WORLD_MAX
                    for point in points for coordinate in point
                ))


if __name__ == "__main__":
    unittest.main()
