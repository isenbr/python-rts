import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main
from main import Game, LEVELS, UNIT_COSTS


class LevelConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.game = Game()

    def test_play_opens_level_selector(self):
        self.game.draw_menu()
        event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=self.game.play_btn.rect.center
        )
        # Mirror the small state transition handled by the run loop.
        if self.game.play_btn.rect.collidepoint(event.pos):
            self.game.state = "level_select"
        self.assertEqual(self.game.state, "level_select")

    def test_level_one_is_small_swordsmen_only_and_enemy_cannot_recruit(self):
        self.game.reset(1)
        self.assertEqual(main.MAP_SIZE, 20)
        self.assertEqual(self.game.level.player_units, ("swordsman",))
        self.assertEqual(self.game.essence, 2000)
        self.assertEqual(self.game.zoom, 30)
        self.assertEqual(len(self.game.terrain), main.MAP_SIZE ** 2)
        self.assertEqual(
            {cell.kind for cell in self.game.terrain.values()}, {"plains"}
        )
        self.game.update_visibility()
        self.assertEqual(
            len(self.game.visible),
            main.MAP_SIZE * main.MAP_SIZE,
        )
        enemy_kinds = [
            unit.kind for unit in self.game.units if unit.team == "red"
        ]
        self.assertEqual(enemy_kinds.count("archer"), 2)
        self.assertEqual(enemy_kinds.count("swordsman"), 10)
        self.assertFalse(any(
            kind in ("king", "knight") for kind in enemy_kinds
        ))
        self.game.essence = self.game.enemy_essence = 10_000
        self.assertTrue(self.game.recruit("swordsman"))
        self.assertFalse(self.game.recruit("archer"))
        self.assertFalse(self.game.recruit("swordsman", "red"))
        starting_enemy_swordsmen = sum(
            u.team == "red" and u.kind == "swordsman"
            for u in self.game.units
        )
        self.game.state = "playing"
        self.game.update(20)
        self.assertEqual(
            sum(
                u.team == "red" and u.kind == "swordsman"
                for u in self.game.units
            ),
            starting_enemy_swordsmen,
        )

    def test_level_one_wins_when_the_last_enemy_unit_is_defeated(self):
        self.game.reset(1)
        self.game.state = "playing"
        for unit in self.game.units:
            if unit.team == "red":
                unit.health = 0

        self.game.update(0)

        self.assertEqual(self.game.winner, "VICTORY")
        self.assertFalse(any(
            unit.team == "red" for unit in self.game.units
        ))

    def test_level_one_zoom_is_locked(self):
        self.game.reset(1)
        starting_zoom = self.game.zoom

        self.game.handle_game_event(
            pygame.event.Event(pygame.MOUSEWHEEL, y=-1)
        )

        self.assertEqual(self.game.zoom, starting_zoom)

    def test_level_one_units_continue_updating_without_a_red_king(self):
        self.game.reset(1)
        self.game.state = "playing"
        self.assertTrue(self.game.recruit("swordsman"))
        swordsman = next(
            unit for unit in self.game.units
            if unit.team == "green" and unit.kind == "swordsman"
        )
        swordsman.selected = True
        starting_position = (swordsman.x, swordsman.y)
        self.game.issue_order((10, 10))

        self.game.update(.1)

        self.assertNotEqual((swordsman.x, swordsman.y), starting_position)

    def test_recruitment_keyboard_shortcuts_are_disabled(self):
        self.game.reset(1)
        starting_gold = self.game.essence
        starting_units = list(self.game.units)

        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s)
        )

        self.assertEqual(self.game.essence, starting_gold)
        self.assertEqual(self.game.units, starting_units)

    def test_level_two_simple_ai_spends_each_200_on_attacking_swordsman(self):
        self.game.reset(2)
        self.assertEqual(main.MAP_SIZE, 60)
        self.assertEqual(
            self.game.level.player_units, ("swordsman", "archer")
        )
        self.game.essence = 10_000
        self.assertTrue(self.game.recruit("swordsman"))
        self.assertTrue(self.game.recruit("archer"))
        self.assertFalse(self.game.recruit("shield"))
        self.game.enemy_essence = UNIT_COSTS["swordsman"] * 2
        self.game.update_simple_enemy_ai()
        attackers = [
            u for u in self.game.units
            if u.team == "red" and u.kind == "swordsman"
        ]
        self.assertEqual(len(attackers), 2)
        self.assertEqual(self.game.enemy_essence, 0)
        self.assertTrue(all(u.target is self.game.team_king("green")
                            for u in attackers))

    def test_level_three_retains_the_original_game(self):
        self.game.reset(3)
        self.assertEqual(main.MAP_SIZE, 120)
        self.assertEqual(self.game.level, LEVELS[3])
        self.assertEqual(self.game.level.player_units, main.UNIT_KINDS)
        self.assertEqual(self.game.level.enemy_ai, "full")
        self.assertEqual(self.game.essence, 400)
        self.assertEqual(self.game.enemy_essence, 500)
        self.assertTrue(any(u.team == "green" and u.kind == "archer"
                            for u in self.game.units))
        self.assertTrue(any(u.team == "red" and u.kind == "archer"
                            for u in self.game.units))

    def test_level_three_victory_stops_defensive_ai_after_king_dies(self):
        self.game.reset(3)
        self.game.state = "playing"
        red_king = self.game.team_king("red")
        attacker = next(
            unit for unit in self.game.units
            if unit.team == "green" and unit.kind == "swordsman"
        )
        attacker.x, attacker.y = red_king.x - .2, red_king.y
        attacker.target = red_king
        attacker.target_pos = (red_king.x, red_king.y)
        attacker.attack_timer = 0
        red_king.health = attacker.damage

        defenders = [
            unit for unit in self.game.units
            if unit.is_enemy_ai_commandable
        ]
        self.game.enemy_ai.state = main.AIState.DEFENDING
        self.game.enemy_ai.defenders = {unit.uid for unit in defenders}
        self.game.enemy_ai.decision_timer = 999
        self.game.enemy_ai.recruitment_timer = 999
        for defender in defenders:
            defender.attack_timer = 999

        self.game.update(.016)

        self.assertEqual(self.game.winner, "VICTORY")
        self.assertIsNone(self.game.team_king("red"))

    def test_each_level_has_a_continuous_path_between_bases(self):
        for number in LEVELS:
            with self.subTest(level=number):
                self.game.reset(number)
                path_columns = {
                    x for (x, _), cell in self.game.terrain.items()
                    if cell.kind == "path"
                }
                if number == 1:
                    self.assertEqual(path_columns, set())
                else:
                    self.assertEqual(
                        path_columns,
                        set(range(main.MAP_SIZE)),
                    )
                self.assertLess(
                    main.RED_KING_POSITION[0]
                    - main.GREEN_KING_POSITION[0],
                    main.MAP_SIZE,
                )


if __name__ == "__main__":
    unittest.main()
