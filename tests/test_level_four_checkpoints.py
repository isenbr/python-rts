import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main
from main import CHECKPOINT_RAID_SIZE, CHECKPOINT_UNITS, Game, UNIT_STATS


class LevelFourCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=123)
        self.game.reset(4)

    def test_level_four_configuration_and_existing_level_income(self):
        self.assertEqual(main.MAP_SIZE, 160)
        self.assertTrue(self.game.level.has_checkpoints)
        self.assertEqual(self.game.level.player_income, 10)
        self.assertEqual(self.game.level.enemy_income, 15)
        self.assertEqual(self.game.essence, 400)
        self.assertEqual(self.game.enemy_essence, 500)

        self.game.reset(3)
        self.assertFalse(self.game.level.has_checkpoints)
        self.assertEqual(self.game.income_rate("green"), 20)
        self.assertEqual(self.game.income_rate("red"), 20)
        self.assertEqual(self.game.checkpoints, [])

    def test_exactly_one_checkpoint_per_biome_is_off_path_and_road_adjacent(self):
        self.assertEqual(len(self.game.checkpoints), 3)
        self.assertEqual(
            {checkpoint.terrain_kind for checkpoint in self.game.checkpoints},
            {"mountain", "forest", "plains"},
        )
        for checkpoint in self.game.checkpoints:
            x, y = checkpoint.cell
            self.assertEqual(self.game.terrain[(x, y)].kind, checkpoint.terrain_kind)
            self.assertNotEqual(self.game.terrain[(x, y)].kind, "path")
            neighbors = (
                (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)
            )
            self.assertTrue(any(
                self.game.terrain.get(cell) is not None
                and self.game.terrain[cell].kind == "path"
                for cell in neighbors
            ))

    def test_checkpoint_placement_is_seed_stable(self):
        first = [(checkpoint.cell, checkpoint.terrain_kind) for checkpoint in self.game.checkpoints]
        self.game.reset(4)
        second = [(checkpoint.cell, checkpoint.terrain_kind) for checkpoint in self.game.checkpoints]
        self.assertEqual(first, second)

    def test_initial_rosters_spawn_and_launch_ten_unit_raid_at_cap(self):
        checkpoint = self.game.checkpoints[0]
        melee, ranged = CHECKPOINT_UNITS[checkpoint.native_faction]
        defenders = [
            unit for unit in self.game.units if unit.uid in checkpoint.defender_uids
        ]
        self.assertEqual([unit.kind for unit in defenders].count(melee), 3)
        self.assertEqual([unit.kind for unit in defenders].count(ranged), 2)

        self.game.update_checkpoints(30)
        self.assertEqual(len(checkpoint.defender_uids), 6)
        newest = max(
            (unit for unit in self.game.units if unit.uid in checkpoint.defender_uids),
            key=lambda unit: unit.uid,
        )
        self.assertEqual(newest.kind, ranged)
        for _ in range(9):
            self.game.update_checkpoints(30)
        raiders = [
            unit for unit in self.game.units
            if (
                unit.checkpoint_uid == checkpoint.uid
                and (
                    unit.raid_target_checkpoint_uid is not None
                    or unit.raid_target_king_team is not None
                )
            )
        ]
        self.assertEqual(len(raiders), CHECKPOINT_RAID_SIZE)
        self.assertEqual(len(checkpoint.defender_uids), 5)

        checkpoint.owner = "green"
        before = len(checkpoint.defender_uids)
        self.game.update_checkpoints(120)
        self.assertEqual(len(checkpoint.defender_uids), before)
        captured_units = [
            unit for unit in self.game.units
            if unit.uid in checkpoint.captured_unit_uids["green"]
        ]
        self.assertEqual(len(captured_units), 2)
        self.assertTrue(all(unit.team == "green" for unit in captured_units))

    def test_captured_hold_produces_native_roster_for_verdant_at_45_second_cap(self):
        checkpoint = self.game.checkpoints[0]
        for unit in self.game.units:
            if unit.uid in checkpoint.defender_uids:
                unit.health = 0
        capturer = self.game.add_unit(
            "swordsman", "green", checkpoint.x, checkpoint.y
        )
        self.game.update_checkpoints(main.CHECKPOINT_CAPTURE_SECONDS)

        self.assertEqual(checkpoint.owner, "green")
        self.game.update_checkpoints(44.9)
        self.assertEqual(checkpoint.captured_unit_uids["green"], set())
        self.game.update_checkpoints(.1)
        first = next(
            unit for unit in self.game.units
            if unit.uid in checkpoint.captured_unit_uids["green"]
        )
        self.assertIn(first.kind, CHECKPOINT_UNITS[checkpoint.native_faction])
        self.assertEqual(first.team, "green")
        self.assertTrue(first.is_player_commandable)

        self.game.update_checkpoints(45 * 5)
        living = [
            unit for unit in self.game.units
            if unit.uid in checkpoint.captured_unit_uids["green"]
            and unit.health > 0
        ]
        self.assertEqual(len(living), main.CAPTURED_CHECKPOINT_MAX_UNITS)

        living[0].health = 0
        previous_max_uid = max(unit.uid for unit in living)
        self.game.update_checkpoints(45)
        replacements = [
            unit for unit in self.game.units
            if unit.uid in checkpoint.captured_unit_uids["green"]
            and unit.health > 0
        ]
        self.assertEqual(len(replacements), main.CAPTURED_CHECKPOINT_MAX_UNITS)
        self.assertGreater(max(unit.uid for unit in replacements), previous_max_uid)
        self.assertGreater(capturer.health, 0)

    def test_captured_hold_produces_native_roster_for_crimson_ai(self):
        checkpoint = self.game.checkpoints[1]
        for unit in self.game.units:
            if unit.uid in checkpoint.defender_uids:
                unit.health = 0
        self.game.add_unit("swordsman", "red", checkpoint.x, checkpoint.y)
        self.game.update_checkpoints(main.CHECKPOINT_CAPTURE_SECONDS)
        self.game.update_checkpoints(main.CAPTURED_CHECKPOINT_SPAWN_SECONDS)

        produced = next(
            unit for unit in self.game.units
            if unit.uid in checkpoint.captured_unit_uids["red"]
        )
        self.assertIn(produced.kind, CHECKPOINT_UNITS[checkpoint.native_faction])
        self.assertEqual(produced.team, "red")
        self.assertTrue(produced.is_enemy_ai_commandable)
        self.game.enemy_ai._assign_available_units()
        assigned = (
            self.game.enemy_ai.squad
            | self.game.enemy_ai.reserve
            | self.game.enemy_ai.defenders
        )
        self.assertIn(produced.uid, assigned)

    def test_native_raid_chooses_nearest_hold_or_king_deterministically(self):
        checkpoint = self.game.checkpoints[0]
        objective = self.game.native_raid_objective(checkpoint)
        candidates = [
            (other, main.dist(
                (checkpoint.x, checkpoint.y), (other.x, other.y)
            ))
            for other in self.game.checkpoints[1:]
        ] + [
            (king, main.dist(
                (checkpoint.x, checkpoint.y), (king.x, king.y)
            ))
            for king in (
                self.game.team_king("green"), self.game.team_king("red")
            )
        ]
        self.assertIs(objective[-1], min(candidates, key=lambda item: item[1])[0])

    def test_native_raiders_leave_home_leash_and_attack_target_hold(self):
        source, target = self.game.checkpoints[:2]
        for other in self.game.checkpoints:
            if other is not source and other is not target:
                other.owner = "green"
        target.x, target.y = source.x + 5, source.y
        for index in range(10):
            unit = self.game.add_unit(
                CHECKPOINT_UNITS[source.native_faction][0],
                source.native_faction,
                source.x,
                source.y,
            )
            unit.checkpoint_uid = source.uid
            source.defender_uids.add(unit.uid)
        while len(source.defender_uids) < main.CHECKPOINT_MAX_DEFENDERS:
            self.game.spawn_checkpoint_defender(source)

        raiders = self.game.launch_native_raid(source)
        self.assertEqual(len(raiders), 10)
        self.assertTrue(all(
            unit.raid_target_checkpoint_uid == target.uid for unit in raiders
        ))
        raider = raiders[0]
        raider.x, raider.y = target.x - .5, target.y
        victim = next(
            unit for unit in self.game.units if unit.uid in target.defender_uids
        )
        victim.x, victim.y = target.x, target.y
        before = victim.health
        self.game.update_unit(raider, 2)
        self.assertLess(victim.health, before)

    def test_native_hold_waits_for_its_active_raid_before_launching_another(self):
        source = self.game.checkpoints[0]
        while len(source.defender_uids) < main.CHECKPOINT_MAX_DEFENDERS:
            self.game.spawn_checkpoint_defender(source)

        first_raid = self.game.launch_native_raid(source)
        self.assertEqual(len(first_raid), CHECKPOINT_RAID_SIZE)
        for _ in range(CHECKPOINT_RAID_SIZE):
            unit = self.game.add_unit(
                CHECKPOINT_UNITS[source.native_faction][0],
                source.native_faction,
                source.x,
                source.y,
            )
            unit.checkpoint_uid = source.uid
            source.defender_uids.add(unit.uid)

        self.assertEqual(len(source.defender_uids), main.CHECKPOINT_MAX_DEFENDERS)
        self.assertEqual(self.game.launch_native_raid(source), [])

    def test_native_raid_captures_checkpoint_for_its_faction(self):
        source, target = self.game.checkpoints[:2]
        for other in self.game.checkpoints[2:]:
            other.owner = "green"
        target.x, target.y = source.x + 5, source.y
        while len(source.defender_uids) < main.CHECKPOINT_MAX_DEFENDERS:
            self.game.spawn_checkpoint_defender(source)
        raiders = self.game.launch_native_raid(source)
        source_faction = source.native_faction
        for unit in self.game.units:
            if unit.uid in target.defender_uids:
                unit.health = 0
        for unit in raiders:
            unit.x, unit.y = target.x, target.y

        self.game.update_checkpoints(main.CHECKPOINT_CAPTURE_SECONDS)

        self.assertEqual(target.owner, source_faction)
        self.assertEqual(target.native_faction, source_faction)
        self.assertFalse(target.ever_captured)
        self.assertTrue({unit.uid for unit in raiders} <= target.defender_uids)
        self.assertTrue(all(
            unit.checkpoint_uid == target.uid
            and unit.raid_target_checkpoint_uid is None
            and unit.raid_target_king_team is None
            for unit in raiders
        ))
        reinforcement = self.game.spawn_checkpoint_defender(target)
        self.assertIsNotNone(reinforcement)
        self.assertEqual(reinforcement.team, source_faction)

    def test_native_raid_does_not_target_faction_owned_checkpoint(self):
        source, friendly, enemy = self.game.checkpoints
        friendly.owner = source.native_faction
        friendly.native_faction = source.native_faction
        friendly.x, friendly.y = source.x + 1, source.y
        enemy.x, enemy.y = source.x + 2, source.y

        objective = self.game.native_raid_objective(source)

        self.assertIsNot(objective[-1], friendly)

    def test_capture_contest_recapture_and_income(self):
        checkpoint = self.game.checkpoints[0]
        for unit in self.game.units:
            if unit.uid in checkpoint.defender_uids:
                unit.health = 0
        green = self.game.add_unit("swordsman", "green", checkpoint.x, checkpoint.y)
        self.game.update_checkpoints(5)
        self.assertEqual(checkpoint.owner, "green")
        self.assertEqual(self.game.income_rate("green"), 15)

        red = self.game.add_unit("swordsman", "red", checkpoint.x, checkpoint.y)
        self.game.update_checkpoints(4.9)
        self.assertEqual(checkpoint.owner, "green")
        self.assertEqual(checkpoint.capture_progress, 0)
        green.x, green.y = 1, 1
        self.game.update_checkpoints(5)
        self.assertEqual(checkpoint.owner, "red")
        self.assertEqual(self.game.income_rate("green"), 10)
        self.assertEqual(self.game.income_rate("red"), 20)
        self.assertGreater(red.health, 0)

    def test_income_update_uses_base_and_owned_checkpoint_rates(self):
        self.game.enemy_ai.update = lambda dt: None
        self.game.checkpoints[0].owner = "green"
        self.game.checkpoints[1].owner = "green"
        self.game.checkpoints[2].owner = "red"
        self.game.state = "playing"
        player_before, enemy_before = self.game.essence, self.game.enemy_essence
        self.game.update(1)
        self.assertEqual(self.game.essence, player_before + 20)
        self.assertEqual(self.game.enemy_essence, enemy_before + 20)

    def test_native_unit_stats_are_unique_and_thematic(self):
        self.assertGreater(UNIT_STATS["dwarf_guard"]["max_health"], UNIT_STATS["shield"]["max_health"])
        self.assertGreater(UNIT_STATS["dwarf_arbalist"]["max_health"], UNIT_STATS["archer"]["max_health"])
        self.assertGreater(UNIT_STATS["elf_ranger"]["attack_range"], UNIT_STATS["archer"]["attack_range"])
        self.assertGreater(
            UNIT_STATS["orc_cleaver"]["damage"] / UNIT_STATS["orc_cleaver"]["cooldown"],
            UNIT_STATS["swordsman"]["damage"] / UNIT_STATS["swordsman"]["cooldown"],
        )
        self.assertEqual(len(main.NATIVE_UNIT_KINDS), 10)
        self.assertEqual(len(set(main.NATIVE_UNIT_KINDS)), 10)

    def test_level_four_ai_uses_checkpoint_strength_gate_before_6000_gold(self):
        ai = self.game.enemy_ai
        ai._assign_available_units()
        while not ai._launch_strength_gate():
            unit = self.game.add_unit("shield", "red", *main.offset_from(main.RED_KING_POSITION, (-5, 0)))
            ai.squad.add(unit.uid)
            ai.formation_roles[unit.uid] = ai.FORMATION_ROLE_BY_KIND[unit.kind]
        self.assertLess(ai._group_essence(ai._squad_units()), ai.TARGET_GROUP_ESSENCE)
        self.assertEqual(ai.last_launch_gate["decision"], "checkpoint_strength_pass")
        self.assertGreaterEqual(ai.last_launch_gate["ratio"], ai.CHECKPOINT_ATTACK_RATIO)
        self.assertIsNotNone(ai.checkpoint_target_uid)

    def test_checkpoint_gate_requires_at_least_fifteen_units(self):
        ai = self.game.enemy_ai
        target = self.game.checkpoints[0]
        for checkpoint in self.game.checkpoints:
            checkpoint.owner = "red"
        target.owner = "green"

        for _ in range(14):
            unit = self.game.add_unit("archer", "red", *ai.rally_point)
            ai.squad.add(unit.uid)
        self.assertFalse(ai._launch_strength_gate())
        self.assertEqual(ai.last_launch_gate["decision"], "checkpoint_force_wait")

        unit = self.game.add_unit("archer", "red", *ai.rally_point)
        ai.squad.add(unit.uid)
        self.assertTrue(ai._launch_strength_gate())
        self.assertEqual(ai.last_launch_gate["decision"], "checkpoint_strength_pass")

    def test_level_four_ai_launches_an_early_checkpoint_wave(self):
        self.game.state = "playing"
        for _ in range(720):
            self.game.update(.25)
            if self.game.enemy_ai.wave_history:
                break
        self.assertTrue(self.game.enemy_ai.wave_history)
        wave = self.game.enemy_ai.wave_history[0]
        self.assertLessEqual(wave["launched_at"], 180)
        self.assertLess(wave["squad_essence"], self.game.enemy_ai.TARGET_GROUP_ESSENCE)
        self.assertGreaterEqual(
            wave["launch_gate"]["ratio"],
            self.game.enemy_ai.CHECKPOINT_ATTACK_RATIO,
        )
        self.assertGreaterEqual(
            sum(wave["composition"].values()),
            self.game.enemy_ai.CHECKPOINT_MIN_ATTACK_UNITS,
        )

    def test_ai_prioritizes_green_checkpoint_then_king_after_all_are_red(self):
        ai = self.game.enemy_ai
        self.game.checkpoints[2].owner = "green"
        objective = ai._select_checkpoint_objective(ai._living_red_units())
        self.assertIs(objective, self.game.checkpoints[2])
        for checkpoint in self.game.checkpoints:
            checkpoint.owner = "red"
        ai.checkpoint_target_uid = None
        self.assertIs(ai.strategic_objective(), self.game.team_king("green"))

    def test_level_selector_and_checkpoint_rendering_do_not_raise(self):
        self.game.draw_level_select()
        self.assertEqual(len(self.game.level_buttons), 1)
        self.assertEqual(self.game.selector_layout["page"], 1)
        self.game.update_visibility()
        self.game.draw_game()


if __name__ == "__main__":
    unittest.main()
