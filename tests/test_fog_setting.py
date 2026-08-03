import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from main import Game


class FogSettingTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=7)
        self.game.update_visibility()

    def test_setting_defaults_on_and_persists_across_level_reset(self):
        self.assertTrue(self.game.fog_of_war_enabled)

        self.game.toggle_fog_of_war()
        self.game.reset(2)

        self.assertFalse(self.game.fog_of_war_enabled)

    def test_menu_and_pause_buttons_toggle_the_setting(self):
        self.game.draw_menu()
        self.game.handle_menu_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=self.game.fog_btn.rect.center,
        ))
        self.assertFalse(self.game.fog_of_war_enabled)

        self.game.state = "paused"
        self.game.draw_pause()
        self.game.handle_pause_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=self.game.pause_fog_btn.rect.center,
        ))
        self.assertTrue(self.game.fog_of_war_enabled)

    def test_disabling_fog_reveals_hidden_units_only_for_rendering(self):
        self.game.units = []
        player = self.game.add_unit("swordsman", "green", 20, 20)
        enemy = self.game.add_unit("swordsman", "red", 23, 20)
        self.game.terrain = {
            position: type(cell)("forest", 0)
            for position, cell in self.game.terrain.items()
        }
        self.game.update_visibility()
        self.assertNotIn((23, 20), self.game.visible)

        self.game.screen.fill((1, 2, 3))
        before = pygame.image.tobytes(self.game.screen, "RGB")
        self.game.camera[:] = [enemy.x, enemy.y]
        self.game.draw_unit(enemy)
        hidden = pygame.image.tobytes(self.game.screen, "RGB")
        self.assertEqual(hidden, before)

        visible_before = self.game.visible.copy()
        explored_before = self.game.explored.copy()
        red_visible_before = self.game.red_visible.copy()
        self.game.toggle_fog_of_war()
        self.game.draw_unit(enemy)

        self.assertNotEqual(pygame.image.tobytes(self.game.screen, "RGB"), before)
        self.assertEqual(self.game.visible, visible_before)
        self.assertEqual(self.game.explored, explored_before)
        self.assertEqual(self.game.red_visible, red_visible_before)
        self.assertIsNone(self.game.find_target(player, search_radius=5))

    def test_disabling_fog_does_not_make_hidden_enemies_targetable(self):
        self.game.units = []
        player = self.game.add_unit("swordsman", "green", 20, 20)
        enemy = self.game.add_unit("swordsman", "red", 23, 20)
        self.game.terrain = {
            position: type(cell)("forest", 0)
            for position, cell in self.game.terrain.items()
        }
        self.game.update_visibility()
        self.game.toggle_fog_of_war()

        self.game.update_unit(player, 0)

        self.assertTrue(self.game.is_display_visible(enemy.x, enemy.y))
        self.assertFalse(self.game.is_visible(enemy.x, enemy.y))
        self.assertIsNone(player.target)
        self.assertEqual(enemy.health, enemy.max_health)

    def test_unexplored_fog_completely_hides_the_background(self):
        self.game.reset(3)
        self.game.visible.clear()
        self.game.explored.clear()

        samples = ((80, 80), (640, 300), (1200, 520))
        rendered_colors = []
        for background in ((255, 255, 255), (0, 0, 0)):
            self.game.screen.fill(background)
            self.game.draw_fog()
            rendered_colors.append([
                self.game.screen.get_at(point)[:3] for point in samples
            ])

        self.assertEqual(rendered_colors[0], rendered_colors[1])


if __name__ == "__main__":
    unittest.main()
