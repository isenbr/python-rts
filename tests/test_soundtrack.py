import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import Game


class FakeSoundtrack:
    def __init__(self):
        self.mode = None
        self.history = []

    def set_mode(self, mode):
        self.mode = mode
        self.history.append(mode)

    def shutdown(self):
        self.mode = None


class SoundtrackStateTests(unittest.TestCase):
    def setUp(self):
        self.soundtrack = FakeSoundtrack()
        self.game = Game(soundtrack=self.soundtrack)
        self.game.state = "playing"
        self.game.visible.clear()

    def test_peaceful_music_plays_when_no_enemy_is_visible(self):
        self.game.update_soundtrack()

        self.assertEqual(self.soundtrack.mode, "peaceful")

    def test_fighting_music_plays_while_enemy_is_visible(self):
        enemy = next(unit for unit in self.game.units if unit.team == "red")
        self.game.visible.add((int(enemy.x), int(enemy.y)))

        self.game.update_soundtrack()

        self.assertEqual(self.soundtrack.mode, "fighting")

        self.game.visible.clear()
        self.game.update_soundtrack()
        self.assertEqual(self.soundtrack.mode, "peaceful")

    def test_fog_display_setting_does_not_reveal_enemies_to_music(self):
        self.game.fog_of_war_enabled = False

        self.game.update_soundtrack()

        self.assertEqual(self.soundtrack.mode, "peaceful")

    def test_music_stops_outside_active_gameplay(self):
        self.game.update_soundtrack()
        self.game.state = "paused"

        self.game.update_soundtrack()

        self.assertIsNone(self.soundtrack.mode)

    def test_dead_visible_enemy_does_not_trigger_fighting_music(self):
        enemy = next(unit for unit in self.game.units if unit.team == "red")
        enemy.health = 0
        self.game.visible.add((int(enemy.x), int(enemy.y)))

        self.game.update_soundtrack()

        self.assertEqual(self.soundtrack.mode, "peaceful")


if __name__ == "__main__":
    unittest.main()
