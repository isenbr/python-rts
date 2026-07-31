import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from main import (
    AIState,
    Game,
    MAP_SIZE,
    MAP_CENTER,
    PLAYER_AUTO_ATTACK_RADIUS,
    PLAYER_RECRUIT_ENGAGE_RADIUS,
    UNIT_COSTS,
    UNIT_KINDS,
    UNIT_RENDER_SCALES,
    UNIT_STATS,
    WORLD_MAX,
    WORLD_MIN,
    Unit,
    dist,
)
from simulate_enemy_ai import simulate


class GameTestCase(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(7))
        self.game.state = "playing"


class ExistingMechanicsTests(GameTestCase):
    def test_unit_statistics_and_recruitment_costs(self):
        sword = Unit("swordsman", "green", 0, 0)
        archer = Unit("archer", "green", 0, 0)
        self.assertEqual((sword.health, sword.speed, sword.damage, sword.cooldown, sword.attack_range),
                         (100, 1, 5, .5, 1.02))
        self.assertEqual((archer.health, archer.speed, archer.damage, archer.cooldown, archer.attack_range),
                         (20, .7, 50, 4 / 3, 5))
        self.assertEqual(UNIT_COSTS["swordsman"], 200)
        self.assertEqual(UNIT_COSTS["archer"], 500)
        before = len(self.game.units)
        self.assertTrue(self.game.recruit("swordsman"))
        self.assertEqual(self.game.essence, 200)
        self.assertEqual(len(self.game.units), before + 1)
        self.assertFalse(self.game.recruit("archer"))

    def test_existing_unit_configuration_is_complete(self):
        self.assertEqual(UNIT_KINDS, ("swordsman", "archer", "shield"))
        self.assertEqual(UNIT_STATS, {
            "swordsman": {
                "max_health": 100, "speed": 1, "damage": 5,
                "cooldown": .5, "attack_range": 1.02,
            },
            "archer": {
                "max_health": 20, "speed": .7, "damage": 50,
                "cooldown": 4 / 3, "attack_range": 5,
            },
            "shield": {
                "max_health": 200, "speed": .8, "damage": 5,
                "cooldown": 1, "attack_range": 1.02,
            },
            "king": {
                "max_health": 700, "speed": 1, "damage": 20,
                "cooldown": .4, "attack_range": 1.5,
            },
            "knight": {
                "max_health": 400, "speed": 1, "damage": 10,
                "cooldown": .5, "attack_range": 1.02,
            },
        })
        self.assertEqual(UNIT_COSTS, {
            "swordsman": 200, "archer": 500, "shield": 300,
        })
        self.assertEqual(UNIT_RENDER_SCALES, {
            "swordsman": 1.55, "archer": 1.55, "shield": 1.55 * 1.15,
            "king": 2.2, "knight": 2.0,
        })

    def test_initial_bases_and_units_are_inside_map(self):
        self.assertEqual(MAP_SIZE, 120)
        objects = [self.game.team_king("green"), self.game.team_king("red"), *self.game.units]
        for obj in objects:
            with self.subTest(obj=obj):
                self.assertLessEqual(WORLD_MIN, obj.x)
                self.assertLessEqual(obj.x, WORLD_MAX)
                self.assertLessEqual(WORLD_MIN, obj.y)
                self.assertLessEqual(obj.y, WORLD_MAX)

    def test_recruited_units_spawn_inside_map(self):
        self.game.essence = self.game.enemy_essence = 10_000
        for team in ("green", "red"):
            for kind in UNIT_KINDS:
                self.assertTrue(self.game.recruit(kind, team))
                recruit = self.game.units[-1]
                self.assertLessEqual(WORLD_MIN, recruit.x)
                self.assertLessEqual(recruit.x, WORLD_MAX)
                self.assertLessEqual(WORLD_MIN, recruit.y)
                self.assertLessEqual(recruit.y, WORLD_MAX)

    def test_new_player_recruit_moves_to_attack_nearby_enemy(self):
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        king = self.game.team_king("green")
        spawn = (
            king.x + 4.0,
            king.y + 1.5,
        )
        enemy = self.game.add_unit(
            "swordsman", "red",
            spawn[0] + PLAYER_RECRUIT_ENGAGE_RADIUS - 1,
            spawn[1],
        )
        self.game.essence = UNIT_COSTS["swordsman"]

        self.assertTrue(self.game.recruit("swordsman"))
        recruit = self.game.units[-1]

        self.assertIs(recruit.target, enemy)
        self.assertEqual(recruit.target_pos, (enemy.x, enemy.y))
        start_x = recruit.x
        self.game.update_unit(recruit, .25)
        self.assertGreater(recruit.x, start_x)

    def test_new_player_recruit_does_not_seek_distant_enemy(self):
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        king = self.game.team_king("green")
        self.game.add_unit(
            "swordsman", "red",
            king.x + 4.0 + PLAYER_RECRUIT_ENGAGE_RADIUS + 1,
            king.y + 1.5,
        )
        self.game.essence = UNIT_COSTS["swordsman"]

        self.assertTrue(self.game.recruit("swordsman"))
        recruit = self.game.units[-1]

        self.assertIsNone(recruit.target)
        self.assertIsNone(recruit.target_pos)

    def test_move_orders_and_movement_clamp_to_map_bounds(self):
        selected = [
            unit for unit in self.game.units if unit.is_player_commandable
        ]
        for unit in selected:
            unit.selected = True
        self.game.issue_order((-100, MAP_SIZE + 100))
        for unit in selected:
            self.assertGreaterEqual(unit.target_pos[0], WORLD_MIN)
            self.assertLessEqual(unit.target_pos[0], WORLD_MAX)
            self.assertGreaterEqual(unit.target_pos[1], WORLD_MIN)
            self.assertLessEqual(unit.target_pos[1], WORLD_MAX)
        mover = selected[0]
        mover.x, mover.y = WORLD_MIN, WORLD_MAX
        mover.target_pos = (-100, MAP_SIZE + 100)
        self.game.update_unit(mover, 10)
        self.assertEqual((mover.x, mover.y), (WORLD_MIN, WORLD_MAX))

    def test_archer_moves_at_configured_speed(self):
        sword = self.game.add_unit("swordsman", "green", 10, 10)
        archer = self.game.add_unit("archer", "green", 10, 12)

        self.game.move_unit_toward(sword, (20, 10), 1)
        self.game.move_unit_toward(archer, (20, 12), 1)

        sword_distance = dist((10, 10), (sword.x, sword.y))
        archer_distance = dist((10, 12), (archer.x, archer.y))
        self.assertEqual(sword_distance, 1)
        self.assertAlmostEqual(archer_distance, .7)

    def test_camera_clamping_and_recentering_cover_smaller_map(self):
        for zoom in (5, 13, 30):
            self.game.zoom = zoom
            for position in ((-100, -100), (MAP_SIZE + 100, MAP_SIZE + 100)):
                self.game.camera[:] = position
                self.game.clamp_camera()
                left, top = self.game.screen_to_world((0, 0))
                right, bottom = self.game.screen_to_world(
                    (self.game.screen.get_width(), self.game.screen.get_height() - 126)
                )
                if right - left <= MAP_SIZE:
                    self.assertGreaterEqual(left, -1e-9)
                    self.assertLessEqual(right, MAP_SIZE + 1e-9)
                else:
                    self.assertEqual(self.game.camera[0], MAP_CENTER)
                if bottom - top <= MAP_SIZE:
                    self.assertGreaterEqual(top, -1e-9)
                    self.assertLessEqual(bottom, MAP_SIZE + 1e-9)
                else:
                    self.assertEqual(self.game.camera[1], MAP_CENTER)
        self.game.zoom = 30
        self.game.camera[:] = (MAP_SIZE, MAP_SIZE)
        self.game.handle_game_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_SPACE,
        ))
        self.assertLess(self.game.camera[0], MAP_CENTER)
        self.assertEqual(self.game.camera[1], MAP_CENTER)

    def test_fog_tiles_never_leave_new_bounds(self):
        edge_scouts = (
            (WORLD_MIN, WORLD_MIN),
            (WORLD_MIN, WORLD_MAX),
            (WORLD_MAX, WORLD_MIN),
            (WORLD_MAX, WORLD_MAX),
        )
        for x, y in edge_scouts:
            self.game.add_unit("swordsman", "green", x, y)
        self.game.update_visibility()
        self.assertTrue(self.game.visible)
        self.assertTrue(self.game.explored)
        for x, y in self.game.visible | self.game.explored:
            self.assertLessEqual(0, x)
            self.assertLess(x, MAP_SIZE)
            self.assertLessEqual(0, y)
            self.assertLess(y, MAP_SIZE)

    def test_starting_armies_do_not_overlap_bases_or_each_other(self):
        for team, king in (
            ("green", self.game.team_king("green")), ("red", self.game.team_king("red"))
        ):
            army = [
                unit for unit in self.game.units
                if unit.team == team and not unit.is_king_objective
            ]
            for unit in army:
                self.assertGreaterEqual(dist((unit.x, unit.y), (king.x, king.y)), 3)
            for index, first in enumerate(army):
                for second in army[index + 1:]:
                    self.assertGreater(
                        dist((first.x, first.y), (second.x, second.y)), 0
                    )

    def test_roads_and_tactical_destinations_are_inside_new_map(self):
        self.assertTrue(self.game.terrain)
        for x, y in self.game.terrain:
            self.assertLessEqual(0, x)
            self.assertLess(x, MAP_SIZE)
            self.assertLessEqual(0, y)
            self.assertLess(y, MAP_SIZE)
        red_archer = next(
            unit for unit in self.game.units
            if unit.team == "red" and unit.kind == "archer"
        )
        threat = self.game.add_unit(
            "swordsman", "green", red_archer.x - 1, red_archer.y
        )
        destination = self.game.enemy_ai.tactical_destination(red_archer, .1)
        self.assertIsNotNone(destination)
        self.assertLessEqual(WORLD_MIN, destination[0])
        self.assertLessEqual(destination[0], WORLD_MAX)
        self.assertLessEqual(WORLD_MIN, destination[1])
        self.assertLessEqual(destination[1], WORLD_MAX)
        self.assertGreater(threat.health, 0)

    def test_enemy_rally_and_formation_destinations_are_inside_map(self):
        ai = self.game.enemy_ai
        ai._assign_available_units()
        destinations = [ai.rally_point]
        destinations.extend(
            ai._formation_destination(unit) for unit in ai._squad_units()
        )
        for x, y in destinations:
            self.assertLessEqual(WORLD_MIN, x)
            self.assertLessEqual(x, WORLD_MAX)
            self.assertLessEqual(WORLD_MIN, y)
            self.assertLessEqual(y, WORLD_MAX)

    def test_existing_selection_and_recruitment_by_kind(self):
        self.game.essence = 10_000
        for kind in ("swordsman", "archer"):
            self.game.select_kind(kind)
            selected = [unit for unit in self.game.units if unit.selected]
            self.assertTrue(selected)
            self.assertTrue(all(unit.team == "green" and unit.kind == kind
                                for unit in selected))
            before = len(self.game.units)
            self.assertTrue(self.game.recruit(kind))
            self.assertEqual(len(self.game.units), before + 1)
            self.assertEqual(self.game.units[-1].kind, kind)

    def test_enemy_essence_generation_and_spending(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.enemy_ai.recruitment_timer = 0
        self.game.update(.25)
        self.assertEqual(self.game.enemy_essence, 305)
        self.assertEqual(
            [
                (unit.team, unit.kind) for unit in self.game.units
                if unit.is_purchasable_army_unit
            ],
            [("red", "swordsman")],
        )


class ShieldPlayerFacingTests(GameTestCase):
    def test_shield_recruit_button_kind_label_cost_enabled_and_click(self):
        self.game.essence = 300
        self.game.draw_hud()
        button, kind = self.game.hud_buttons[2]
        self.assertEqual(kind, "shield")
        self.assertEqual(button.text, "Hire Shield")
        self.assertEqual(button.sub, "300 gold")
        self.assertTrue(button.enabled)
        before = len(self.game.units)
        self.game.handle_game_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center,
        ))
        self.assertEqual(len(self.game.units), before + 1)
        self.assertEqual(self.game.units[-1].kind, "shield")
        self.assertEqual(self.game.essence, 0)
        self.game.draw_hud()
        self.assertFalse(self.game.hud_buttons[2][0].enabled)

    def test_q_does_not_recruit_shield(self):
        self.game.essence = 300
        before = list(self.game.units)
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q)
        )
        self.assertEqual(self.game.units, before)
        self.assertEqual(self.game.essence, 300)

    def test_four_selects_only_friendly_shields(self):
        green_shield = self.game.add_unit("shield", "green", 10, 10)
        red_shield = self.game.add_unit("shield", "red", 11, 10)
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4)
        )
        selected = [unit for unit in self.game.units if unit.selected]
        self.assertIn(green_shield, selected)
        self.assertNotIn(red_shield, selected)
        self.assertTrue(all(
            unit.team == "green" and unit.kind == "shield" for unit in selected
        ))

    def test_three_still_selects_every_friendly_unit(self):
        self.game.add_unit("shield", "green", 10, 10)
        self.game.add_unit("shield", "red", 11, 10)
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
        )
        self.assertTrue(all(
            unit.selected == unit.is_player_commandable
            for unit in self.game.units
        ))

    def test_army_summary_includes_shields(self):
        self.game.add_unit("shield", "green", 10, 10)
        self.game.draw_hud()
        self.assertIn("1 shield", self.game.hud_text["army"])

    def test_shield_render_scale_is_about_fifteen_percent_larger(self):
        self.assertAlmostEqual(
            UNIT_RENDER_SCALES["shield"] / UNIT_RENDER_SCALES["swordsman"],
            1.15,
            delta=.01,
        )
        self.assertAlmostEqual(
            UNIT_RENDER_SCALES["shield"] / UNIT_RENDER_SCALES["archer"],
            1.15,
            delta=.01,
        )

    def test_default_hud_controls_fit_without_overlap(self):
        self.game.draw_hud()
        layout = self.game.hud_layout
        for rect in (*layout["buttons"], layout["army"], layout["controls"], layout["king"]):
            self.assertTrue(layout["hud"].contains(rect), rect)
        regions = [*layout["buttons"], layout["army"], layout["controls"]]
        for index, first in enumerate(regions):
            for second in regions[index + 1:]:
                self.assertFalse(first.colliderect(second), (first, second))
        self.assertTrue(all(
            not rect.colliderect(layout["king"]) for rect in regions
        ))

    def test_resized_hud_keeps_king_status_clear_of_controls(self):
        self.game.screen = pygame.display.set_mode((900, 600), pygame.RESIZABLE)
        self.game.draw_hud()
        layout = self.game.hud_layout
        regions = [
            *layout["buttons"],
            layout["army"],
            layout["controls"],
        ]
        self.assertTrue(layout["hud"].contains(layout["king"]))
        self.assertTrue(all(
            not rect.colliderect(layout["king"]) for rect in regions
        ))

    def test_attack_range_and_cooldown(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        attacker = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15, 10)
        self.game.visible.add((15, 10))
        self.game.update_unit(attacker, 0)
        self.assertEqual(target.health, 50)
        self.assertEqual(attacker.attack_timer, 4 / 3)
        self.game.update_unit(attacker, 1)
        self.assertEqual(target.health, 50)
        self.game.update_unit(attacker, 1 / 3)
        self.assertEqual(target.health, 0)

    def test_death_and_target_cleanup(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        attacker = self.game.add_unit("swordsman", "red", 20, 20)
        dead = self.game.add_unit("archer", "green", 21, 20)
        attacker.target = dead
        dead.health = 0
        self.game.enemy_ai.recruitment_timer = 999
        self.game.update(0)
        self.assertIsNone(attacker.target)
        self.assertNotIn(dead, self.game.units)

    def test_targets_killed_late_in_tick_are_cleaned_immediately(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        watcher = self.game.add_unit("swordsman", "red", 20, 20)
        victim = self.game.add_unit("archer", "green", 21, 20)
        killer = self.game.add_unit("archer", "red", 22, 20)
        watcher.target = victim
        watcher.attack_timer = 999
        victim.health = killer.damage
        self.game.enemy_ai.recruitment_timer = 999
        self.game.update(0)
        self.assertNotIn(victim, self.game.units)
        self.assertIsNone(watcher.target)

    def test_new_enemy_units_rally_instead_of_immediately_attacking(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.enemy_essence = 200
        self.assertTrue(self.game.recruit("swordsman", "red"))
        enemy = self.game.units[-1]
        self.assertIsNone(enemy.target_pos)
        self.game.enemy_ai.recruitment_timer = 999
        self.game.update(.25)
        self.assertEqual(self.game.enemy_ai.state, AIState.RALLYING)
        self.assertGreater(enemy.target_pos[0], self.game.team_king("green").x)
        self.assertEqual(
            enemy.target_pos,
            self.game.enemy_ai._formation_destination(enemy),
        )

    def test_player_targeting_is_restricted_by_fog(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        player = self.game.add_unit("archer", "green", 10, 10)
        hidden = self.game.add_unit("swordsman", "red", 12, 10)
        self.assertIsNone(self.game.find_target(player))
        self.game.visible.add((12, 10))
        self.assertIs(self.game.find_target(player), hidden)
        enemy = self.game.add_unit("archer", "red", 11, 10)
        self.assertIs(self.game.find_target(enemy), player)

    def test_idle_player_unit_auto_attacks_enemy_within_five_tiles(self):
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        player = self.game.add_unit("swordsman", "green", 10, 10)
        enemy = self.game.add_unit(
            "swordsman", "red", 10 + PLAYER_AUTO_ATTACK_RADIUS, 10
        )
        self.game.visible.add((int(enemy.x), int(enemy.y)))

        self.game.update_unit(player, .25)

        self.assertIs(player.target, enemy)
        self.assertGreater(player.x, 10)

    def test_idle_player_unit_ignores_enemy_beyond_five_tiles(self):
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        player = self.game.add_unit("swordsman", "green", 10, 10)
        enemy = self.game.add_unit(
            "swordsman", "red", 10 + PLAYER_AUTO_ATTACK_RADIUS + .01, 10
        )
        self.game.visible.add((int(enemy.x), int(enemy.y)))

        self.game.update_unit(player, .25)

        self.assertIsNone(player.target)
        self.assertEqual((player.x, player.y), (10, 10))

    def test_player_order_prevents_idle_auto_attack(self):
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        player = self.game.add_unit("swordsman", "green", 10, 10)
        enemy = self.game.add_unit("swordsman", "red", 12, 10)
        self.game.visible.add((int(enemy.x), int(enemy.y)))
        player.target_pos = (10, 20)

        self.game.update_unit(player, .25)

        self.assertIsNone(player.target)
        self.assertGreater(player.y, 10)

    def test_pause_resume_preserves_match_and_stops_simulation(self):
        unit = self.game.units[0]
        before = (unit.uid, unit.x, unit.y, self.game.essence)
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        )
        self.assertEqual(self.game.state, "paused")
        self.game.update(1)
        self.assertEqual((unit.uid, unit.x, unit.y, self.game.essence), before)

    def test_victory_defeat_and_restart_preserve_core_conditions(self):
        self.game.team_king("red").health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "VICTORY")
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)
        )
        self.assertIsNone(self.game.winner)
        self.game.team_king("green").health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "DEFEAT")
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        )
        self.assertEqual(self.game.state, "menu")


class ShieldUnitTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.enemy_ai._known_red_uids.clear()
        self.game.enemy_ai.recruitment_timer = 999

    def test_shield_cost_and_all_statistics(self):
        shield = Unit("shield", "green", 10, 10)
        self.assertEqual(UNIT_COSTS["shield"], 300)
        self.assertEqual(
            (
                shield.health,
                shield.max_health,
                shield.speed,
                shield.cooldown,
                shield.damage,
                shield.attack_range,
            ),
            (200, 200, .8, 1, 5, 1.02),
        )

    def test_shield_balance_relations_to_swordsman(self):
        shield = Unit("shield", "green", 10, 10)
        sword = Unit("swordsman", "green", 10, 10)
        self.assertEqual(shield.health, sword.health * 2)
        self.assertLess(shield.speed, sword.speed)
        self.assertGreater(shield.cooldown, sword.cooldown)

    def test_recruit_shield_at_exact_cost(self):
        self.game.essence = 300
        self.assertTrue(self.game.recruit("shield"))
        self.assertEqual(self.game.essence, 0)
        self.assertEqual(
            [
                (unit.kind, unit.team) for unit in self.game.units
                if unit.is_purchasable_army_unit
            ],
            [("shield", "green")],
        )

    def test_reject_shield_below_cost_without_state_change(self):
        self.game.essence = 299
        before = (self.game.essence, list(self.game.units), self.game.uid)
        self.assertFalse(self.game.recruit("shield"))
        self.assertEqual(
            (self.game.essence, self.game.units, self.game.uid),
            before,
        )

    def test_invalid_kinds_fail_without_changing_game_state(self):
        before = (
            self.game.essence,
            self.game.enemy_essence,
            list(self.game.units),
            self.game.uid,
        )
        with self.assertRaisesRegex(ValueError, "Invalid unit kind"):
            self.game.recruit("unknown")
        with self.assertRaisesRegex(ValueError, "Invalid unit kind"):
            self.game.recruit("unknown", "red")
        with self.assertRaisesRegex(ValueError, "Invalid unit kind"):
            self.game.add_unit("unknown", "green", 10, 10)
        with self.assertRaisesRegex(ValueError, "Invalid unit kind"):
            Unit("unknown", "green", 10, 10)
        self.assertEqual(
            (
                self.game.essence,
                self.game.enemy_essence,
                self.game.units,
                self.game.uid,
            ),
            before,
        )

    def test_shield_moves_point_eight_units_in_one_second(self):
        shield = self.game.add_unit("shield", "green", 10, 10)
        shield.target_pos = (20, 10)
        self.game.update_unit(shield, 1)
        self.assertAlmostEqual(shield.x, 10.8)
        self.assertEqual(shield.y, 10)

    def test_shield_takes_thirty_percent_damage_from_archers(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        shield = self.game.add_unit("shield", "red", 11, 10)

        self.game.attack(archer, shield)

        self.assertEqual(shield.health, 185)

    def test_archer_damage_reduction_only_applies_to_shields(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        swordsman = self.game.add_unit("swordsman", "red", 11, 10)

        self.game.attack(archer, swordsman)

        self.assertEqual(swordsman.health, 50)

    def test_shield_cooldown_melee_damage_and_target_acquisition(self):
        shield = self.game.add_unit("shield", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 11, 10)
        self.game.visible.add((11, 10))
        self.assertIs(self.game.find_target(shield), target)
        self.game.update_unit(shield, 0)
        self.assertEqual(target.health, 95)
        self.assertEqual(shield.attack_timer, 1)
        self.assertEqual(len(self.game.particles), 1)
        self.assertEqual(self.game.arrows, [])
        self.game.update_unit(shield, .99)
        self.assertEqual(target.health, 95)
        self.game.update_unit(shield, .02)
        self.assertEqual(target.health, 90)

    def test_shield_death_and_target_cleanup(self):
        watcher = self.game.add_unit("shield", "red", 20, 20)
        victim = self.game.add_unit("shield", "green", 21, 20)
        watcher.target = victim
        victim.health = 0
        self.game.update(0)
        self.assertNotIn(victim, self.game.units)
        self.assertIsNone(watcher.target)

    def test_green_and_red_shields_work_with_fog_selection_and_combat(self):
        green = self.game.add_unit("shield", "green", 10, 10)
        red = self.game.add_unit("shield", "red", 11, 10)
        self.game.select_kind("shield")
        self.assertTrue(green.selected)
        self.assertFalse(red.selected)
        self.assertIsNone(self.game.find_target(green))
        self.game.update_visibility()
        self.assertIn((10, 10), self.game.visible)
        self.assertIn((11, 10), self.game.visible)
        self.assertIs(self.game.find_target(green), red)
        self.assertIs(self.game.find_target(red), green)
        self.game.update_unit(green, 0)
        self.game.update_unit(red, 0)
        self.assertEqual((green.health, red.health), (195, 195))

    def test_shield_can_trigger_victory_and_defeat(self):
        green = self.game.add_unit(
            "shield",
            "green",
            self.game.team_king("red").x - UNIT_STATS["shield"]["attack_range"],
            self.game.team_king("red").y,
        )
        self.game.team_king("red").health = green.damage
        green.target = self.game.team_king("red")
        self.game.update(0)
        self.assertEqual(self.game.winner, "VICTORY")

        self.game.reset()
        self.game.state = "playing"
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        red = self.game.add_unit(
            "shield",
            "red",
            self.game.team_king("green").x + UNIT_STATS["shield"]["attack_range"],
            self.game.team_king("green").y,
        )
        self.game.team_king("green").health = red.damage
        red.target = self.game.team_king("green")
        self.game.update(0)
        self.assertEqual(self.game.winner, "DEFEAT")


class ArcherMovementAttackTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.enemy_ai.recruitment_timer = 999

    def test_green_archer_does_not_fire_on_update_it_moves_into_range(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15.1, 10)
        archer.target = target
        self.game.visible.add((15, 10))

        self.game.update_unit(archer, .1)

        self.assertTrue(archer.moved_this_update)
        self.assertEqual(target.health, target.max_health)
        self.assertEqual(self.game.arrows, [])

    def test_red_archer_does_not_fire_while_tactically_retreating(self):
        archer = self.game.add_unit("archer", "red", 20, 20)
        target = self.game.add_unit("swordsman", "green", 22, 20)

        self.game.update_unit(archer, .1)

        self.assertTrue(archer.moved_this_update)
        self.assertLess(archer.x, 20)
        self.assertEqual(target.health, target.max_health)
        self.assertEqual(self.game.arrows, [])

    def test_archer_fires_after_stopping_when_cooldown_permits(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15.04, 10)
        archer.target = target
        self.game.visible.add((15, 10))
        self.game.update_unit(archer, .1)

        self.game.update_unit(archer, 0)

        self.assertFalse(archer.moved_this_update)
        self.assertEqual(target.health, 50)
        self.assertEqual(len(self.game.arrows), 1)

    def test_stationary_archer_with_target_in_range_fires_immediately(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15, 10)
        self.game.visible.add((15, 10))

        self.game.update_unit(archer, 0)

        self.assertFalse(archer.moved_this_update)
        self.assertEqual(target.health, 50)
        self.assertEqual(len(self.game.arrows), 1)

    def test_reached_or_stale_move_destination_does_not_block_firing(self):
        for destination in ((10, 10), (10.01, 10)):
            with self.subTest(destination=destination):
                self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
                self.game.arrows.clear()
                archer = self.game.add_unit("archer", "green", 10, 10)
                target = self.game.add_unit("swordsman", "red", 14, 10)
                archer.target_pos = destination
                self.game.visible.add((14, 10))

                self.game.update_unit(archer, 0)

                self.assertFalse(archer.moved_this_update)
                self.assertEqual(target.health, 50)
                self.assertEqual(len(self.game.arrows), 1)

    def test_continuous_stationary_firing_uses_faster_cooldown(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("shield", "red", 14, 10)
        self.game.visible.add((14, 10))
        self.game.update_unit(archer, 0)
        self.assertEqual(target.health, 185)

        for index in range(2):
            self.game.update_unit(archer, .5)
            self.assertFalse(archer.moved_this_update, index)
            self.assertEqual(target.health, 185, index)
        self.game.update_unit(archer, .5)
        self.assertEqual(target.health, 170)
        self.assertEqual(len(self.game.arrows), 2)

    def test_archer_cannot_move_until_lock_expires_then_moves_immediately(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 14, 10)
        self.game.visible.add((14, 10))
        self.game.update_unit(archer, .1)
        target.health = 0
        archer.target_pos = (20, 10)

        start = (archer.x, archer.y)
        for _ in range(2):
            self.game.update_unit(archer, .6)
            self.assertEqual((archer.x, archer.y), start)
            self.assertFalse(archer.moved_this_update)

        self.game.update_unit(archer, 2 / 15)
        self.assertTrue(archer.moved_this_update)
        self.assertGreater(archer.x, start[0])
        self.assertEqual(archer.movement_lock_timer, 0)

    def test_player_attack_move_order_survives_lock_and_resumes(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15.04, 10)
        destination = (20, 10)
        archer.target_pos = destination
        self.game.visible.add((15, 10))

        self.game.update_unit(archer, .1)
        moved_position = (archer.x, archer.y)
        self.game.update_unit(archer, 0)
        self.assertEqual((archer.x, archer.y), moved_position)
        self.assertEqual(target.health, 50)
        self.assertEqual(archer.target_pos, destination)

        target.health = 0
        self.game.update_unit(archer, .5)
        self.assertFalse(archer.moved_this_update)
        self.assertEqual(archer.target_pos, destination)
        self.game.update_unit(archer, 5 / 6)
        self.assertTrue(archer.moved_this_update)
        self.assertGreater(archer.x, moved_position[0])

    def test_red_archer_retreat_obeys_lock_and_resumes(self):
        archer = self.game.add_unit("archer", "red", 20, 20)
        target = self.game.add_unit("swordsman", "green", 24, 20)
        self.game.update_unit(archer, .1)
        self.assertEqual(target.health, 50)

        target.x = 22
        fired_position = (archer.x, archer.y)
        self.game.update_unit(archer, .5)
        self.assertEqual((archer.x, archer.y), fired_position)
        self.assertIsNotNone(archer.tactical_pos)

        self.game.update_unit(archer, 5 / 6)
        self.assertTrue(archer.moved_this_update)
        self.assertLess(archer.x, fired_position[0])

    def test_lock_applies_only_after_successful_shot(self):
        archer = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15.1, 10)
        archer.target = target
        archer.target_pos = (20, 10)
        self.game.visible.add((15, 10))

        self.game.update_unit(archer, .1)

        self.assertTrue(archer.moved_this_update)
        self.assertEqual(target.health, target.max_health)
        self.assertEqual(archer.movement_lock_timer, 0)

    def test_swordsman_and_shield_movement_is_not_locked(self):
        for kind in ("swordsman", "shield"):
            with self.subTest(kind=kind):
                self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
                unit = self.game.add_unit(kind, "green", 10, 10)
                unit.movement_lock_timer = 1
                unit.target_pos = (20, 10)

                self.game.update_unit(unit, .1)

                self.assertTrue(unit.moved_this_update)
                self.assertGreater(unit.x, 10)

    def test_swordsman_and_shield_melee_attacks_are_unchanged(self):
        for kind, damage in (("swordsman", 5), ("shield", 5)):
            with self.subTest(kind=kind):
                self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
                self.game.particles.clear()
                attacker = self.game.add_unit(kind, "green", 10, 10)
                target = self.game.add_unit("shield", "red", 11, 10)
                self.game.visible.add((11, 10))

                self.game.update_unit(attacker, 0)

                self.assertEqual(target.health, target.max_health - damage)
                self.assertEqual(len(self.game.particles), 1)
                self.assertEqual(self.game.arrows, [])


class EnemyAITests(GameTestCase):
    def set_units(self, *units):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        return [self.game.add_unit(*unit) for unit in units]

    def test_initial_state(self):
        self.assertEqual(self.game.enemy_ai.state, AIState.BUILDING)

    def test_valid_and_invalid_state_transitions(self):
        ai = self.game.enemy_ai
        ai.transition_to(AIState.RALLYING)
        ai.transition_to(AIState.ATTACKING)
        ai.transition_to(AIState.RECOVERING)
        ai.transition_to(AIState.BUILDING)
        with self.assertRaises(ValueError):
            ai.transition_to(AIState.RECOVERING)

    def test_decisions_update_only_on_controlled_interval(self):
        ai = self.game.enemy_ai
        ai.update(.24)
        self.assertEqual(ai.decision_count, 0)
        ai.update(.01)
        self.assertEqual(ai.decision_count, 1)
        ai.update(.5)
        self.assertEqual(ai.decision_count, 3)

    def test_fixed_seed_makes_decisions_deterministic(self):
        def result(seed):
            game = Game(enemy_rng=random.Random(seed))
            game.units[:] = [unit for unit in game.units if unit.is_king_objective]
            game.enemy_essence = 500
            ai = game.enemy_ai
            ai.recruitment_timer = 0
            ai.make_decision()
            unit = game.units[-1]
            unit.target = None
            unit.target_pos = None
            ai.make_decision()
            return unit.kind, ai.recruitment_timer, unit.target_pos

        self.assertEqual(result(1234), result(1234))

    def test_swordsman_prefers_reachable_archer(self):
        sword, enemy_sword, enemy_archer = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "green", 22, 20),
            ("archer", "green", 23, 20),
        )
        self.assertIs(self.game.enemy_ai.choose_target(sword), enemy_archer)

    def test_shield_prefers_reachable_archer(self):
        shield, enemy_sword, enemy_archer = self.set_units(
            ("shield", "red", 20, 20),
            ("swordsman", "green", 22, 20),
            ("archer", "green", 23, 20),
        )
        self.assertIs(self.game.enemy_ai.choose_target(shield), enemy_archer)

    def test_shield_uses_melee_screening_for_allied_archer(self):
        shield, archer, threat = self.set_units(
            ("shield", "red", 20, 22),
            ("archer", "red", 20, 20),
            ("swordsman", "green", 24, 20),
        )
        destination = self.game.enemy_ai.tactical_destination(shield, .25)
        self.assertIsNotNone(destination)
        self.assertGreater(destination[0], archer.x)
        self.assertLess(
            dist(destination, (threat.x, threat.y)),
            dist((archer.x, archer.y), (threat.x, threat.y)),
        )

    def test_archer_prioritizes_vulnerable_or_high_threat_target(self):
        archer, healthy, vulnerable = self.set_units(
            ("archer", "red", 20, 20),
            ("swordsman", "green", 23, 20),
            ("swordsman", "green", 24, 20),
        )
        vulnerable.health = 20
        self.assertIs(self.game.enemy_ai.choose_target(archer), vulnerable)
        vulnerable.health = vulnerable.max_health
        healthy.target = archer
        self.assertIs(self.game.enemy_ai.choose_target(archer), healthy)

    def test_unit_finishes_low_health_target_when_sensible(self):
        sword, healthy, finishable = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "green", 21, 20),
            ("swordsman", "green", 22, 20),
        )
        finishable.health = sword.damage
        self.assertIs(self.game.enemy_ai.choose_target(sword), finishable)

    def test_unit_responds_to_attacker(self):
        sword, nearby, attacker = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "green", 21, 20),
            ("swordsman", "green", 23, 20),
        )
        attacker.target = sword
        self.assertIs(self.game.enemy_ai.choose_target(sword), attacker)

    def test_target_commitment_is_stable_across_updates(self):
        sword, current, slightly_better = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "green", 22, 20),
            ("swordsman", "green", 21.5, 20),
        )
        sword.target = current
        for _ in range(4):
            self.assertIs(self.game.enemy_ai.choose_target(sword), current)
        slightly_better.target = sword
        self.assertIs(self.game.enemy_ai.choose_target(sword), slightly_better)

    def test_invalid_dead_or_distant_targets_are_released(self):
        sword, target = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "green", 21, 20),
        )
        sword.target = target
        target.health = 0
        self.assertIsNone(self.game.enemy_ai.choose_target(sword))
        target.health = target.max_health
        target.x = 40
        sword.target = target
        self.assertIsNone(self.game.enemy_ai.choose_target(sword))
        sword.target = self.game.team_king("red")
        self.assertIsNone(self.game.enemy_ai.choose_target(sword))

    def test_base_defense_threat_receives_increased_priority(self):
        defender, base_threat, other_threat = self.set_units(
            ("archer", "red", 172, 100),
            ("swordsman", "green", 170, 100),
            ("swordsman", "green", 169, 100),
        )
        # Equidistant threats differ only in whether they endanger the king.
        self.game.team_king("red").x = 184
        base_threat.x = 175
        self.assertIs(self.game.enemy_ai.choose_target(defender), base_threat)


class EnemyProductionTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.ai = self.game.enemy_ai
        self.ai._known_red_uids.clear()
        self.ai.recent_losses.clear()
        self.game.enemy_essence = 1000

    def add_red_frontline(self, count=2):
        for index in range(count):
            self.game.add_unit("swordsman", "red", 170, 98 + index)
        self.ai._record_losses()

    def observe_player(self, kinds):
        for index, kind in enumerate(kinds):
            self.game.add_unit(
                kind, "green",
                self.game.team_king("red").x - 5,
                self.game.team_king("red").y + index * .2,
            )
        self.ai._update_strategic_knowledge()

    def learn_player_counter(self, kinds):
        self.ai._learn_victorious_player_composition({
            kind: kinds.count(kind) * UNIT_COSTS[kind]
            for kind in UNIT_KINDS
        })

    def produce_many(self, count):
        self.game.enemy_essence = 100_000
        choices = []
        for _ in range(count):
            kind = self.ai.choose_production()
            choices.append(kind)
            self.assertTrue(self.game.recruit(kind, "red"))
        return choices

    def test_default_production_without_player_information_starts_balancing_essence(self):
        self.assertEqual(self.ai.known_player_composition(), {
            "swordsman": 0, "archer": 0, "shield": 0
        })
        self.assertEqual(self.ai.choose_production(), "swordsman")

    def test_observed_armies_shift_weighted_counter_preference(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 4)
        self.learn_player_counter(["swordsman"] * 4)
        self.assertEqual(self.ai.choose_production(), "archer")
        self.game.units[:] = [u for u in self.game.units if u.is_king_objective or u.team == "red"]
        self.ai.player_knowledge.clear()
        self.observe_player(["archer"] * 4)
        self.learn_player_counter(["archer"] * 4)
        self.assertEqual(self.ai.choose_production(), "shield")

    def test_low_moderate_and_high_observed_archer_threat(self):
        self.add_red_frontline()
        for count, level in ((0, "low"), (3, "moderate"), (6, "high")):
            self.game.units[:] = [u for u in self.game.units if u.is_king_objective or u.team == "red"]
            self.ai.player_knowledge.clear()
            self.observe_player(["archer"] * count)
            scores = self.ai.production_scores()
            self.assertEqual(self.ai.archer_threat_level, level)
            if level == "low":
                low_scores = scores
            else:
                self.assertGreater(scores["shield"], scores["swordsman"])
                self.assertEqual(self.ai.choose_production(), "shield")
        self.assertGreater(
            self.ai.last_production_scores["shield"] - self.ai.last_production_scores["swordsman"],
            low_scores["shield"] - low_scores["swordsman"],
        )

    def test_archer_threat_hysteresis_avoids_threshold_oscillation(self):
        self.add_red_frontline()
        levels = []
        for count in (3, 2, 3, 2, 1):
            self.ai.player_knowledge = {
                10_000 + index: ("archer", self.ai.elapsed)
                for index in range(count)
            }
            self.ai.production_scores()
            levels.append(self.ai.archer_threat_level)
        self.assertEqual(
            levels, ["moderate", "moderate", "moderate", "moderate", "low"]
        )

    def test_stale_archer_information_returns_to_low_threat(self):
        self.add_red_frontline()
        baseline_choice = self.ai.choose_production()
        self.observe_player(["archer"] * 6)
        self.assertEqual(self.ai.choose_production(), "shield")
        self.game.units[:] = [u for u in self.game.units if u.is_king_objective or u.team == "red"]
        self.ai.elapsed += self.ai.PLAYER_KNOWLEDGE_TTL + .01
        self.ai._update_strategic_knowledge()
        self.assertIn(self.ai.choose_production(), UNIT_KINDS)
        self.assertEqual(self.ai.archer_threat_level, "low")

    def test_low_resources_save_for_preferred_shield_instead_of_defaulting_to_sword(self):
        self.add_red_frontline()
        self.observe_player(["archer"] * 6)
        self.game.enemy_essence = UNIT_COSTS["swordsman"]
        self.assertIsNone(self.ai.choose_production())

    def test_resource_constrained_emergency_still_allows_cheap_swordsman(self):
        self.add_red_frontline()
        self.observe_player(["archer"] * 6)
        self.game.enemy_essence = UNIT_COSTS["swordsman"]
        self.assertEqual(
            self.ai.choose_production(self.ai.SERIOUS_THREAT_SCORE),
            "swordsman",
        )

    def test_temporarily_unavailable_preferred_unit_uses_other_composition(self):
        self.add_red_frontline()
        self.observe_player(["archer"] * 6)
        self.learn_player_counter(["archer"] * 6)
        self.ai.unavailable_production_kinds.add("shield")
        self.assertEqual(self.ai.choose_production(), "swordsman")
        self.ai.unavailable_production_kinds.clear()
        self.assertEqual(self.ai.choose_production(), "shield")

    def test_archer_counter_displaces_sword_without_displacing_other_choice(self):
        self.add_red_frontline()
        self.observe_player(["archer"] * 6)
        self.learn_player_counter(["archer"] * 6)
        self.assertEqual(self.ai.choose_production(), "shield")
        self.game.units[:] = [u for u in self.game.units if u.is_king_objective or u.team == "red"]
        self.ai.player_knowledge.clear()
        self.ai.last_seen_player_army.clear()
        self.ai.archer_threat_level = "low"
        self.observe_player(["swordsman"] * 4)
        self.learn_player_counter(["swordsman"] * 4)
        self.assertEqual(self.ai.choose_production(), "archer")

    def test_swordsman_counter_target_overrides_legacy_frontline_score(self):
        self.game.add_unit("archer", "red", 170, 100)
        self.observe_player(["swordsman"] * 5)
        self.learn_player_counter(["swordsman"] * 5)
        self.assertEqual(self.ai.choose_production(), "archer")

    def test_saves_for_archer_when_justified(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 4)
        self.learn_player_counter(["swordsman"] * 4)
        self.game.enemy_essence = 300
        self.assertIsNone(self.ai.choose_production())

    def test_emergency_abandons_archer_savings(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 4)
        self.learn_player_counter(["swordsman"] * 4)
        self.game.enemy_essence = 300
        self.assertEqual(
            self.ai.choose_production(self.ai.SERIOUS_THREAT_SCORE),
            "swordsman",
        )

    def test_recruitment_respects_costs_and_available_essence(self):
        self.game.enemy_essence = UNIT_COSTS["swordsman"] - 1
        self.assertIsNone(self.ai.choose_production())
        self.ai.recruitment_timer = 0
        self.assertIsNone(self.ai._run_production(0))
        self.assertFalse(
            [unit for unit in self.game.units if unit.is_purchasable_army_unit]
        )

    def test_production_has_defined_behavior_in_every_ai_state(self):
        self.add_red_frontline()
        results = {}
        for state in AIState:
            self.ai.state = state
            choice = self.ai.choose_production()
            self.assertIn(choice, UNIT_KINDS)
            self.assertEqual(set(self.ai.last_production_scores), set(UNIT_KINDS))
            results[state] = choice
        self.assertEqual(set(results), set(AIState))

    def test_sighting_does_not_override_neutral_target_in_base_defense(self):
        self.observe_player(["archer"] * 3)
        self.ai.state = AIState.DEFENDING
        self.game.enemy_essence = UNIT_COSTS["shield"]
        self.assertEqual(self.ai.production_target_shares(), {
            kind: 1 / 3 for kind in UNIT_KINDS
        })
        self.assertEqual(self.ai.choose_production(2), "swordsman")

    def test_shield_supports_frontline_and_mixed_armies_without_monoculture(self):
        self.game.add_unit("archer", "red", 170, 100)
        self.assertEqual(self.ai.choose_production(), "shield")
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.add_unit("swordsman", "red", 170, 100)
        self.game.add_unit("archer", "red", 170, 101)
        self.ai.state = AIState.DEFENDING
        self.assertEqual(self.ai.choose_production(2), "shield")
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.add_unit("shield", "red", 170, 100)
        self.assertEqual(self.ai.choose_production(), "swordsman")

    def test_shield_losses_and_production_history_are_complete(self):
        shield = self.game.add_unit("shield", "red", 170, 100)
        self.ai._record_losses()
        before = self.ai.production_scores()["shield"]
        shield.health = 0
        self.ai._record_losses()
        self.assertGreater(self.ai.production_scores()["shield"], before)
        self.ai.state = AIState.DEFENDING
        self.ai.recruitment_timer = 0
        self.game.enemy_essence = 300
        produced = self.ai._run_production(2)
        self.assertEqual(self.ai.production_history[-1]["kind"], produced)
        self.assertEqual(
            set(self.ai.production_history[-1]["scores"]), set(UNIT_KINDS)
        )
        self.assertEqual(
            set(self.ai.production_history[-1]["spent_essence"]), set(UNIT_KINDS)
        )
        self.assertEqual(
            self.ai.production_history[-1]["target_shares"],
            {kind: 1 / 3 for kind in UNIT_KINDS},
        )
        self.assertIn("selected_deficit", self.ai.production_history[-1])

    def test_neutral_target_is_stable_despite_tactical_hysteresis(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"])
        self.ai.last_production_choice = "archer"
        choices = [self.ai.choose_production() for _ in range(8)]
        self.assertEqual(choices, ["shield"] * 8)

    def test_long_no_information_sequence_balances_essence_not_unit_counts(self):
        choices = []
        self.game.enemy_essence = 100_000
        for _ in range(40):
            kind = self.ai.choose_production()
            choices.append(kind)
            self.assertTrue(self.game.recruit(kind, "red"))
        spent = self.ai.production_essence_investment()
        total = sum(spent.values())
        shares = {kind: spent[kind] / total for kind in UNIT_KINDS}
        counts = {kind: choices.count(kind) for kind in UNIT_KINDS}
        self.assertEqual(counts, {
            "swordsman": 19, "archer": 8, "shield": 13,
        })
        self.assertEqual(len(set(counts.values())), len(UNIT_KINDS))
        for share in shares.values():
            self.assertAlmostEqual(share, 1 / 3, delta=.02)
        self.assertLessEqual(
            max(spent.values()) - min(spent.values()),
            max(UNIT_COSTS.values()),
        )

    def test_low_resources_save_for_underfunded_unaffordable_kind(self):
        for kind in ("swordsman",) * 3 + ("shield",) * 2:
            self.game.add_unit(kind, "red", 170, 100)
        self.game.enemy_essence = UNIT_COSTS["shield"]
        self.assertEqual(
            self.ai.production_essence_investment(),
            {"swordsman": 600, "archer": 0, "shield": 600},
        )
        self.assertIsNone(self.ai.choose_production())

    def test_no_information_emergency_has_affordable_fallback(self):
        for kind in ("swordsman",) * 3 + ("shield",) * 2:
            self.game.add_unit(kind, "red", 170, 100)
        self.game.enemy_essence = UNIT_COSTS["swordsman"]
        self.assertEqual(
            self.ai.choose_production(self.ai.SERIOUS_THREAT_SCORE),
            "swordsman",
        )

    def test_unavailable_underfunded_kind_does_not_deadlock(self):
        for kind in ("swordsman",) * 3 + ("shield",) * 2:
            self.game.add_unit(kind, "red", 170, 100)
        self.ai.unavailable_production_kinds.add("archer")
        self.game.enemy_essence = UNIT_COSTS["shield"]
        self.assertIn(self.ai.choose_production(), ("swordsman", "shield"))

    def test_no_information_sequence_is_deterministic_for_fixed_seed(self):
        def sequence(seed):
            game = Game(enemy_rng=random.Random(seed))
            game.units[:] = [unit for unit in game.units if unit.is_king_objective]
            game.enemy_ai._known_red_uids.clear()
            game.enemy_essence = 100_000
            result = []
            for _ in range(40):
                kind = game.enemy_ai.choose_production()
                result.append(kind)
                self.assertTrue(game.recruit(kind, "red"))
            return result

        self.assertEqual(sequence(73), sequence(73))

    def test_long_archer_threat_sequence_displaces_swords_with_shields(self):
        self.observe_player(["archer"] * 6)
        self.learn_player_counter(["archer"] * 6)
        self.game.enemy_essence = 100_000
        choices = []
        for _ in range(40):
            self.ai.last_production_choice = None
            kind = self.ai.choose_production()
            choices.append(kind)
            self.assertTrue(self.game.recruit(kind, "red"))
        self.assertEqual(
            {kind: choices.count(kind) for kind in UNIT_KINDS},
            {"swordsman": 0, "archer": 0, "shield": 40},
        )

    def test_equal_counts_use_player_essence_not_unit_counts(self):
        self.ai._learn_victorious_player_composition({
            kind: UNIT_COSTS[kind] for kind in UNIT_KINDS
        })
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": .3,
            "archer": .2,
            "shield": .5,
        })

    def test_equal_archer_and_shield_essence_converges_to_half_counters(self):
        self.ai._learn_victorious_player_composition({
            "swordsman": 0,
            "archer": UNIT_COSTS["archer"] * 3,
            "shield": UNIT_COSTS["shield"] * 5,
        })
        choices = self.produce_many(60)
        spent = self.ai.production_essence_investment()
        total = sum(spent.values())
        shares = {kind: spent[kind] / total for kind in UNIT_KINDS}
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": .5, "archer": 0.0, "shield": .5,
        })
        self.assertEqual(choices.count("archer"), 0)
        for kind in ("swordsman", "shield"):
            self.assertAlmostEqual(
                shares[kind], .5,
                delta=self.ai.PRODUCTION_SHARE_ROUNDING_TOLERANCE,
            )

    def test_each_player_majority_redirects_to_explicit_counter(self):
        cases = (
            ("swordsman", "archer"),
            ("archer", "shield"),
            ("shield", "swordsman"),
        )
        for player_kind, counter in cases:
            with self.subTest(player_kind=player_kind):
                self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
                self.ai.last_seen_player_army.clear()
                self.ai._learn_victorious_player_composition({
                    kind: UNIT_COSTS[player_kind] * 6
                    if kind == player_kind else 0
                    for kind in UNIT_KINDS
                })
                self.assertEqual(self.ai.choose_production(), counter)

    def test_new_visible_sighting_does_not_overwrite_learned_target(self):
        self.ai._learn_victorious_player_composition({
            "swordsman": UNIT_COSTS["swordsman"] * 4,
            "archer": 0,
            "shield": 0,
        })
        self.assertEqual(self.ai.choose_production(), "archer")
        self.observe_player(["shield"] * 4)
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": 0.0, "archer": 1.0, "shield": 0.0,
        })

    def test_long_mixed_counter_sequence_meets_documented_tolerance(self):
        self.ai._learn_victorious_player_composition({
            "swordsman": UNIT_COSTS["swordsman"] * 5,
            "archer": UNIT_COSTS["archer"] * 2,
            "shield": UNIT_COSTS["shield"] * 5,
        })
        self.produce_many(100)
        target = self.ai.production_target_shares()
        spent = self.ai.production_essence_investment()
        total = sum(spent.values())
        for kind in UNIT_KINDS:
            self.assertAlmostEqual(
                spent[kind] / total,
                target[kind],
                delta=self.ai.PRODUCTION_SHARE_ROUNDING_TOLERANCE,
            )

    def test_stale_player_information_expires(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 3)
        self.assertEqual(self.ai.known_player_composition()["swordsman"], 3)
        self.game.units[:] = [u for u in self.game.units if u.is_king_objective or u.team == "red"]
        self.ai.elapsed += self.ai.PLAYER_KNOWLEDGE_TTL + .01
        self.ai._update_strategic_knowledge()
        self.assertEqual(self.ai.known_player_composition()["swordsman"], 0)

    def test_hidden_distant_units_do_not_enter_ai_knowledge(self):
        self.add_red_frontline()
        self.game.add_unit("archer", "green", 40, 40)
        self.ai._update_strategic_knowledge()
        self.assertEqual(self.ai.known_player_composition()["archer"], 0)

    def test_recent_losses_and_failed_waves_affect_scores(self):
        sword = self.game.add_unit("swordsman", "red", 170, 100)
        self.ai._record_losses()
        before = self.ai.production_scores()["swordsman"]
        sword.health = 0
        self.ai._record_losses()
        self.ai.failed_waves = 1
        after = self.ai.production_scores()["swordsman"]
        self.assertGreater(after, before)


class EnemySquadTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.ai = self.game.enemy_ai
        self.ai.recruitment_timer = 999

    def add_formed_squad(self, kinds=("archer",) * 12):
        units = [
            self.game.add_unit(kind, "red", 170, 100 + index)
            for index, kind in enumerate(kinds)
        ]
        self.ai.make_decision()
        for unit in units:
            if unit.uid in self.ai.squad:
                unit.x, unit.y = self.ai._formation_destination(unit)
        return units

    def remember_player_squad(self, kinds):
        players = [
            self.game.add_unit(
                kind, "green",
                self.game.team_king("red").x - 5,
                self.game.team_king("red").y + index,
            )
            for index, kind in enumerate(kinds)
        ]
        self.ai._update_strategic_knowledge()
        for unit in players:
            unit.x = 10
        self.ai._update_strategic_knowledge()
        return players

    def test_three_rank_roles_and_forward_order(self):
        shield, sword, archer = self.add_formed_squad(
            ("shield", "swordsman", "archer")
        )
        self.assertEqual(self.ai.formation_roles[shield.uid], "shield_rank")
        self.assertEqual(self.ai.formation_roles[sword.uid], "swordsman_rank")
        self.assertEqual(self.ai.formation_roles[archer.uid], "archer_rank")
        destinations = [
            self.ai._formation_destination(unit)
            for unit in (shield, sword, archer)
        ]
        advance = self.ai._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            (self.game.team_king("green").x, self.game.team_king("green").y),
        )
        progress = [
            destination[0] * advance[0] + destination[1] * advance[1]
            for destination in destinations
        ]
        self.assertGreater(progress[0], progress[1])
        self.assertGreater(progress[1], progress[2])

    def test_three_rank_order_uses_non_horizontal_advance_direction(self):
        self.game.team_king("green").x, self.game.team_king("green").y = 20, 20
        self.game.team_king("red").x, self.game.team_king("red").y = 100, 90
        shield, sword, archer = self.add_formed_squad(
            ("shield", "swordsman", "archer")
        )
        advance = self.ai._unit_vector((100, 90), (20, 20))
        progress = []
        for unit in (shield, sword, archer):
            destination = self.ai._formation_destination(unit)
            progress.append(
                destination[0] * advance[0] + destination[1] * advance[1]
            )
        self.assertGreater(progress[0], progress[1])
        self.assertGreater(progress[1], progress[2])

    def test_each_rank_is_laterally_centered_and_uid_ordered(self):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        members = []
        for kind in ("shield", "swordsman", "archer"):
            members.extend(
                self.game.add_unit(kind, "red", 100, 50 + index)
                for index in range(3)
            )
        self.ai.squad = {unit.uid for unit in members}
        for unit in members:
            self.ai._formation_role(unit)
        advance = self.ai._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            (self.game.team_king("green").x, self.game.team_king("green").y),
        )
        side = (-advance[1], advance[0])
        for kind in UNIT_KINDS:
            rank = sorted(
                (unit for unit in members if unit.kind == kind),
                key=lambda unit: unit.uid,
            )
            lateral = [
                destination[0] * side[0] + destination[1] * side[1]
                for destination in (
                    self.ai._formation_destination(unit, members)
                    for unit in rank
                )
            ]
            self.assertAlmostEqual(lateral[1], sum(lateral) / len(lateral))
            self.assertEqual(lateral, sorted(lateral))

    def test_missing_ranks_are_ready_and_keep_remaining_order(self):
        sword, archer = self.add_formed_squad(("swordsman", "archer"))
        sword.x, sword.y = self.ai._formation_destination(sword)
        archer.x, archer.y = self.ai._formation_destination(archer)
        self.assertTrue(self.ai._formation_ready())
        self.assertLess(sword.x, archer.x)

        self.game.units.remove(sword)
        self.ai._cleanup_squad()
        self.assertNotIn(sword.uid, self.ai.formation_roles)
        self.assertTrue(self.ai._formation_ready())

    def test_formation_destinations_clamp_at_map_edges(self):
        self.game.team_king("red").x, self.game.team_king("red").y = WORLD_MIN, WORLD_MIN
        self.game.team_king("green").x, self.game.team_king("green").y = WORLD_MAX, WORLD_MAX
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        members = [
            self.game.add_unit(kind, "red", WORLD_MIN, WORLD_MIN)
            for kind in UNIT_KINDS for _ in range(7)
        ]
        self.ai.squad = {unit.uid for unit in members}
        for unit in members:
            destination = self.ai._formation_destination(
                unit, members, anchor=(WORLD_MIN, WORLD_MIN)
            )
            self.assertTrue(all(
                WORLD_MIN <= coordinate <= WORLD_MAX
                for coordinate in destination
            ))

    def test_advancing_idle_units_restore_three_rank_order(self):
        members = self.add_formed_squad(
            ("shield", "swordsman", "archer")
        )
        for unit in members:
            unit.x, unit.y = self.ai._formation_destination(unit)
        self.ai._launch_strength_gate()
        self.ai._launch_wave()
        advance = self.ai._unit_vector(
            (self.game.team_king("red").x, self.game.team_king("red").y),
            (self.game.team_king("green").x, self.game.team_king("green").y),
        )
        for _ in range(24):
            for unit in members:
                self.game.update_unit(unit, .25)
            self.ai._advance_wave()
            progress = {
                unit.kind: unit.x * advance[0] + unit.y * advance[1]
                for unit in members
            }
            self.assertGreater(progress["shield"], progress["swordsman"])
            self.assertGreater(progress["swordsman"], progress["archer"])

    def test_cleanup_removes_roles_for_living_removed_members(self):
        shield, sword = self.add_formed_squad(("shield", "swordsman"))
        self.ai.squad.remove(shield.uid)
        self.ai._cleanup_squad()
        self.assertNotIn(shield.uid, self.ai.formation_roles)
        self.assertIn(sword.uid, self.ai.formation_roles)

    def test_shields_are_frontline_and_preferred_for_home_reserve(self):
        members = self.add_formed_squad((
            "swordsman", "shield", "archer", "swordsman", "archer",
            "shield", "shield", *("archer",) * 12,
        ))
        sword, shield, archer, sword2, archer2, shield2, shield3 = members[:7]
        self.assertEqual(self.ai.formation_roles[shield3.uid], "shield_rank")
        self.assertEqual(self.ai.formation_roles[archer.uid], "archer_rank")
        reserve_shields = {
            unit.uid for unit in (shield, shield2, shield3)
            if unit.uid in self.ai.reserve
        }
        self.assertEqual(len(reserve_shields), 1)
        self.assertTrue(any(
            unit.uid in self.ai.squad
            and self.ai.formation_roles[unit.uid] == "shield_rank"
            for unit in (shield, shield2, shield3)
        ))

    def test_wave_composition_reports_every_unit_kind(self):
        members = self.add_formed_squad(
            ("swordsman", "shield", "shield", *("archer",) * 11)
        )
        for unit in members:
            if unit.uid in self.ai.squad:
                unit.x, unit.y = self.ai._formation_destination(unit)
        self.ai.make_decision()
        self.assertEqual(
            set(self.ai.wave_history[-1]["composition"]), set(UNIT_KINDS)
        )

    def test_many_cheap_units_below_target_do_not_launch(self):
        members = self.add_formed_squad(("swordsman",) * 29)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        self.assertEqual(self.ai.last_launch_gate["squad_essence"], 5800)
        self.assertEqual(self.ai.wave_number, 0)

    def test_mixed_group_at_exact_target_launches(self):
        kinds = ("archer",) * 10 + ("shield",) * 2 + ("swordsman",) * 2
        self.add_formed_squad(kinds)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertEqual(self.ai.wave_history[-1]["squad_essence"], 6000)

    def test_group_above_target_launches(self):
        self.add_formed_squad(("archer",) * 13)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertGreaterEqual(
            self.ai.wave_history[-1]["squad_essence"],
            self.ai.TARGET_GROUP_ESSENCE,
        )

    def test_maximum_rally_time_cannot_launch_below_target(self):
        self.add_formed_squad(("swordsman",) * 29)
        self.ai.rally_elapsed = self.ai.MAX_RALLY_WAIT
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        self.assertEqual(self.ai.wave_number, 0)

    def test_reserve_does_not_prevent_available_target_wave(self):
        members = self.add_formed_squad(
            ("archer",) * 12 + ("shield",) * 2
        )
        self.assertEqual(len(self.ai.reserve), 2)
        self.assertEqual(
            self.ai._group_essence(self.ai._squad_units()),
            self.ai.TARGET_GROUP_ESSENCE,
        )
        for unit in members:
            if unit.uid in self.ai.squad:
                unit.x, unit.y = self.ai._formation_destination(unit)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_wave_history_reports_squad_essence(self):
        self.add_formed_squad(("archer",) * 12)
        self.ai.make_decision()
        self.assertEqual(self.ai.wave_history[-1]["squad_essence"], 6000)
        self.assertEqual(
            self.ai.wave_history[-1]["launch_gate"]["squad_essence"], 6000
        )

    def test_underpowered_formed_squad_is_held_by_last_seen_strength(self):
        self.remember_player_squad(("swordsman",) * 30)
        self.add_formed_squad()
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        self.assertEqual(
            self.ai.last_launch_gate["decision"], "strength_hold"
        )
        self.assertLess(
            self.ai.last_launch_gate["ratio"],
            self.ai.combat_evaluator.STRONGER_RATIO,
        )

    def test_maximum_rally_wait_cannot_bypass_observed_strength_gate(self):
        self.remember_player_squad(("swordsman",) * 30)
        self.add_formed_squad()
        self.ai.rally_elapsed = self.ai.MAX_RALLY_WAIT
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        self.assertEqual(self.ai.wave_number, 0)

    def test_counter_reinforcements_eventually_open_launch_gate(self):
        self.remember_player_squad(("archer",) * 4)
        members = self.add_formed_squad(("shield",) * 2)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        for index in range(18):
            members.append(self.game.add_unit("shield", "red", 170, 110 + index))
        self.ai.make_decision()
        for unit in members:
            if unit.uid in self.ai.squad:
                unit.x, unit.y = self.ai._formation_destination(unit)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertEqual(
            self.ai.wave_history[-1]["launch_gate"]["decision"],
            "strength_pass",
        )

    def test_strength_margin_launches_after_formation_or_timeout(self):
        self.remember_player_squad(("swordsman",))
        members = self.add_formed_squad(("swordsman",) * 30)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertGreaterEqual(
            self.ai.wave_history[-1]["launch_gate"]["ratio"],
            self.ai.combat_evaluator.STRONGER_RATIO,
        )

    def test_hidden_player_changes_do_not_change_gate_until_observed(self):
        players = self.remember_player_squad(("swordsman",))
        self.add_formed_squad(("swordsman",) * 30)
        first = self.ai._launch_strength_gate()
        first_ratio = self.ai.last_launch_gate["ratio"]
        players[0].health = players[0].max_health * .05
        self.ai._update_strategic_knowledge()
        self.assertEqual(self.ai._launch_strength_gate(), first)
        self.assertEqual(self.ai.last_launch_gate["ratio"], first_ratio)

    def test_new_stronger_observation_immediately_closes_gate(self):
        players = self.remember_player_squad(("swordsman",))
        self.add_formed_squad(("swordsman",) * 30)
        self.assertTrue(self.ai._launch_strength_gate())
        for index in range(39):
            players.append(self.game.add_unit(
                "swordsman", "green",
                self.game.team_king("red").x - 5,
                self.game.team_king("red").y + index,
            ))
        self.ai._update_strategic_knowledge()
        self.assertFalse(self.ai._launch_strength_gate())
        self.assertEqual(
            self.ai.last_launch_gate["decision"], "strength_hold"
        )

    def test_no_observation_bootstrap_uses_legacy_readiness(self):
        self.add_formed_squad()
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertEqual(
            self.ai.wave_history[-1]["launch_gate"]["decision"],
            "bootstrap_ready",
        )

    def test_squad_members_advance_together_with_reasonable_tolerance(self):
        members = self.add_formed_squad()
        self.ai.make_decision()
        for _ in range(56):
            for member in members:
                self.game.update_unit(member, .25)
            self.ai.make_decision()
        xs = [member.x for member in members]
        self.assertLess(max(xs) - min(xs), self.ai.WAVE_COHESION_TOLERANCE + 1)
        self.assertLess(max(xs), self.ai.rally_point[0] - 4)

    def test_casualties_trigger_recovery_and_cleanup_bookkeeping(self):
        members = self.add_formed_squad()
        self.ai.make_decision()
        for member in members[:6]:
            member.health = 0
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertNotIn(members[0].uid, self.ai.squad)
        self.assertNotIn(members[1].uid, self.ai.formation_roles)

    def test_recovering_squad_ignores_nearby_targets_and_keeps_retreating(self):
        retreating = self.game.add_unit("archer", "red", 40, 40)
        nearby_enemy = self.game.add_unit("swordsman", "green", 36, 40)
        self.ai.squad = {retreating.uid}
        self.ai.formation_roles = {retreating.uid: "archer_rank"}
        self.ai.wave_start_strength = 1
        self.ai.state = AIState.ATTACKING
        self.ai._begin_recovery()

        self.game.update_unit(retreating, .25)

        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertIsNone(retreating.target)
        self.assertEqual(retreating.target_pos, self.ai.rally_point)
        self.assertGreater(retreating.x, 40)
        self.assertEqual(nearby_enemy.health, nearby_enemy.max_health)

    def test_recovery_leaves_two_forward_shields_as_stationary_guards(self):
        shields = [
            self.game.add_unit("shield", "red", x, 40)
            for x in (45, 40, 35)
        ]
        archer = self.game.add_unit("archer", "red", 42, 42)
        members = [*shields, archer]
        self.ai.squad = {unit.uid for unit in members}
        self.ai.formation_roles = {
            unit.uid: self.ai.FORMATION_ROLE_BY_KIND[unit.kind]
            for unit in members
        }
        self.ai.wave_start_strength = len(members)
        self.ai.state = AIState.ATTACKING

        self.ai._begin_recovery()

        self.assertEqual(
            self.ai.recovery_guards,
            {shields[1].uid, shields[2].uid},
        )
        for shield in shields[1:]:
            self.assertEqual(shield.target_pos, (shield.x, shield.y))
        self.assertEqual(shields[0].target_pos, self.ai.rally_point)
        self.assertEqual(archer.target_pos, self.ai.rally_point)

    def test_recovery_uses_one_shield_or_none_when_that_is_all_it_has(self):
        for shield_count in (0, 1):
            with self.subTest(shield_count=shield_count):
                game = Game(enemy_rng=random.Random(7))
                game.units[:] = [unit for unit in game.units if unit.is_king_objective]
                ai = game.enemy_ai
                members = [game.add_unit("archer", "red", 40, 40)]
                members.extend(
                    game.add_unit("shield", "red", 39, 40)
                    for _ in range(shield_count)
                )
                ai.squad = {unit.uid for unit in members}
                ai.formation_roles = {
                    unit.uid: ai.FORMATION_ROLE_BY_KIND[unit.kind]
                    for unit in members
                }
                ai.wave_start_strength = len(members)
                ai.state = AIState.ATTACKING

                ai._begin_recovery()

                self.assertEqual(len(ai.recovery_guards), shield_count)
                self.assertEqual(members[0].target_pos, ai.rally_point)

    def test_successive_attack_waves_are_possible(self):
        first_wave = self.add_formed_squad()
        self.ai.make_decision()
        self.assertEqual(self.ai.wave_number, 1)
        for unit in first_wave[:6]:
            unit.health = 0
        self.ai.make_decision()
        self.ai.recovery_elapsed = self.ai.RECOVERY_DURATION
        self.ai.make_decision()
        for unit in list(self.game.units):
            if unit.is_enemy_ai_commandable:
                unit.health = 0
        self.ai.make_decision()
        second_wave = [
            self.game.add_unit(kind, "red", 170, 100 + index)
            for index, kind in enumerate(("archer",) * 12)
        ]
        self.ai.make_decision()
        for unit in second_wave:
            if unit.uid in self.ai.squad:
                unit.x, unit.y = self.ai._formation_destination(unit)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertEqual(self.ai.wave_number, 2)
        self.assertEqual(len(self.ai.wave_history), 2)


class EnemyDefenseTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.ai = self.game.enemy_ai
        self.ai.recruitment_timer = 999

    def add_red(self, count=4, start_x=None):
        start_x = (
            self.game.team_king("red").x - 7 if start_x is None else start_x
        )
        return [
            self.game.add_unit(
                "archer" if index == count - 1 else "swordsman",
                "red", start_x + index * .2,
                self.game.team_king("red").y - 2 + index,
            )
            for index in range(count)
        ]

    def add_threat(self, kind="swordsman", x=None, target_base=False):
        x = self.game.team_king("red").x - 13 if x is None else x
        unit = self.game.add_unit(kind, "green", x, self.game.team_king("red").y)
        if target_base:
            unit.target = self.game.team_king("red")
            unit.target_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        return unit

    def test_approaching_unit_enters_defending_but_distant_unit_is_ignored(self):
        self.add_red()
        distant = self.add_threat(x=self.game.team_king("red").x - 37)
        distant.target = self.game.team_king("red")
        distant.target_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        self.ai.make_decision()
        self.assertNotEqual(self.ai.state, AIState.DEFENDING)
        distant.x = self.game.team_king("red").x - 13
        distant.target_pos = (self.game.team_king("red").x, self.game.team_king("red").y)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.DEFENDING)

    def test_reserve_engages_before_attackers_are_recalled(self):
        reds = self.add_red(32)
        self.ai.make_decision()
        reserve = set(self.ai.reserve)
        attackers = set(self.ai.squad)
        self.assertEqual(len(reserve), self.ai.DEFENSIVE_RESERVE_SIZE)
        self.add_threat(kind="archer")
        self.ai.make_decision()
        self.assertTrue(reserve <= self.ai.defenders)
        self.assertTrue(attackers.isdisjoint(self.ai.defenders))
        self.assertTrue(all(
            unit.target_pos != (self.game.team_king("green").x, self.game.team_king("green").y)
            for unit in reds if unit.uid in reserve
        ))

    def test_attackers_recalled_only_for_dangerous_threat(self):
        self.add_red()
        self.ai.make_decision()
        for unit in self.ai._squad_units():
            unit.x = self.game.team_king("red").x - 37
        self.ai._launch_wave()
        attackers = set(self.ai.squad)
        self.add_threat(kind="archer")
        self.ai.make_decision()
        self.assertTrue(attackers.isdisjoint(self.ai.defenders))

        self.game.units = [unit for unit in self.game.units if unit.is_king_objective or unit.team == "red"]
        for offset in range(3):
            self.add_threat(
                x=self.game.team_king("red").x - 12 + offset, target_base=True
            )
        self.ai.make_decision()
        self.assertTrue(attackers & self.ai.defenders)

    def test_emergency_melee_recruitment_respects_essence_and_cost(self):
        self.game.add_unit(
            "archer", "red",
            self.game.team_king("red").x - 4, self.game.team_king("red").y,
        )
        for offset in range(2):
            self.add_threat(
                x=self.game.team_king("red").x - 3 + offset, target_base=True
            )
        self.game.enemy_essence = UNIT_COSTS["swordsman"]
        self.ai.make_decision()
        self.assertEqual(self.game.enemy_essence, 0)
        self.assertEqual(
            sum(unit.team == "red" and unit.kind == "swordsman"
                for unit in self.game.units), 1
        )

        game = Game(enemy_rng=random.Random(7))
        game.units[:] = [unit for unit in game.units if unit.is_king_objective]
        game.enemy_ai.recruitment_timer = 999
        game.add_unit(
            "archer", "red", game.team_king("red").x - 4, game.team_king("red").y
        )
        for offset in range(2):
            threat = game.add_unit(
                "swordsman", "green",
                game.team_king("red").x - 3 + offset, game.team_king("red").y,
            )
            threat.target = game.team_king("red")
        game.enemy_essence = UNIT_COSTS["swordsman"] - 1
        game.enemy_ai.make_decision()
        self.assertFalse(any(
            unit.team == "red" and unit.kind == "swordsman" for unit in game.units
        ))

    def test_defensive_target_priority_favors_immediate_base_danger(self):
        defender = self.game.add_unit(
            "archer", "red",
            self.game.team_king("red").x - 5, self.game.team_king("red").y,
        )
        near = self.add_threat(x=self.game.team_king("red").x - 3)
        attacker = self.add_threat(
            x=self.game.team_king("red").x - 8, target_base=True
        )
        self.ai.defenders.add(defender.uid)
        self.ai.transition_to(AIState.DEFENDING)
        self.assertIs(self.ai.choose_target(defender), attacker)
        self.assertIsNot(attacker, near)

    def test_defense_has_clear_cooldown_and_returns_to_strategy(self):
        self.add_red()
        threat = self.add_threat(x=self.game.team_king("red").x - 12)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.DEFENDING)
        threat.x = self.game.team_king("red").x - 47
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.DEFENDING)
        decisions = int(self.ai.DEFENSE_CLEAR_COOLDOWN / self.ai.decision_interval)
        for _ in range(decisions - 1):
            self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        self.assertTrue(self.ai.reserve)

    def test_boundary_hysteresis_prevents_rapid_state_switching(self):
        self.add_red()
        threat = self.add_threat(x=self.game.team_king("red").x - 13.5)
        self.ai.make_decision()
        for x in (
            self.game.team_king("red").x - 14.5,
            self.game.team_king("red").x - 13.5,
            self.game.team_king("red").x - 14.5,
            self.game.team_king("red").x - 13.5,
        ):
            threat.x = x
            self.ai.make_decision()
            self.assertEqual(self.ai.state, AIState.DEFENDING)
        self.assertEqual(
            sum(state == AIState.DEFENDING for _, state in self.ai.state_history), 1
        )

    def test_base_attack_interrupts_rally_attack_and_recovery(self):
        for starting_state in (
            AIState.RALLYING, AIState.ATTACKING, AIState.RECOVERING
        ):
            game = Game(enemy_rng=random.Random(7))
            game.units[:] = [unit for unit in game.units if unit.is_king_objective]
            ai = game.enemy_ai
            ai.recruitment_timer = 999
            for index in range(4):
                game.add_unit(
                    "swordsman", "red",
                    game.team_king("red").x - 7, game.team_king("red").y - 2 + index,
                )
            ai.transition_to(AIState.RALLYING)
            ai._assign_available_units()
            if starting_state == AIState.ATTACKING:
                ai._launch_wave()
            elif starting_state == AIState.RECOVERING:
                ai._launch_wave()
                ai._begin_recovery()
            threat = game.add_unit(
                "swordsman", "green",
                game.team_king("red").x - 2, game.team_king("red").y,
            )
            threat.target = game.team_king("red")
            ai.make_decision()
            self.assertEqual(ai.state, AIState.DEFENDING)
            self.assertEqual(ai.pre_defense_state, starting_state)


