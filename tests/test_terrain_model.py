import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main
from main import Game, LEVELS, TERRAIN_KINDS, TERRAIN_METADATA


class TerrainModelTests(unittest.TestCase):
    def test_every_level_has_complete_valid_in_bounds_terrain(self):
        game = Game()
        for level_number, level in LEVELS.items():
            with self.subTest(level=level_number):
                game.reset(level_number)
                expected = {
                    (x, y)
                    for x in range(level.map_size)
                    for y in range(level.map_size)
                }
                self.assertEqual(set(game.terrain), expected)
                self.assertEqual(len(game.terrain), level.map_size ** 2)
                self.assertTrue(all(
                    cell.kind in TERRAIN_KINDS
                    for cell in game.terrain.values()
                ))
                self.assertTrue(all(
                    type(cell.variation) is int and 0 <= cell.variation <= 3
                    for cell in game.terrain.values()
                ))

    def test_exact_multipliers_and_variation_independence(self):
        expected = {
            "mountain": 0.5,
            "forest": 0.75,
            "path": 2.0,
            "plains": 1.0,
        }
        self.assertEqual(set(TERRAIN_METADATA), set(expected))
        for kind, multiplier in expected.items():
            self.assertEqual(
                TERRAIN_METADATA[kind]["movement_multiplier"], multiplier
            )
            for variation in range(4):
                cell = main.TerrainCell(kind, variation)
                self.assertEqual(
                    main.terrain_movement_multiplier(cell.kind), multiplier
                )

    def test_generation_is_deterministic_across_reset_and_instances(self):
        game = Game(terrain_seed=8128)
        first = dict(game.terrain)
        game.reset()
        self.assertEqual(game.terrain, first)
        fresh = Game(terrain_seed=8128)
        self.assertEqual(fresh.terrain, first)

    def test_required_spawn_recruitment_and_objective_areas_are_valid(self):
        game = Game()
        for level_number in LEVELS:
            game.reset(level_number)
            positions = [(unit.x, unit.y) for unit in game.units]
            for team in ("green", "red"):
                king = game.team_king(team)
                if king is not None:
                    direction = 1 if team == "green" else -1
                    positions.append((
                        king.x + direction * main.RECRUIT_FORWARD_OFFSET,
                        king.y + main.RECRUIT_FIRST_LATERAL_OFFSET,
                    ))
            for x, y in positions:
                cell_position = (int(x), int(y))
                self.assertIn(cell_position, game.terrain)
                self.assertIn(game.terrain[cell_position].kind, TERRAIN_KINDS)

    def test_generation_does_not_mutate_module_random_state(self):
        random.seed(9341)
        before = random.getstate()
        game = Game(terrain_seed=55)
        game.reset(1)
        game.reset(2)
        game.reset(3)
        self.assertEqual(random.getstate(), before)


if __name__ == "__main__":
    unittest.main()
