import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    ALL_UNIT_KINDS,
    AUTONOMOUS_GUARD_KINDS,
    ENEMY_PRODUCTION_KINDS,
    OBJECTIVE_UNIT_KINDS,
    NATIVE_UNIT_KINDS,
    PURCHASABLE_UNIT_KINDS,
    RECRUIT_SHORTCUTS,
    SELECTION_SHORTCUTS,
    SWORDSMAN_ATTACK_RANGE,
    SWORDSMAN_BASE_SPEED,
    UNIT_COSTS,
    UNIT_KINDS,
    UNIT_RENDER_SCALES,
    UNIT_STATS,
    CombatStrengthEvaluator,
    Game,
    Unit,
)


class UnitRoleAndRosterTests(unittest.TestCase):
    def setUp(self):
        self.game = Game()

    def test_complete_entity_model_and_purchasable_roster_are_distinct(self):
        self.assertEqual(UNIT_KINDS, ("swordsman", "archer", "shield"))
        self.assertEqual(PURCHASABLE_UNIT_KINDS, UNIT_KINDS)
        self.assertEqual(ENEMY_PRODUCTION_KINDS, UNIT_KINDS)
        self.assertEqual(OBJECTIVE_UNIT_KINDS, ("king",))
        self.assertEqual(AUTONOMOUS_GUARD_KINDS, ("knight",))
        self.assertEqual(
            ALL_UNIT_KINDS,
            (
                "swordsman", "archer", "shield",
                *NATIVE_UNIT_KINDS,
                "king", "knight",
            ),
        )
        self.assertEqual(set(UNIT_COSTS), set(UNIT_KINDS))

    def test_king_has_exact_stats_and_render_footprint_scale(self):
        king = Unit("king", "green", 10, 10)
        self.assertEqual(
            (
                king.max_health,
                king.health,
                king.speed,
                king.damage,
                king.cooldown,
                king.attack_range,
            ),
            (700, 700, SWORDSMAN_BASE_SPEED, 20, .4, 1.5),
        )
        self.assertEqual(UNIT_RENDER_SCALES["king"], 2.2)
        self.assertGreater(
            UNIT_RENDER_SCALES["king"],
            max(
                UNIT_RENDER_SCALES[kind]
                for kind in ("swordsman", "archer", "shield")
            ),
        )

    def test_knight_has_exact_stats_and_shares_swordsman_values(self):
        knight = Unit("knight", "green", 10, 10)
        sword = Unit("swordsman", "green", 10, 10)
        self.assertEqual(
            (
                knight.max_health,
                knight.health,
                knight.damage,
                knight.cooldown,
            ),
            (400, 400, 10, .5),
        )
        self.assertEqual(knight.speed, sword.speed)
        self.assertEqual(knight.speed, SWORDSMAN_BASE_SPEED)
        self.assertEqual(knight.attack_range, sword.attack_range)
        self.assertEqual(knight.attack_range, SWORDSMAN_ATTACK_RANGE)
        self.assertIs(
            UNIT_STATS["knight"]["attack_range"],
            UNIT_STATS["swordsman"]["attack_range"],
        )
        self.assertEqual(UNIT_RENDER_SCALES["knight"], 2.0)
        self.assertGreater(
            UNIT_RENDER_SCALES["knight"],
            max(
                UNIT_RENDER_SCALES[kind]
                for kind in ("swordsman", "archer", "shield")
            ),
        )

    def test_role_and_control_predicates_are_explicit(self):
        green_sword = Unit("swordsman", "green", 0, 0)
        red_sword = Unit("swordsman", "red", 0, 0)
        green_native = Unit("elf_ranger", "green", 0, 0)
        red_native = Unit("dwarf_guard", "red", 0, 0)
        green_king = Unit("king", "green", 0, 0)
        red_knight = Unit("knight", "red", 0, 0)

        self.assertTrue(green_sword.is_purchasable_army_unit)
        self.assertTrue(green_sword.is_player_commandable)
        self.assertFalse(green_sword.is_enemy_ai_commandable)
        self.assertTrue(red_sword.is_enemy_ai_commandable)
        self.assertFalse(red_sword.is_player_commandable)
        self.assertTrue(green_native.is_player_commandable)
        self.assertFalse(green_native.is_enemy_ai_commandable)
        self.assertTrue(red_native.is_enemy_ai_commandable)
        self.assertFalse(red_native.is_player_commandable)

        self.assertTrue(green_king.is_king_objective)
        self.assertFalse(green_king.is_purchasable_army_unit)
        self.assertFalse(green_king.is_player_commandable)
        self.assertFalse(green_king.is_enemy_ai_commandable)

        self.assertTrue(red_knight.is_autonomous_guard)
        self.assertFalse(red_knight.is_purchasable_army_unit)
        self.assertFalse(red_knight.is_player_commandable)
        self.assertFalse(red_knight.is_enemy_ai_commandable)

    def test_king_and_knight_are_absent_from_shortcuts_and_hud_roster(self):
        shortcut_kinds = {
            kind for kind in (*RECRUIT_SHORTCUTS.values(), *SELECTION_SHORTCUTS.values())
            if kind is not None
        }
        self.assertNotIn("king", shortcut_kinds)
        self.assertNotIn("knight", shortcut_kinds)

        self.game.draw_hud()
        hud_kinds = [kind for _, kind in self.game.hud_buttons]
        self.assertEqual(hud_kinds, list(UNIT_KINDS))
        self.assertNotIn("king", self.game.hud_text["army"])
        self.assertNotIn("knight", self.game.hud_text["army"])

    def test_recruitment_rejects_non_purchasable_entities_without_side_effects(self):
        for team, wallet_name in (("green", "essence"), ("red", "enemy_essence")):
            for kind in ("king", "knight"):
                with self.subTest(team=team, kind=kind):
                    setattr(self.game, wallet_name, 10_000)
                    essence_before = getattr(self.game, wallet_name)
                    units_before = list(self.game.units)
                    self.assertFalse(self.game.recruit(kind, team))
                    self.assertEqual(getattr(self.game, wallet_name), essence_before)
                    self.assertEqual(self.game.units, units_before)

    def test_non_army_entities_cannot_be_selected_or_assigned_to_enemy_ai(self):
        king = self.game.add_unit("king", "green", 20, 20)
        knight = self.game.add_unit("knight", "red", 100, 60)
        self.game.select_kind()
        self.assertFalse(king.selected)
        self.assertNotIn(knight, self.game.enemy_ai._living_red_units())

    def test_combat_strength_rejects_unsupported_roles_before_matchup_lookup(self):
        knight = self.game.add_unit("knight", "red", 100, 60)
        with self.assertRaisesRegex(
            ValueError, "purchasable army units only.*knight"
        ):
            CombatStrengthEvaluator().assess(
                (knight,),
                (),
                now=0,
                observation_revision=0,
            )


if __name__ == "__main__":
    unittest.main()