class EnemyTacticalPositioningTests(GameTestCase):
    def set_units(self, *units):
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.game.enemy_ai.recruitment_timer = 999
        return [self.game.add_unit(*unit) for unit in units]

    def test_archer_retreats_from_close_melee_unit(self):
        archer, sword = self.set_units(
            ("archer", "red", 20, 20),
            ("swordsman", "green", 22, 20),
        )
        self.game.update_unit(archer, .25)
        self.assertLess(archer.x, 20)
        self.assertGreater(dist((archer.x, archer.y), (sword.x, sword.y)), 2)

    def test_archer_holds_position_when_safely_within_attack_range(self):
        archer, sword = self.set_units(
            ("archer", "red", 20, 20),
            ("swordsman", "green", 24, 20),
        )
        before = (archer.x, archer.y)
        self.game.update_unit(archer, .25)
        self.assertEqual((archer.x, archer.y), before)
        self.assertEqual(sword.health, 50)

    def test_archer_resumes_attacks_after_repositioning(self):
        archer, sword = self.set_units(
            ("archer", "red", 20, 20),
            ("swordsman", "green", 22, 20),
        )
        self.game.update_unit(archer, .5)
        self.assertEqual(sword.health, sword.max_health)
        sword.x = archer.x + 4
        archer.attack_timer = 0
        self.game.update_unit(archer, .1)
        self.assertEqual(sword.health, 50)
        self.assertIsNone(archer.tactical_pos)

    def test_swordsman_moves_to_screen_nearby_archer(self):
        sword, archer, threat = self.set_units(
            ("swordsman", "red", 20, 22),
            ("archer", "red", 20, 20),
            ("swordsman", "green", 24, 20),
        )
        before = dist((sword.x, sword.y), (22, 20))
        self.game.update_unit(sword, .5)
        self.assertLess(dist((sword.x, sword.y), (22, 20)), before)
        self.assertGreater(sword.x, archer.x)

    def test_enemy_units_separate_when_overlapping(self):
        first, second = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "red", 20, 20),
        )
        self.game.update_unit(first, .25)
        self.game.update_unit(second, .25)
        self.assertGreater(dist((first.x, first.y), (second.x, second.y)), 0)

    def test_tiny_separation_adjustment_does_not_stall_strategic_movement(self):
        first, second = self.set_units(
            ("swordsman", "red", 20, 20),
            ("swordsman", "red", 20, 21.14),
        )
        first.target_pos = (10, 20)
        before = first.x
        self.game.update_unit(first, .05)
        self.assertLess(first.x, before)

    def test_attack_wave_progress_is_consistent_across_fixed_step_sizes(self):
        def progress(dt):
            game = Game(enemy_rng=random.Random(7))
            game.state = "playing"
            game.enemy_ai.recruitment_timer = 999
            for _ in range(round(20 / dt)):
                game.update(dt)
            return max(unit.x for unit in game.enemy_ai._squad_units())

        fine = progress(.05)
        coarse = progress(.1)
        self.assertLess(fine, 160)
        self.assertAlmostEqual(fine, coarse, delta=2.5)

    def test_tactical_movement_stays_within_map_boundaries(self):
        archer, threat = self.set_units(
            ("archer", "red", .5, .5),
            ("swordsman", "green", 1.5, .5),
        )
        for _ in range(20):
            self.game.update_unit(archer, .1)
        self.assertGreaterEqual(archer.x, .5)
        self.assertGreaterEqual(archer.y, .5)
        self.assertLessEqual(archer.x, WORLD_MAX)
        self.assertLessEqual(archer.y, WORLD_MAX)

    def test_archer_retreat_does_not_rapidly_oscillate(self):
        archer, threat = self.set_units(
            ("archer", "red", 20, 20),
            ("swordsman", "green", 22, 20),
        )
        positions = []
        for _ in range(12):
            self.game.update_unit(archer, .1)
            positions.append(archer.x)
        direction_changes = sum(
            (b - a) * (c - b) < -1e-9
            for a, b, c in zip(positions, positions[1:], positions[2:])
        )
        self.assertEqual(direction_changes, 0)

    def test_player_controlled_unit_behavior_is_unchanged(self):
        player, threat = self.set_units(
            ("archer", "green", 20, 20),
            ("swordsman", "red", 22, 20),
        )
        # Green archers use the original behavior: they attack, not retreat.
        self.game.visible.add((22, 20))
        before = (player.x, player.y)
        self.game.update_unit(player, .1)
        self.assertEqual((player.x, player.y), before)
        self.assertEqual(threat.health, 50)
        self.assertIsNone(player.tactical_pos)


