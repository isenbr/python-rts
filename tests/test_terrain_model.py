import os
import random
import unittest
from unittest import mock

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

    def test_exact_vision_costs(self):
        expected = {
            "mountain": 0.75,
            "forest": 5.0,
            "path": 1.0,
            "plains": 1.0,
        }
        for kind, cost in expected.items():
            self.assertEqual(TERRAIN_METADATA[kind]["vision_cost"], cost)
            self.assertEqual(main.terrain_vision_cost(kind), cost)

    def test_generation_is_deterministic_across_reset_and_instances(self):
        game = Game(terrain_seed=8128)
        first = dict(game.terrain)
        game.reset()
        self.assertEqual(game.terrain, first)
        fresh = Game(terrain_seed=8128)
        self.assertEqual(fresh.terrain, first)

    def test_start_level_chooses_fresh_seed_and_reset_preserves_it(self):
        game = Game(terrain_seed=8128)
        with mock.patch.object(
            random.SystemRandom, "getrandbits", return_value=9918273
        ):
            game.start_level(3)
        fresh_terrain = dict(game.terrain)
        self.assertEqual(game.terrain_seed, 9918273)

        game.reset()

        self.assertEqual(game.terrain_seed, 9918273)
        self.assertEqual(game.terrain, fresh_terrain)

    def test_explicit_start_level_seed_is_reproducible(self):
        first = Game(terrain_seed=1)
        second = Game(terrain_seed=2)
        first.start_level(3, terrain_seed=7755)
        second.start_level(3, terrain_seed=7755)
        self.assertEqual(first.terrain, second.terrain)
        self.assertEqual(first._terrain_road_routes, second._terrain_road_routes)

    def test_multiple_seeds_vary_regions_and_terrain(self):
        game = Game(terrain_seed=1)
        terrains = []
        region_counts = set()
        for seed in range(8):
            game.start_level(3, terrain_seed=seed)
            terrains.append(tuple(cell.kind for cell in game.terrain.values()))
            region_counts.add(game._terrain_region_count)
            self.assertIn("forest", {cell.kind for cell in game.terrain.values()})
            self.assertIn("mountain", {cell.kind for cell in game.terrain.values()})
        self.assertGreater(len(set(terrains)), 1)
        self.assertGreater(len(region_counts), 1)

    def test_average_biome_share_is_one_third_outside_excluded_areas(self):
        game = Game(terrain_seed=1)
        biome_kinds = ("plains", "forest", "mountain")
        for level_number in (2, 3):
            totals = {kind: 0 for kind in biome_kinds}
            for seed in range(24):
                game.start_level(level_number, terrain_seed=seed)
                for position, cell in game.terrain.items():
                    if (
                        position not in game._terrain_protected_cells
                        and cell.kind != "path"
                    ):
                        totals[cell.kind] += 1
            measured_cells = sum(totals.values())
            for kind in biome_kinds:
                with self.subTest(level=level_number, kind=kind):
                    self.assertAlmostEqual(
                        totals[kind] / measured_cells,
                        1 / 3,
                        delta=.025,
                    )

    def test_branching_roads_are_connected_split_and_rejoin_routes(self):
        game = Game(terrain_seed=1)
        for level_number in (2, 3):
            for seed in range(8):
                with self.subTest(level=level_number, seed=seed):
                    game.start_level(level_number, terrain_seed=seed)
                    routes = game._terrain_road_routes
                    self.assertIn(len(routes), (2, 3))
                    main_route = routes[0]
                    main_cells = set(main_route)
                    self.assertLess(main_route[0][0], main_route[-1][0])
                    for branch in routes[1:]:
                        self.assertIn(branch[0], main_cells)
                        self.assertIn(branch[-1], main_cells)
                        self.assertTrue(any(cell not in main_cells for cell in branch))
                    for route in routes:
                        for first, second in zip(route, route[1:]):
                            self.assertEqual(second[0], first[0] + 1)
                            self.assertLessEqual(abs(second[1] - first[1]), 2)

    def test_protected_unit_and_recruitment_cells_remain_plains(self):
        game = Game(terrain_seed=1)
        for level_number in (2, 3):
            for seed in range(8):
                with self.subTest(level=level_number, seed=seed):
                    game.start_level(level_number, terrain_seed=seed)
                    positions = [(unit.x, unit.y) for unit in game.units]
                    for team in ("green", "red"):
                        king = game.team_king(team)
                        direction = 1 if team == "green" else -1
                        positions.append((
                            king.x + direction * main.RECRUIT_FORWARD_OFFSET,
                            king.y + main.RECRUIT_FIRST_LATERAL_OFFSET,
                        ))
                    self.assertTrue(all(
                        game.terrain[(int(x), int(y))].kind == "plains"
                        for x, y in positions
                    ))

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
