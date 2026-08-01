import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main
from main import Game, TerrainCell


class TerrainVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=41)
        self.game.terrain = {
            position: TerrainCell("plains", 0)
            for position in self.game.terrain
        }

    def paint_ray(self, start_x, end_x, kind, y=20):
        for x in range(start_x, end_x + 1):
            self.game.terrain[(x, y)] = TerrainCell(kind, 0)

    def test_exact_terrain_vision_costs(self):
        self.assertEqual(main.terrain_vision_cost("mountain"), 0.75)
        self.assertEqual(main.terrain_vision_cost("forest"), 5.0)
        self.assertEqual(main.terrain_vision_cost("path"), 1.0)
        self.assertEqual(main.terrain_vision_cost("plains"), 1.0)

    def test_plains_and_path_use_normal_cost(self):
        self.assertEqual(self.game.terrain_sight_cost((20, 20), (28, 20)), 8.0)
        self.paint_ray(21, 28, "path")
        self.assertEqual(self.game.terrain_sight_cost((20, 20), (28, 20)), 8.0)

    def test_mountains_extend_line_of_sight(self):
        self.paint_ray(21, 30, "mountain")
        self.assertEqual(self.game.terrain_sight_cost((20, 20), (30, 20)), 7.5)
        self.assertTrue(
            self.game.has_terrain_line_of_sight((20, 20), (30, 20), 8.0)
        )

    def test_forests_consume_five_times_the_sight_budget(self):
        self.paint_ray(21, 22, "forest")
        self.assertEqual(self.game.terrain_sight_cost((20, 20), (22, 20)), 10.0)
        self.assertFalse(
            self.game.has_terrain_line_of_sight((20, 20), (22, 20), 8.0)
        )

    def test_diagonal_crossings_scale_terrain_cost_by_distance(self):
        self.game.terrain[(21, 21)] = TerrainCell("forest", 0)
        self.assertAlmostEqual(
            self.game.terrain_sight_cost((20, 20), (21, 21)),
            5 * 2 ** 0.5,
        )

    def test_visibility_update_uses_weighted_rays(self):
        self.game.units = []
        scout = self.game.add_unit("swordsman", "green", 20, 20)
        self.paint_ray(21, 30, "mountain")
        self.game.update_visibility()
        self.assertIn((30, 20), self.game.visible)

        self.game.terrain[(21, 20)] = TerrainCell("forest", 0)
        self.game.terrain[(22, 20)] = TerrainCell("forest", 0)
        self.game.update_visibility()
        self.assertNotIn((22, 20), self.game.visible)
        self.assertEqual((scout.x, scout.y), (20, 20))

    def test_enemy_observation_uses_the_same_weighted_rays(self):
        self.game.units = []
        observer = self.game.add_unit("swordsman", "red", 20, 20)
        player = self.game.add_unit("swordsman", "green", 23, 20)
        self.paint_ray(21, 23, "forest")
        self.assertFalse(
            self.game.enemy_ai._player_unit_is_visible(player, [observer])
        )

    def test_enemy_cannot_target_or_damage_player_hidden_by_forest(self):
        self.game.units = []
        archer = self.game.add_unit("archer", "red", 20, 20)
        player = self.game.add_unit("swordsman", "green", 23, 20)
        self.paint_ray(21, 23, "forest")
        self.game.update_team_visibility("red")

        self.game.update_unit(archer, 0)

        self.assertIsNone(archer.target)
        self.assertEqual(player.health, player.max_health)
        self.assertEqual(self.game.arrows, [])

    def test_enemy_units_share_legitimate_team_vision(self):
        self.game.units = []
        archer = self.game.add_unit("archer", "red", 20, 20)
        self.game.add_unit("swordsman", "red", 23, 21)
        player = self.game.add_unit("swordsman", "green", 23, 20)
        self.paint_ray(21, 23, "forest")
        self.game.update_team_visibility("red")

        self.game.update_unit(archer, 0)

        self.assertIs(archer.target, player)
        self.assertLess(player.health, player.max_health)

    def test_enemy_lost_target_keeps_only_last_visible_position(self):
        self.game.units = []
        archer = self.game.add_unit("archer", "red", 20, 20)
        player = self.game.add_unit("swordsman", "green", 23, 20)
        self.game.update_team_visibility("red")
        self.game.update_unit(archer, 0)
        last_seen = (player.x, player.y)

        self.paint_ray(21, 23, "forest")
        self.game.update_team_visibility("red")
        self.game.update_unit(archer, 0)

        self.assertIsNone(archer.target)
        self.assertEqual(archer.target_pos, last_seen)


if __name__ == "__main__":
    unittest.main()