class EnemySimulationHarnessTests(unittest.TestCase):
    def test_integration_review_covers_loss_gated_production_and_wave_cost(self):
        from simulate_enemy_ai import simulate_integration_review

        first = simulate_integration_review()
        second = simulate_integration_review()
        self.assertEqual(first, second)

        neutral = {kind: 1 / len(UNIT_KINDS) for kind in UNIT_KINDS}
        scenario_a = first["scenario_a_player_loses"]
        self.assertTrue(scenario_a["remained_neutral"])
        self.assertEqual(scenario_a["target_after_player_loss"], neutral)

        all_swords = {"swordsman": 1.0, "archer": 0.0, "shield": 0.0}
        scenario_b = first["scenario_b_player_wins"]
        self.assertEqual(scenario_b["target_after_ai_defeat"], all_swords)
        self.assertEqual(scenario_b["subsequent_spending_shares"], all_swords)

        scenario_c = first["scenario_c_weaker_retreat"]
        self.assertEqual(scenario_c["assessment"], "WEAKER")
        self.assertFalse(scenario_c["assessment_stale"])
        self.assertEqual(scenario_c["ai_state"], AIState.RECOVERING.name)
        self.assertEqual(scenario_c["casualties"], 0)
        self.assertEqual(scenario_c["target_before_rebuild"], all_swords)

        scenario_d = first["scenario_d_launch_gate"]
        self.assertLess(
            scenario_d["below_target_essence"],
            scenario_d["target_essence"],
        )
        self.assertFalse(scenario_d["launched_below_target"])
        self.assertGreaterEqual(
            scenario_d["launched_wave_essence"],
            scenario_d["target_essence"],
        )

    def test_headless_simulation_is_deterministic_and_reports_health_metrics(self):
        first = simulate(7, "idle", duration=240, dt=.05)
        second = simulate(7, "idle", duration=240, dt=.05)
        self.assertEqual(first, second)
        self.assertIsNotNone(first["first_attack"])
        self.assertLess(first["first_attack"], 240)
        self.assertEqual(first["invalid_target_frames"], 0)
        self.assertEqual(first["stale_ai_unit_ids"], 0)
        self.assertEqual(set(first["produced"]), set(UNIT_KINDS))
        self.assertEqual(set(first["living_red"]), set(UNIT_KINDS))
        self.assertTrue(all(
            set(wave["composition"]) == set(UNIT_KINDS)
            for wave in first["waves"]
        ))

    def test_smaller_map_alone_does_not_trigger_defense(self):
        game = Game(enemy_rng=random.Random(7))
        for _ in range(20):
            game.enemy_ai.make_decision()
        self.assertNotEqual(game.enemy_ai.state, AIState.DEFENDING)
        self.assertFalse(game.enemy_ai.defenders)

    def test_deterministic_assault_eventually_allows_cost_valid_wave(self):
        result = simulate(7, "player_assault", duration=240, dt=.05)
        self.assertGreaterEqual(result["wave_count"], 1)
        self.assertGreaterEqual(
            result["waves"][0]["squad_essence"],
            6000,
        )


if __name__ == "__main__":
    unittest.main()
