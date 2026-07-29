import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from main import Game, KING_SLASH_LIFETIME


class KingSlashEffectTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(19))
        self.game.state = "playing"
        self.game.units.clear()

    def test_successful_king_attack_emits_exactly_one_oriented_slash_only(self):
        king = self.game.add_unit("king", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 11, 10)

        self.game.attack(king, target)

        self.assertEqual(len(self.game.king_slashes), 1)
        self.assertEqual(self.game.particles, [])
        self.assertEqual(self.game.arrows, [])
        slash = self.game.king_slashes[0]
        self.assertEqual((slash.x, slash.y), (10, 10))
        self.assertEqual((slash.dx, slash.dy), (1, 0))
        self.assertEqual(slash.life, KING_SLASH_LIFETIME)
        self.assertEqual(slash.team, "green")

    def test_non_king_melee_effects_are_unchanged(self):
        for kind in ("swordsman", "shield", "knight"):
            with self.subTest(kind=kind):
                self.game.particles.clear()
                self.game.king_slashes.clear()
                attacker = self.game.add_unit(kind, "green", 10, 10)
                target = self.game.add_unit("swordsman", "red", 11, 10)
                self.game.attack(attacker, target)
                self.assertEqual(len(self.game.particles), 1)
                self.assertEqual(self.game.king_slashes, [])

    def test_slash_lifetime_updates_and_expires_deterministically(self):
        king = self.game.add_unit("king", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 11, 10)
        self.game.attack(king, target)

        self.game.update(KING_SLASH_LIFETIME / 2)
        self.assertAlmostEqual(
            self.game.king_slashes[0].life, KING_SLASH_LIFETIME / 2
        )
        self.game.update(KING_SLASH_LIFETIME / 2)
        self.assertEqual(self.game.king_slashes, [])

    def test_hidden_red_king_slash_does_not_render(self):
        king = self.game.add_unit("king", "red", 100, 60)
        target = self.game.add_unit("swordsman", "green", 99, 60)
        self.game.attack(king, target)
        self.game.visible.clear()
        self.game.screen.fill((1, 2, 3))
        before = pygame.image.tobytes(self.game.screen, "RGB")

        self.game.draw_effects()

        self.assertEqual(pygame.image.tobytes(self.game.screen, "RGB"), before)


if __name__ == "__main__":
    unittest.main()
