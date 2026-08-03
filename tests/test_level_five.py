import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main
from main import (
    Game,
    LARGE_CHECKPOINT_PROFILE,
    LEVEL_FIVE_STANDARD_CHECKPOINT_PROFILE,
    STANDARD_CHECKPOINT_PROFILE,
)


class LevelFiveGenerationTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=73)
        self.game.reset(5)

    def test_level_five_has_three_standard_and_two_large_edge_holds(self):
        self.assertEqual(main.MAP_SIZE, 160)
        self.assertEqual(len(self.game.checkpoints), 5)
        standard = [
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.profile is LEVEL_FIVE_STANDARD_CHECKPOINT_PROFILE
        ]
        large = [
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.profile is LARGE_CHECKPOINT_PROFILE
        ]
        self.assertEqual(len(standard), 3)
        self.assertEqual(len(large), 2)
        self.assertTrue(all(checkpoint.profile.income == 10 for checkpoint in standard))
        self.assertTrue(all(checkpoint.profile.income == 20 for checkpoint in large))
        self.assertEqual(
            {checkpoint.native_faction for checkpoint in large},
            {"demon", "frost_giant"},
        )
        self.assertLess(large[0].y, main.MAP_SIZE * .2 + 1)
        self.assertGreaterEqual(large[1].y, main.MAP_SIZE * .8)
        for checkpoint in large:
            x, y = checkpoint.cell
            self.assertNotEqual(self.game.terrain[(x, y)].kind, "path")
            self.assertTrue(any(
                self.game.terrain.get(cell) is not None
                and self.game.terrain[cell].kind == "path"
                for cell in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            ))

    def test_large_faction_assignment_and_positions_are_seed_stable(self):
        first = [
            (checkpoint.native_faction, checkpoint.cell)
            for checkpoint in self.game.checkpoints
            if checkpoint.profile is LARGE_CHECKPOINT_PROFILE
        ]
        self.game.reset(5)
        second = [
            (checkpoint.native_faction, checkpoint.cell)
            for checkpoint in self.game.checkpoints
            if checkpoint.profile is LARGE_CHECKPOINT_PROFILE
        ]
        self.assertEqual(first, second)

    def test_level_four_checkpoint_profiles_are_unchanged(self):
        self.game.reset(4)
        self.assertEqual(len(self.game.checkpoints), 3)
        self.assertTrue(all(
            checkpoint.profile is STANDARD_CHECKPOINT_PROFILE
            for checkpoint in self.game.checkpoints
        ))
        self.assertTrue(all(
            checkpoint.profile.income == 5 for checkpoint in self.game.checkpoints
        ))

    def test_level_five_income_is_profile_specific(self):
        small = next(
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.profile is LEVEL_FIVE_STANDARD_CHECKPOINT_PROFILE
        )
        large = next(
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.profile is LARGE_CHECKPOINT_PROFILE
        )
        self.assertEqual(self.game.income_rate("green"), 10)
        self.assertEqual(self.game.income_rate("red"), 30)
        small.owner = large.owner = "green"
        self.assertEqual(self.game.income_rate("green"), 40)
        small.owner = large.owner = "red"
        self.assertEqual(self.game.income_rate("red"), 60)


class LargeCheckpointBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=73)
        self.game.reset(5)
        self.large = [
            checkpoint for checkpoint in self.game.checkpoints
            if checkpoint.profile is LARGE_CHECKPOINT_PROFILE
        ]

    def defenders(self, checkpoint):
        return [
            unit for unit in self.game.units
            if unit.uid in checkpoint.defender_uids and unit.health > 0
        ]

    def test_initial_roster_and_profile_values(self):
        checkpoint = self.large[0]
        melee, ranged = main.CHECKPOINT_UNITS[checkpoint.native_faction]
        defenders = self.defenders(checkpoint)
        self.assertEqual(len(defenders), 10)
        self.assertEqual(sum(unit.kind == melee for unit in defenders), 6)
        self.assertEqual(sum(unit.kind == ranged for unit in defenders), 4)
        self.assertEqual(checkpoint.spawn_timer, 10)
        self.assertEqual(checkpoint.profile.max_defenders, 100)
        self.assertEqual(checkpoint.profile.raid_threshold, 70)
        self.assertEqual(checkpoint.profile.raid_size, 50)

    def test_reaching_seventy_launches_fifty_toward_opposite_hold(self):
        source, target = self.large
        melee = main.CHECKPOINT_UNITS[source.native_faction][0]
        while len(source.defender_uids) < 69:
            unit = self.game.add_unit(melee, source.native_faction, source.x, source.y)
            unit.checkpoint_uid = source.uid
            source.defender_uids.add(unit.uid)
        source.spawn_count = 69
        source.spawn_timer = 0

        self.game.update_checkpoints(0)

        self.assertEqual(len(source.defender_uids), 20)
        raiders = [
            unit for unit in self.game.units
            if unit.checkpoint_uid == source.uid
            and unit.raid_target_checkpoint_uid == target.uid
        ]
        self.assertEqual(len(raiders), 50)

    def test_large_hold_caps_at_one_hundred_without_a_raid_target(self):
        source, opposite = self.large
        opposite.owner = "green"
        for king in (self.game.team_king("green"), self.game.team_king("red")):
            king.health = 0
        melee = main.CHECKPOINT_UNITS[source.native_faction][0]
        while len(source.defender_uids) < 100:
            unit = self.game.add_unit(melee, source.native_faction, source.x, source.y)
            unit.checkpoint_uid = source.uid
            source.defender_uids.add(unit.uid)
        self.assertEqual(self.game.launch_native_raid(source), [])
        self.assertIsNone(self.game.spawn_checkpoint_defender(source))
        self.assertEqual(len(source.defender_uids), 100)

    def test_level_five_ai_requires_twenty_attackers_for_holds_and_king(self):
        checkpoint = self.game.checkpoints[0]
        checkpoint.owner = "green"
        checkpoint.defender_uids.clear()
        ai = self.game.enemy_ai
        ai.squad.clear()
        for _ in range(19):
            unit = self.game.add_unit("shield", "red", *ai.rally_point)
            ai.squad.add(unit.uid)
            ai.formation_roles[unit.uid] = ai.FORMATION_ROLE_BY_KIND[unit.kind]
        self.assertFalse(ai._launch_strength_gate())
        twentieth = self.game.add_unit("shield", "red", *ai.rally_point)
        ai.squad.add(twentieth.uid)
        ai.formation_roles[twentieth.uid] = ai.FORMATION_ROLE_BY_KIND[twentieth.kind]
        self.assertTrue(ai._launch_strength_gate())

        for item in self.game.checkpoints:
            item.owner = "red"
        ai.squad.clear()
        for _ in range(19):
            unit = self.game.add_unit("archer", "red", *ai.rally_point)
            ai.squad.add(unit.uid)
            ai.formation_roles[unit.uid] = ai.FORMATION_ROLE_BY_KIND[unit.kind]
        self.assertFalse(ai._launch_strength_gate())
        twentieth = self.game.add_unit("archer", "red", *ai.rally_point)
        ai.squad.add(twentieth.uid)
        ai.formation_roles[twentieth.uid] = ai.FORMATION_ROLE_BY_KIND[twentieth.kind]
        self.assertTrue(ai._launch_strength_gate())


class LevelFiveUnitAndInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=73)
        self.game.reset(5)
        self.game.units.clear()

    def test_new_unit_stats_and_ai_profiles_are_exact(self):
        expected = {
            "demon_reaver": (500, 1.0, 30, .5, 1.1),
            "infernal_warlock": (180, .75, 90, 1.8, 6.0),
            "frost_colossus": (650, .45, 50, 1.2, 1.4),
            "ice_hurler": (250, .5, 85, 2.5, 7.0),
        }
        for kind, values in expected.items():
            stats = main.UNIT_STATS[kind]
            self.assertEqual(
                (
                    stats["max_health"], stats["speed"], stats["damage"],
                    stats["cooldown"], stats["attack_range"],
                ),
                values,
            )
        self.assertEqual(main.EnemyAI.CHECKPOINT_PRODUCTION_SHARES["demon"], {
            "archer": .60, "shield": .30, "swordsman": .10,
        })
        self.assertEqual(
            main.EnemyAI.CHECKPOINT_PRODUCTION_SHARES["frost_giant"],
            {"archer": .55, "shield": .40, "swordsman": .05},
        )

    def test_demon_lifesteal_and_warlock_splash_are_bounded(self):
        reaver = self.game.add_unit("demon_reaver", "demon", 20, 20)
        victim = self.game.add_unit("swordsman", "green", 21, 20)
        reaver.health -= 100
        self.game.attack(reaver, victim)
        self.assertEqual(reaver.health, 415)

        warlock = self.game.add_unit("infernal_warlock", "demon", 30, 30)
        primary = self.game.add_unit("shield", "green", 31, 30)
        secondary = [
            self.game.add_unit("shield", "green", 31 + index * .1, 30.5)
            for index in range(4)
        ]
        self.game.attack(warlock, primary)
        damaged_secondaries = [u for u in secondary if u.health < u.max_health]
        self.assertEqual(len(damaged_secondaries), 3)
        self.assertTrue(all(
            unit.max_health - unit.health == 45 for unit in damaged_secondaries
        ))

    def test_frost_slows_refresh_without_stacking_and_expire(self):
        colossus = self.game.add_unit("frost_colossus", "frost_giant", 20, 20)
        victim = self.game.add_unit("swordsman", "green", 21, 20)
        self.game.attack(colossus, victim)
        self.assertEqual(victim.slow_multiplier, .6)
        self.assertEqual(victim.slow_timer, 2)
        self.game.apply_movement_slow(victim, .7, 2)
        self.assertEqual(victim.slow_multiplier, .6)
        self.game.update_unit(victim, 2)
        self.assertEqual(victim.slow_multiplier, 1)
        self.assertEqual(victim.slow_timer, 0)

    def test_ice_hurler_slows_primary_and_three_splash_targets(self):
        hurler = self.game.add_unit("ice_hurler", "frost_giant", 30, 30)
        primary = self.game.add_unit("shield", "green", 31, 30)
        secondary = [
            self.game.add_unit("shield", "green", 31 + index * .1, 30.5)
            for index in range(4)
        ]
        self.game.attack(hurler, primary)
        self.assertEqual(primary.slow_multiplier, .7)
        slowed = [unit for unit in secondary if unit.slow_multiplier == .7]
        self.assertEqual(len(slowed), 3)

    def test_last_stand_selector_contains_one_clickable_title(self):
        self.game.selected_level_page = 5
        self.game.state = "level_select"
        self.game.draw_level_select()
        self.assertEqual(self.game.selector_layout["page"], 5)
        self.assertEqual(set(self.game.selector_layout), {"title", "play", "page"})
        self.assertEqual(len(self.game.level_buttons), 1)
        self.assertEqual(self.game.level_nav_buttons, [])
        self.assertEqual(self.game.level_dot_rects, [])
        self.game.handle_level_select_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=self.game.selector_layout["play"].center,
        ))
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.level_number, 5)

    def test_key_five_selects_level_five(self):
        self.game.selected_level_page = 1
        self.game.handle_level_select_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_5
        ))
        self.assertEqual(self.game.selected_level_page, 5)


if __name__ == "__main__":
    unittest.main()
