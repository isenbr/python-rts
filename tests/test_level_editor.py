import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main
from main import (
    AIState, EditorHold, EditorLevelDraft, Game, TerrainCell, UNIT_KINDS,
    make_random_editor_draft,
)


class LevelEditorTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=23)

    def test_default_editor_opens_on_an_expanded_playable_map(self):
        draft = self.game.editor_draft
        self.assertEqual(draft.map_size, 200)
        self.assertEqual(len(draft.terrain), 200 * 200)
        self.assertEqual(draft.available_units, set(UNIT_KINDS))
        self.assertEqual(len(draft.holds), 3)
        self.assertTrue(draft.fog_of_war)

    def test_editor_controls_cover_requested_level_settings(self):
        draft = self.game.editor_draft
        self.game._handle_editor_action("income:green:+")
        self.game._handle_editor_action("income:red:-")
        self.game._handle_editor_action("fog")
        self.game._handle_editor_action("available:archer")
        self.game._handle_editor_action("count:green:shield:+")
        self.assertEqual(draft.green_income, 25)
        self.assertEqual(draft.red_income, 15)
        self.assertFalse(draft.fog_of_war)
        self.assertNotIn("archer", draft.available_units)
        self.assertEqual(draft.green_starting_counts["shield"], 2)

        old_position = draft.green_start
        self.game.editor_tool = "green_start"
        self.game._apply_editor_tool((30, 40))
        self.assertNotEqual(draft.green_start, old_position)
        self.assertEqual(draft.green_start, (30.5, 40.5))

        self.game.editor_tool = "forest"
        self.game.editor_brush_size = 3
        self.game._apply_editor_tool((70, 80))
        self.assertTrue(all(
            draft.terrain[(x, y)].kind == "forest"
            for x in range(69, 72) for y in range(79, 82)
        ))

    def test_draft_round_trip_preserves_all_editable_fields(self):
        original = self.game.editor_draft
        restored = EditorLevelDraft.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_randomized_map_preserves_settings_and_builds_playable_geography(self):
        draft = self.game.editor_draft
        draft.resize(60)
        draft.green_income = 35
        draft.red_income = 45
        draft.fog_of_war = False
        draft.available_units = {"swordsman", "shield"}
        draft.green_starting_counts["shield"] = 7
        before_settings = (
            draft.green_income,
            draft.red_income,
            draft.fog_of_war,
            set(draft.available_units),
            dict(draft.green_starting_counts),
            dict(draft.red_starting_counts),
        )

        randomized = make_random_editor_draft(draft, random.Random(9127))

        self.assertEqual(randomized.map_size, 60)
        self.assertEqual(len(randomized.terrain), 60 * 60)
        self.assertEqual(len(randomized.holds), 3)
        self.assertEqual(len({(hold.x, hold.y) for hold in randomized.holds}), 3)
        self.assertEqual(
            {randomized.terrain[(hold.x, hold.y)].kind for hold in randomized.holds},
            {"plains", "forest", "mountain"},
        )
        self.assertIn("path", {cell.kind for cell in randomized.terrain.values()})
        self.assertEqual(
            (
                randomized.green_income,
                randomized.red_income,
                randomized.fog_of_war,
                randomized.available_units,
                randomized.green_starting_counts,
                randomized.red_starting_counts,
            ),
            before_settings,
        )

    def test_randomize_editor_action_replaces_the_map(self):
        self.game.editor_draft.resize(60)
        original = self.game.editor_draft
        original_terrain = original.terrain
        revision = self.game.editor_revision

        self.game._handle_editor_action("randomize")

        self.assertIsNot(self.game.editor_draft, original)
        self.assertIsNot(self.game.editor_draft.terrain, original_terrain)
        self.assertEqual(self.game.editor_draft.map_size, 60)
        self.assertEqual(self.game.editor_revision, revision + 1)
        self.assertIn("Randomized 60 × 60", self.game.editor_notice)

    def test_randomizer_options_control_generated_map(self):
        self.game.editor_draft.resize(60)
        self.game._set_editor_randomizer_value("hold_count", 7)
        self.game._set_editor_randomizer_value("hold_connections", 0)
        self.game._set_editor_randomizer_value("path_amount", 0)
        self.game._set_editor_randomizer_value("terrain:plains", 0)
        self.game._set_editor_randomizer_value("terrain:forest", 100)
        self.game._set_editor_randomizer_value("terrain:mountain", 0)

        self.game._handle_editor_action("randomize")

        draft = self.game.editor_draft
        self.assertEqual(len(draft.holds), 7)
        self.assertNotIn("path", {cell.kind for cell in draft.terrain.values()})
        self.assertTrue(all(
            draft.terrain[(hold.x, hold.y)].kind == "forest"
            for hold in draft.holds
        ))

    def test_full_hold_connection_ratio_connects_every_hold_to_a_path(self):
        self.game.editor_draft.resize(60)
        draft = make_random_editor_draft(
            self.game.editor_draft,
            random.Random(447),
            hold_count=8,
            hold_connection_ratio=1,
            path_amount=.25,
        )

        for hold in draft.holds:
            self.assertTrue(any(
                draft.terrain.get((hold.x + dx, hold.y + dy), TerrainCell("plains", 0)).kind
                == "path"
                for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if dx or dy
            ))

    def test_randomizer_tab_exposes_draggable_sliders(self):
        self.game.editor_tab = "randomizer"
        self.game.draw_level_editor()
        sliders = {slider["key"]: slider for slider in self.game.editor_sliders}
        self.assertEqual(
            set(sliders),
            {
                "map_size", "hold_count", "hold_connections", "path_amount",
                "terrain:plains", "terrain:forest", "terrain:mountain",
            },
        )

        map_slider = sliders["map_size"]
        self.game.handle_level_editor_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": map_slider["track"].midleft},
        ))
        self.assertEqual(self.game.editor_draft.map_size, 60)
        self.game.handle_level_editor_event(pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"button": 1, "pos": map_slider["track"].midleft},
        ))

        hold_slider = sliders["hold_count"]
        event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": hold_slider["track"].midright},
        )
        self.game.handle_level_editor_event(event)
        self.assertEqual(self.game.editor_random_hold_count, 12)
        self.game.handle_level_editor_event(pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"button": 1, "pos": hold_slider["track"].midright},
        ))
        self.assertIsNone(self.game.editor_slider_dragging)

    def test_custom_level_uses_editor_terrain_holds_armies_and_economy(self):
        draft = self.game.editor_draft
        draft.resize(60)
        draft.fog_of_war = False
        draft.green_income = 35
        draft.red_income = 45
        draft.available_units = {"swordsman", "shield"}
        draft.green_starting_counts = {
            "swordsman": 1, "archer": 2, "shield": 0,
        }
        draft.red_starting_counts = {
            "swordsman": 0, "archer": 1, "shield": 2,
        }
        draft.terrain[(10, 10)] = TerrainCell("mountain", 2)

        self.game.start_custom_level()

        self.assertTrue(self.game.custom_level_active)
        self.assertEqual(main.MAP_SIZE, 60)
        self.assertEqual(self.game.level.player_units, ("swordsman", "shield"))
        self.assertEqual(self.game.terrain[(10, 10)].kind, "mountain")
        self.assertEqual(len(self.game.checkpoints), len(draft.holds))
        self.assertEqual(self.game.income_rate("green"), 35)
        self.assertEqual(self.game.income_rate("red"), 45)
        self.assertFalse(self.game.fog_of_war_enabled)
        self.assertTrue(all(
            checkpoint.profile.income == 10
            for checkpoint in self.game.checkpoints
        ))
        self.game.checkpoints[0].owner = "green"
        self.assertEqual(self.game.income_rate("green"), 45)
        self.assertEqual(
            sum(unit.team == "green" and unit.kind == "archer"
                for unit in self.game.units),
            2,
        )
        self.assertEqual(
            sum(unit.team == "red" and unit.kind == "shield"
                for unit in self.game.units),
            2,
        )

    def test_custom_ai_garrisons_each_capture_then_targets_next_nearest_hold(self):
        draft = self.game.editor_draft
        draft.resize(60)
        draft.holds = [
            EditorHold(12, 30),
            EditorHold(47, 30),
            EditorHold(32, 30),
        ]
        draft.green_start = (5.0, 30.0)
        draft.red_start = (53.0, 30.0)
        draft.green_starting_counts = {kind: 0 for kind in UNIT_KINDS}
        draft.red_starting_counts = {kind: 0 for kind in UNIT_KINDS}
        self.game.start_custom_level()
        ai = self.game.enemy_ai
        nearest = self.game.checkpoints[1]
        next_nearest = self.game.checkpoints[2]
        self.game.checkpoints[0].owner = "green"

        self.assertIs(ai.strategic_objective(), nearest)

        king_garrison = [
            self.game.add_unit("shield", "red", *main.RED_KING_POSITION)
            for _ in range(ai.CUSTOM_KING_GARRISON_SIZE)
        ]
        ai._assign_available_units()
        self.assertEqual(
            ai.reserve, {unit.uid for unit in king_garrison},
        )

        for unit in self.game.units:
            if unit.uid in nearest.defender_uids:
                unit.health = 0
        attackers = []
        for index in range(ai.CUSTOM_CHECKPOINT_GARRISON_SIZE + 5):
            unit = self.game.add_unit(
                "swordsman", "red", nearest.x, nearest.y
            )
            unit.x += .01 * index
            attackers.append(unit)
            ai.squad.add(unit.uid)
            ai.formation_roles[unit.uid] = ai.FORMATION_ROLE_BY_KIND[unit.kind]
        ai.state = AIState.ATTACKING
        ai.wave_start_strength = len(attackers)

        self.game.update_checkpoints(main.CHECKPOINT_CAPTURE_SECONDS)
        ai.make_decision()

        self.assertEqual(nearest.owner, "red")
        self.assertEqual(ai.state, AIState.RALLYING)
        self.assertIs(ai.strategic_objective(), next_nearest)
        self.assertEqual(ai.checkpoint_target_uid, next_nearest.uid)
        self.assertEqual(len(ai.reserve), ai.CUSTOM_KING_GARRISON_SIZE)
        self.assertEqual(
            ai.reserve, {unit.uid for unit in king_garrison},
        )
        checkpoint_garrison = ai.checkpoint_guards[nearest.uid]
        self.assertEqual(
            len(checkpoint_garrison), ai.CUSTOM_CHECKPOINT_GARRISON_SIZE
        )
        self.assertTrue(checkpoint_garrison <= {unit.uid for unit in attackers})
        continuing_attackers = [
            unit for unit in attackers if unit.uid not in checkpoint_garrison
        ]
        self.assertEqual(len(continuing_attackers), 5)
        self.assertTrue(all(unit.uid in ai.squad for unit in continuing_attackers))
        self.assertTrue(all(
            unit.target_pos is not None
            and main.dist(unit.target_pos, (nearest.x, nearest.y)) <= 1.25 + 1e-9
            for unit in attackers if unit.uid in checkpoint_garrison
        ))

        intruder = self.game.add_unit(
            "swordsman", "green", nearest.x - 2, nearest.y
        )
        self.game.rebuild_unit_spatial_hash()
        self.game.update_visibility()
        self.assertIs(ai.choose_target(attackers[0]), intruder)
        intruder.health = 0

        king_garrison[0].health = 0
        reinforcements = [
            self.game.add_unit("shield", "red", *main.RED_KING_POSITION)
            for _ in range(
                ai.CHECKPOINT_MIN_ATTACK_UNITS - len(continuing_attackers)
            )
        ]
        ai._assign_available_units()
        self.assertEqual(len(ai.reserve), ai.CUSTOM_KING_GARRISON_SIZE)
        self.assertFalse(ai._launch_strength_gate())
        final_reinforcement = self.game.add_unit(
            "shield", "red", *main.RED_KING_POSITION
        )
        ai._assign_available_units()
        self.assertIn(final_reinforcement.uid, ai.squad)
        self.assertTrue(all(
            unit.uid not in ai.squad
            for unit in attackers if unit.uid in checkpoint_garrison
        ))
        for unit in self.game.units:
            if unit.uid in next_nearest.defender_uids:
                unit.health = 0
        self.assertTrue(ai._launch_strength_gate())
        ai._launch_wave()
        self.assertEqual(ai.state, AIState.ATTACKING)
        self.assertEqual(ai.checkpoint_target_uid, next_nearest.uid)

        fallen_king_guard = next(
            unit for unit in king_garrison if unit.health > 0
        )
        fallen_king_guard.health = 0
        king_replacement = self.game.add_unit(
            "shield", "red", *main.RED_KING_POSITION
        )
        fallen_hold_uid = min(checkpoint_garrison)
        fallen_hold_guard = next(
            unit for unit in attackers if unit.uid == fallen_hold_uid
        )
        fallen_hold_guard.health = 0
        hold_replacement = self.game.add_unit(
            "swordsman", "red", *main.RED_KING_POSITION
        )
        ai._cleanup_squad()
        ai._reinforce_custom_garrisons_from_unassigned()
        self.assertEqual(len(ai.reserve), ai.CUSTOM_KING_GARRISON_SIZE)
        self.assertIn(king_replacement.uid, ai.reserve)
        self.assertEqual(
            len(ai.checkpoint_guards[nearest.uid]),
            ai.CUSTOM_CHECKPOINT_GARRISON_SIZE,
        )
        self.assertIn(
            hold_replacement.uid, ai.checkpoint_guards[nearest.uid]
        )


if __name__ == "__main__":
    unittest.main()
