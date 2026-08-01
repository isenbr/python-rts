import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main
from main import Game, TerrainCell


class TerrainCombatTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=17)
        self.game.state = "playing"
        self.game.units.clear()
        self.game.terrain = {
            cell: TerrainCell("plains", 0) for cell in self.game.terrain
        }

    def place(self, unit, terrain):
        self.game.terrain[(int(unit.x), int(unit.y))] = TerrainCell(terrain, 0)

    def damage(self, attacker_kind, attacker_terrain, target_terrain):
        attacker = self.game.add_unit(attacker_kind, "green", 20.5, 20.5)
        target = self.game.add_unit("swordsman", "red", 21.5, 20.5)
        self.place(attacker, attacker_terrain)
        self.place(target, target_terrain)
        before = target.health
        self.game.attack(attacker, target)
        self.game.units.clear()
        return before - target.health

    def test_mountain_archer_range_bonus_is_automatic(self):
        archer = self.game.add_unit("archer", "green", 20.5, 20.5)
        target = self.game.add_unit("swordsman", "red", 26.25, 20.5)
        self.place(archer, "mountain")
        self.place(target, "mountain")
        self.game.visible.add((int(target.x), int(target.y)))

        self.assertEqual(self.game.effective_attack_range(archer), 6.0)
        self.assertIs(self.game.find_target(archer), target)

        self.place(archer, "plains")
        self.assertEqual(self.game.effective_attack_range(archer), 5.0)
        self.assertIsNone(self.game.find_target(archer))
        self.assertEqual(archer.attack_range, 5.0)

    def test_only_archers_gain_mountain_range(self):
        swordsman = self.game.add_unit("swordsman", "green", 20.5, 20.5)
        self.place(swordsman, "mountain")
        self.assertEqual(
            self.game.effective_attack_range(swordsman), swordsman.attack_range
        )

    def test_mountain_archer_damage_bonus_requires_lower_target(self):
        self.assertEqual(self.damage("archer", "mountain", "plains"), 60.0)
        self.assertEqual(self.damage("archer", "mountain", "mountain"), 50.0)

    def test_forest_reduces_only_ranged_damage(self):
        self.assertEqual(self.damage("archer", "plains", "forest"), 35.0)
        self.assertEqual(self.damage("swordsman", "plains", "forest"), 5.0)

    def test_path_increases_all_incoming_damage(self):
        self.assertEqual(self.damage("archer", "plains", "path"), 60.0)
        self.assertEqual(self.damage("swordsman", "plains", "path"), 6.0)

    def test_mountain_and_forest_ranged_modifiers_stack(self):
        self.assertAlmostEqual(
            self.damage("archer", "mountain", "forest"), 42.0
        )

    def test_visual_variation_does_not_change_combat_metadata(self):
        for kind in main.TERRAIN_KINDS:
            expected = main.TERRAIN_METADATA[kind]
            for variation in range(4):
                cell = TerrainCell(kind, variation)
                self.assertEqual(main.TERRAIN_METADATA[cell.kind], expected)


if __name__ == "__main__":
    unittest.main()
