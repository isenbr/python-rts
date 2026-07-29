import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from main import (
    RED_KING_POSITION,
    ENEMY_STARTING_UNITS,
    KING_GUARD_POST_OFFSETS,
    GREEN_KING_POSITION,
    PLAYER_STARTING_UNITS,
    RECRUIT_FIRST_LATERAL_OFFSET,
    RECRUIT_FORWARD_OFFSET,
    RECRUIT_LATERAL_SPACING,
    RECRUIT_SLOTS_PER_COLUMN,
    Game,
    clamp_to_map,
    offset_from,
)


class KingGuardSpawningTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(7))
        self.game.state = "playing"

    def special_units(self, kind=None, team=None):
        return [
            unit for unit in self.game.units
            if (kind is None or unit.kind == kind)
            and (team is None or unit.team == team)
        ]

    def test_reset_spawns_exact_kings_armies_and_mirrored_guards(self):
        expected_count = (
            2 + 4 + len(PLAYER_STARTING_UNITS) + len(ENEMY_STARTING_UNITS)
        )
        self.assertEqual(len(self.game.units), expected_count)
        self.assertEqual(
            [(unit.team, (unit.x, unit.y)) for unit in self.special_units("king")],
            [
                ("green", GREEN_KING_POSITION),
                ("red", RED_KING_POSITION),
            ],
        )
        for team, king_position in (
            ("green", GREEN_KING_POSITION),
            ("red", RED_KING_POSITION),
        ):
            expected_posts = [
                clamp_to_map(offset_from(king_position, guard_offset))
                for guard_offset in KING_GUARD_POST_OFFSETS
            ]
            guards = self.special_units("knight", team)
            self.assertEqual([(guard.x, guard.y) for guard in guards], expected_posts)
            self.assertEqual(
                [guard.home_position for guard in guards],
                expected_posts,
            )
            self.assertEqual(
                expected_posts[0][1] - king_position[1],
                -(expected_posts[1][1] - king_position[1]),
            )

        first_layout = [
            (unit.uid, unit.kind, unit.team, unit.x, unit.y, unit.home_position)
            for unit in self.game.units
        ]
        self.game.reset()
        second_layout = [
            (unit.uid, unit.kind, unit.team, unit.x, unit.y, unit.home_position)
            for unit in self.game.units
        ]
        self.assertEqual(first_layout, second_layout)

    def test_kings_and_knights_are_never_selected_or_ordered(self):
        specials = self.special_units("king") + self.special_units("knight")
        self.game.select_kind()
        self.assertFalse(any(unit.selected for unit in specials))

        for unit in specials:
            screen_position = self.game.world_to_screen(unit.x, unit.y)
            self.game.handle_game_event(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": screen_position},
            ))
            self.game.handle_game_event(pygame.event.Event(
                pygame.MOUSEBUTTONUP,
                {"button": 1, "pos": screen_position},
            ))
            self.assertFalse(unit.selected)

        for unit in specials:
            unit.selected = True
        self.game.issue_order((50, 50))
        self.assertTrue(all(unit.target is None for unit in specials))
        self.assertTrue(all(unit.target_pos is None for unit in specials))

    def test_enemy_ai_never_manages_kings_or_knights(self):
        ai = self.game.enemy_ai
        ai.make_decision()
        special_uids = {
            unit.uid for unit in self.special_units()
            if unit.kind in ("king", "knight")
        }
        for collection in (
            ai.squad,
            ai.reserve,
            ai.defenders,
            ai.recovery_guards,
            set(ai.formation_roles),
            set(ai._known_red_uids),
        ):
            self.assertTrue(special_uids.isdisjoint(collection))
        for guard in self.special_units("knight", "red"):
            self.assertIsNone(ai.choose_target(guard))
            self.assertIsNone(ai.tactical_destination(guard, 1))

    def test_recruits_spawn_in_front_of_each_king_in_stable_slots(self):
        self.game.essence = self.game.enemy_essence = 10_000
        expected = []
        for team, king, initial_count, direction in (
            ("green", self.game.team_king("green"), len(PLAYER_STARTING_UNITS), 1),
            ("red", self.game.team_king("red"), len(ENEMY_STARTING_UNITS), -1),
        ):
            for index, kind in enumerate(("swordsman", "archer", "shield")):
                self.assertTrue(self.game.recruit(kind, team))
                recruit = self.game.units[-1]
                slot = (initial_count + index) % RECRUIT_SLOTS_PER_COLUMN
                position = clamp_to_map((
                    king.x + direction * RECRUIT_FORWARD_OFFSET,
                    king.y + RECRUIT_FIRST_LATERAL_OFFSET
                    + slot * RECRUIT_LATERAL_SPACING,
                ))
                self.assertEqual((recruit.x, recruit.y), position)
                self.assertEqual((recruit.x - king.x) * direction, RECRUIT_FORWARD_OFFSET)
                expected.append((team, kind, position))

        second_game = Game(enemy_rng=random.Random(99))
        second_game.essence = second_game.enemy_essence = 10_000
        actual = []
        for team in ("green", "red"):
            for kind in ("swordsman", "archer", "shield"):
                self.assertTrue(second_game.recruit(kind, team))
                unit = second_game.units[-1]
                actual.append((team, kind, (unit.x, unit.y)))
        self.assertEqual(actual, expected)

    def test_hidden_red_objective_and_guards_do_not_render_or_target(self):
        self.game.visible.clear()
        player = self.game.add_unit(
            "swordsman",
            "green",
            self.game.team_king("red").x - 1,
            self.game.team_king("red").y,
        )
        self.assertIsNone(self.game.find_target(player))
        player.selected = True
        self.game.issue_order((self.game.team_king("red").x, self.game.team_king("red").y))
        self.assertIsNone(player.target)

        self.game.screen.fill((1, 2, 3))
        before = pygame.image.tobytes(self.game.screen, "RGB")
        self.game.draw_unit(self.game.team_king("red"))
        for guard in self.special_units("knight", "red"):
            self.game.draw_unit(guard)
        after = pygame.image.tobytes(self.game.screen, "RGB")
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
