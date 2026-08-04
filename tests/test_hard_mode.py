import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main


class HardModeTests(unittest.TestCase):
    def setUp(self):
        self.game = main.Game(terrain_seed=41)

    def test_campaign_hard_mode_is_available_only_for_levels_three_to_five(self):
        self.game.selected_level_page = 3
        self.game.handle_level_select_event(pygame.event.Event(
            pygame.KEYDOWN, {"key": pygame.K_h}
        ))
        self.assertTrue(self.game.campaign_hard_mode)

        self.game.start_level(3, terrain_seed=77)
        self.assertTrue(self.game.hard_mode)
        self.assertIsInstance(self.game.enemy_ai, main.HardModeAI)

        self.game.start_level(2, terrain_seed=77)
        self.assertFalse(self.game.hard_mode)
        self.assertIs(type(self.game.enemy_ai), main.EnemyAI)

    def test_standard_mode_keeps_the_existing_enemy_ai(self):
        self.game.campaign_hard_mode = False
        self.game.start_level(5, terrain_seed=91)

        self.assertFalse(self.game.hard_mode)
        self.assertIs(type(self.game.enemy_ai), main.EnemyAI)

    def test_hard_ai_recruits_a_composed_army_and_issues_attack_move_orders(self):
        self.game.campaign_hard_mode = True
        self.game.start_level(3, terrain_seed=103)
        self.game.enemy_essence = 15000
        ai = self.game.enemy_ai

        starting_count = len(ai._controller_army())
        ai.update(.05)

        army = ai._controller_army()
        self.assertGreater(len(army), starting_count)
        self.assertEqual(ai.state, main.AIState.ATTACKING)
        self.assertTrue(ai.assault_started)
        self.assertTrue(any(unit.order_pos is not None for unit in army))
        self.assertGreater(sum(unit.kind == "archer" for unit in army), 1)
        self.assertGreater(sum(unit.kind == "shield" for unit in army), 1)

    def test_editor_hard_mode_round_trips_and_drives_custom_battles(self):
        draft = self.game.editor_draft
        original = draft.hard_mode
        self.game._handle_editor_action("difficulty")
        self.assertIs(draft.hard_mode, not original)

        restored = main.EditorLevelDraft.from_dict(draft.to_dict())
        self.assertEqual(restored.hard_mode, draft.hard_mode)

        draft.hard_mode = True
        self.game.start_custom_level()
        self.assertTrue(self.game.hard_mode)
        self.assertIsInstance(self.game.enemy_ai, main.HardModeAI)


if __name__ == "__main__":
    unittest.main()
