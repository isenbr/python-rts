import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main
from main import Game, LastSeenPlayerUnit, TerrainCell, UNIT_STATS


class NativePassiveTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=9)
        self.game.reset(4)
        self.game.units.clear()
        self.game.terrain = {
            cell: TerrainCell("plains", 0) for cell in self.game.terrain
        }

    def test_dwarf_guard_and_braced_arbalist_damage_reduction(self):
        archer = self.game.add_unit("archer", "green", 20, 20)
        guard = self.game.add_unit("dwarf_guard", "dwarf", 21, 20)
        self.game.attack(archer, guard)
        self.assertAlmostEqual(guard.max_health - guard.health, 35.0)

        attacker = self.game.add_unit("swordsman", "green", 30, 30)
        arbalist = self.game.add_unit("dwarf_arbalist", "dwarf", 31, 30)
        self.game.update_unit(arbalist, 1.0)
        self.assertTrue(arbalist.braced)
        self.game.attack(attacker, arbalist)
        self.assertAlmostEqual(arbalist.max_health - arbalist.health, 3.75)
        self.game.move_unit_toward(arbalist, (32, 30), .25)
        self.assertFalse(arbalist.braced)
        self.assertEqual(arbalist.stationary_time, 0.0)

    def test_bladedancer_ignores_only_forest_slowing(self):
        self.game.terrain = {
            cell: TerrainCell("forest", 0) for cell in self.game.terrain
        }
        dancer = self.game.add_unit("elf_bladedancer", "elf", 20.5, 20.5)
        sword = self.game.add_unit("swordsman", "green", 30.5, 20.5)
        self.game.move_unit_toward(dancer, (25.5, 20.5), 1)
        self.game.move_unit_toward(sword, (35.5, 20.5), 1)
        self.assertAlmostEqual(dancer.x - 20.5, dancer.speed)
        self.assertAlmostEqual(sword.x - 30.5, sword.speed * .75)

    def test_ranger_kites_and_fires_after_moving_within_leash(self):
        checkpoint = self.game.checkpoints[1]
        checkpoint.defender_uids.clear()
        ranger = self.game.add_unit(
            "elf_ranger", checkpoint.native_faction,
            checkpoint.x + 2, checkpoint.y,
        )
        ranger.checkpoint_uid = checkpoint.uid
        checkpoint.defender_uids.add(ranger.uid)
        target = self.game.add_unit(
            "swordsman", "green", checkpoint.x, checkpoint.y
        )
        before_position = ranger.x, ranger.y
        self.game.update_unit(ranger, .25)
        self.assertNotEqual((ranger.x, ranger.y), before_position)
        self.assertLess(target.health, target.max_health)
        self.assertLessEqual(
            main.dist((ranger.x, ranger.y), (checkpoint.x, checkpoint.y)),
            main.ELF_RANGER_KITE_LEASH + 1e-9,
        )

    def test_orc_splash_hits_only_nearest_secondary_and_spear_threshold(self):
        cleaver = self.game.add_unit("orc_cleaver", "orc", 20, 20)
        primary = self.game.add_unit("swordsman", "green", 21, 20)
        nearest = self.game.add_unit("swordsman", "green", 21.3, 20)
        third = self.game.add_unit("swordsman", "green", 21.5, 20)
        self.game.attack(cleaver, primary)
        self.assertEqual(primary.health, primary.max_health - cleaver.damage)
        self.assertEqual(nearest.health, nearest.max_health - cleaver.damage * .5)
        self.assertEqual(third.health, third.max_health)

        spear = self.game.add_unit("orc_spear_thrower", "orc", 30, 30)
        victim = self.game.add_unit("swordsman", "green", 31, 30)
        spear.health = spear.max_health * .5
        self.game.attack(spear, victim)
        self.assertEqual(victim.max_health - victim.health, spear.damage)
        victim.health = victim.max_health
        spear.health -= .01
        spear.attack_timer = 0
        self.game.attack(spear, victim)
        self.assertAlmostEqual(victim.max_health - victim.health, spear.damage * 1.35)


class CheckpointSupportAndInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=123)
        self.game.reset(4)

    def clear_checkpoint(self, checkpoint):
        for unit in self.game.units:
            if unit.uid in checkpoint.defender_uids:
                unit.health = 0
        checkpoint.defender_uids.clear()

    def test_owned_hold_heals_army_only_and_suppresses_benefits_under_attack(self):
        checkpoint = self.game.checkpoints[0]
        self.clear_checkpoint(checkpoint)
        checkpoint.owner = "green"
        army = self.game.add_unit("swordsman", "green", checkpoint.x + 4, checkpoint.y)
        king = self.game.team_king("green")
        native = self.game.add_unit("dwarf_guard", "dwarf", checkpoint.x, checkpoint.y)
        outside = self.game.add_unit("swordsman", "green", checkpoint.x + 4.01, checkpoint.y)
        for unit in (army, king, native, outside):
            unit.health = max(1, unit.health - 10)
        self.game.update_checkpoints(1)
        self.assertEqual(army.health, army.max_health - 9)
        self.assertEqual(king.health, king.max_health - 10)
        self.assertEqual(native.health, native.max_health - 10)
        self.assertEqual(outside.health, outside.max_health - 10)
        self.assertEqual(self.game.checkpoint_income("green"), 5)

        self.game.add_unit("swordsman", "red", checkpoint.x, checkpoint.y)
        health = army.health
        self.game.update_checkpoints(1)
        self.assertTrue(checkpoint.under_attack)
        self.assertFalse(checkpoint.income_active)
        self.assertEqual(self.game.checkpoint_income("green"), 0)
        self.assertEqual(army.health, health)

    def test_owned_hold_vision_ignores_forest_and_discovery_persists(self):
        checkpoint = self.game.checkpoints[0]
        checkpoint.owner = "green"
        self.game.terrain = {
            cell: TerrainCell("forest", 0) for cell in self.game.terrain
        }
        self.game.update_visibility()
        cx, cy = checkpoint.cell
        self.assertIn((cx + 12, cy), self.game.visible)
        self.assertTrue(checkpoint.discovered)
        checkpoint.owner = "red"
        self.game.units[:] = [
            unit for unit in self.game.units if unit.team != "green"
        ]
        self.game.update_visibility()
        self.assertTrue(checkpoint.discovered)

    def test_unknown_bar_entry_is_not_clickable_and_discovered_entry_centers(self):
        self.game.update_visibility()
        self.game.draw_checkpoint_objective_bar()
        checkpoint = self.game.checkpoints[0]
        rect = next(rect for rect, item in self.game.checkpoint_bar_entries
                    if item is checkpoint)
        checkpoint.discovered = False
        before = tuple(self.game.camera)
        self.game.handle_game_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center
        ))
        self.assertEqual(tuple(self.game.camera), before)
        checkpoint.discovered = True
        self.game.handle_game_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center
        ))
        self.assertLessEqual(
            main.dist(self.game.camera, (checkpoint.x, checkpoint.y)), 1.0
        )


class CheckpointAiAndSelectorTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=1)
        self.game.reset(4)

    def test_projected_launch_diagnostics_and_native_production_shares(self):
        ai = self.game.enemy_ai
        checkpoint = self.game.checkpoints[0]
        ai.checkpoint_target_uid = checkpoint.uid
        ai.state = main.AIState.RALLYING
        self.assertEqual(
            ai.production_target_shares(),
            ai.CHECKPOINT_PRODUCTION_SHARES["dwarf"],
        )
        checkpoint.owner = "green"
        self.assertNotEqual(
            ai.production_target_shares(),
            ai.CHECKPOINT_PRODUCTION_SHARES["dwarf"],
        )

        checkpoint.owner = checkpoint.native_faction
        ai.squad.clear()
        for index in range(ai.CHECKPOINT_MIN_ATTACK_UNITS):
            unit = self.game.add_unit("shield", "red", *ai.rally_point)
            ai.squad.add(unit.uid)
            ai.formation_roles[unit.uid] = ai.FORMATION_ROLE_BY_KIND[unit.kind]
        ai._launch_strength_gate()
        diagnostic = ai.last_launch_gate
        for field in (
            "target", "eta", "projected_defender_count",
            "projected_defender_strength", "projected_defender_composition",
            "projected_attacker_composition", "ratio",
        ):
            self.assertIn(field, diagnostic)
        self.assertGreaterEqual(
            diagnostic["projected_defender_count"],
            len(checkpoint.defender_uids),
        )

    def test_orc_attack_strongly_favors_archers_by_essence(self):
        ai = self.game.enemy_ai
        checkpoint = next(
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.native_faction == "orc"
        )
        ai.checkpoint_target_uid = checkpoint.uid
        ai.state = main.AIState.ATTACKING

        self.assertEqual(ai.production_target_shares(), {
            "swordsman": .10,
            "archer": .70,
            "shield": .20,
        })

    def test_green_checkpoint_estimate_uses_only_last_seen_units(self):
        ai = self.game.enemy_ai
        checkpoint = self.game.checkpoints[0]
        checkpoint.owner = "green"
        hidden = self.game.add_unit("shield", "green", checkpoint.x, checkpoint.y)
        self.assertNotIn(hidden, ai._checkpoint_defenders(checkpoint))
        ai.last_seen_player_army[hidden.uid] = LastSeenPlayerUnit(
            hidden.uid, hidden.kind, hidden.x, hidden.y, hidden.health, 0.0
        )
        self.assertEqual(
            [unit.uid for unit in ai._checkpoint_defenders(checkpoint)],
            [hidden.uid],
        )

    def test_last_seen_native_kind_strength_uses_canonical_max_health(self):
        ai = self.game.enemy_ai
        snapshot = LastSeenPlayerUnit(
            999, "orc_spear_thrower", 10, 10,
            UNIT_STATS["orc_spear_thrower"]["max_health"] * .49, 0.0,
        )
        opponent = self.game.add_unit("swordsman", "red", 11, 10)
        strength = ai._raw_group_strength((snapshot,), (opponent,))
        self.assertGreater(strength, 0)

    def test_grouped_ranged_units_receive_uncapped_strength_bonus(self):
        ai = self.game.enemy_ai
        opponent = self.game.add_unit("swordsman", "green", 50, 50)
        archers = tuple(
            self.game.add_unit("archer", "red", 10 + index, 10)
            for index in range(5)
        )

        clustered = ai._raw_group_strength(archers, (opponent,))
        for index, archer in enumerate(archers):
            archer.x = 10 + index * (ai.RANGED_GROUP_RADIUS + 1)
        separated = ai._raw_group_strength(archers, (opponent,))

        self.assertAlmostEqual(clustered, separated * 1.4)

    def test_selector_metadata_keyboard_navigation_and_play_routing(self):
        self.game.draw_level_select()
        self.assertEqual(self.game.selected_level_page, 1)
        self.game.handle_level_select_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_RIGHT
        ))
        self.assertEqual(self.game.selected_level_page, 2)
        self.game.handle_level_select_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_4
        ))
        self.assertEqual(self.game.selected_level_page, 4)
        self.assertEqual(main.LEVELS[4].preview_type, "three_checkpoints")
        self.game.handle_level_select_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_RETURN
        ))
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.level_number, 4)

    def test_representative_native_hold_is_captured_within_300_seconds(self):
        self.game.state = "playing"
        for _ in range(1200):
            self.game.update(.25)
            if any(checkpoint.owner == "red" for checkpoint in self.game.checkpoints):
                break
        self.assertTrue(any(
            checkpoint.owner == "red" for checkpoint in self.game.checkpoints
        ))


if __name__ == "__main__":
    unittest.main()
