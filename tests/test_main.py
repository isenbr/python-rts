import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from main import AIState, Game, UNIT_COSTS, Unit, dist
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
                         (20, 2, 30, 1, 5))
        self.assertEqual(UNIT_COSTS, {"swordsman": 200, "archer": 500})
        before = len(self.game.units)
        self.assertTrue(self.game.recruit("swordsman"))
        self.assertEqual(self.game.essence, 200)
        self.assertEqual(len(self.game.units), before + 1)
        self.assertFalse(self.game.recruit("archer"))

    def test_enemy_essence_generation_and_spending(self):
        self.game.units.clear()
        self.game.enemy_ai.recruitment_timer = 0
        self.game.update(.25)
        self.assertEqual(self.game.enemy_essence, 305)
        self.assertEqual([(unit.team, unit.kind) for unit in self.game.units], [("red", "swordsman")])

    def test_attack_range_and_cooldown(self):
        self.game.units.clear()
        attacker = self.game.add_unit("archer", "green", 10, 10)
        target = self.game.add_unit("swordsman", "red", 15, 10)
        self.game.visible.add((15, 10))
        self.game.update_unit(attacker, 0)
        self.assertEqual(target.health, 70)
        self.assertEqual(attacker.attack_timer, 1)
        self.game.update_unit(attacker, .5)
        self.assertEqual(target.health, 70)
        self.game.update_unit(attacker, .5)
        self.assertEqual(target.health, 40)

    def test_death_and_target_cleanup(self):
        self.game.units.clear()
        attacker = self.game.add_unit("swordsman", "red", 20, 20)
        dead = self.game.add_unit("archer", "green", 21, 20)
        attacker.target = dead
        dead.health = 0
        self.game.enemy_ai.recruitment_timer = 999
        self.game.update(0)
        self.assertIsNone(attacker.target)
        self.assertNotIn(dead, self.game.units)

    def test_targets_killed_late_in_tick_are_cleaned_immediately(self):
        self.game.units.clear()
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
        self.game.units.clear()
        self.game.enemy_essence = 200
        self.assertTrue(self.game.recruit("swordsman", "red"))
        enemy = self.game.units[-1]
        self.assertIsNone(enemy.target_pos)
        self.game.enemy_ai.recruitment_timer = 999
        self.game.update(.25)
        self.assertEqual(self.game.enemy_ai.state, AIState.RALLYING)
        self.assertGreater(enemy.target_pos[0], self.game.player_base.x)
        self.assertAlmostEqual(enemy.target_pos[0], self.game.enemy_ai.rally_point[0])

    def test_player_targeting_is_restricted_by_fog(self):
        self.game.units.clear()
        player = self.game.add_unit("archer", "green", 10, 10)
        hidden = self.game.add_unit("swordsman", "red", 12, 10)
        self.assertIsNone(self.game.find_target(player))
        self.game.visible.add((12, 10))
        self.assertIs(self.game.find_target(player), hidden)
        enemy = self.game.add_unit("archer", "red", 11, 10)
        self.assertIs(self.game.find_target(enemy), player)

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
        self.game.enemy_base.health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "VICTORY")
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)
        )
        self.assertIsNone(self.game.winner)
        self.game.player_base.health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "DEFEAT")
        self.game.handle_game_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        )
        self.assertEqual(self.game.state, "menu")


class EnemyAITests(GameTestCase):
    def set_units(self, *units):
        self.game.units.clear()
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
            game.units.clear()
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
        sword.target = self.game.enemy_base
        self.assertIsNone(self.game.enemy_ai.choose_target(sword))

    def test_base_defense_threat_receives_increased_priority(self):
        defender, base_threat, other_threat = self.set_units(
            ("archer", "red", 172, 100),
            ("swordsman", "green", 170, 100),
            ("swordsman", "green", 169, 100),
        )
        # Equidistant threats differ only in whether they endanger the keep.
        self.game.enemy_base.x = 184
        base_threat.x = 175
        self.assertIs(self.game.enemy_ai.choose_target(defender), base_threat)


class EnemyProductionTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units.clear()
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
            self.game.add_unit(kind, "green", 169, 104 + index)
        self.ai._update_strategic_knowledge()

    def test_default_production_without_player_information_is_neutral_frontline(self):
        self.assertEqual(self.ai.known_player_composition(), {
            "swordsman": 0, "archer": 0
        })
        self.assertEqual(self.ai.choose_production(), "swordsman")

    def test_observed_armies_shift_weighted_counter_preference(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 4)
        self.assertEqual(self.ai.choose_production(), "archer")
        self.game.units[:] = [u for u in self.game.units if u.team == "red"]
        self.ai.player_knowledge.clear()
        self.observe_player(["archer"] * 4)
        self.assertEqual(self.ai.choose_production(), "swordsman")

    def test_minimum_frontline_overrides_swordsman_counter(self):
        self.game.add_unit("archer", "red", 170, 100)
        self.observe_player(["swordsman"] * 5)
        self.assertEqual(self.ai.choose_production(), "swordsman")

    def test_saves_for_archer_when_justified(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 4)
        self.game.enemy_essence = 300
        self.assertIsNone(self.ai.choose_production())

    def test_emergency_abandons_archer_savings(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 4)
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
        self.assertFalse(self.game.units)

    def test_production_has_defined_behavior_in_every_ai_state(self):
        self.add_red_frontline()
        results = {}
        for state in AIState:
            self.ai.state = state
            choice = self.ai.choose_production()
            self.assertIn(choice, ("swordsman", "archer"))
            results[state] = choice
        self.assertEqual(set(results), set(AIState))

    def test_choice_hysteresis_prevents_rapid_composition_oscillation(self):
        self.add_red_frontline()
        self.ai.last_production_choice = "swordsman"
        choices = [self.ai.choose_production() for _ in range(8)]
        self.assertEqual(choices, ["swordsman"] * 8)

    def test_stale_player_information_expires(self):
        self.add_red_frontline()
        self.observe_player(["swordsman"] * 3)
        self.assertEqual(self.ai.known_player_composition()["swordsman"], 3)
        self.game.units[:] = [u for u in self.game.units if u.team == "red"]
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
        self.game.units.clear()
        self.ai = self.game.enemy_ai
        self.ai.recruitment_timer = 999

    def add_formed_squad(self, kinds=("swordsman", "swordsman", "swordsman", "archer")):
        units = [
            self.game.add_unit(kind, "red", 170, 100 + index)
            for index, kind in enumerate(kinds)
        ]
        self.ai.make_decision()
        for unit in units:
            unit.x, unit.y = self.ai._formation_destination(unit)
        return units

    def test_formation_roles_put_swordsmen_ahead_of_archers(self):
        sword, archer = self.add_formed_squad(("swordsman", "archer"))
        self.assertEqual(self.ai.formation_roles[sword.uid], "frontline")
        self.assertEqual(self.ai.formation_roles[archer.uid], "rear")
        sword_destination = self.ai._formation_destination(sword)
        archer_destination = self.ai._formation_destination(archer)
        self.assertLess(sword_destination[0], archer_destination[0])

    def test_sufficiently_strong_formed_squad_launches(self):
        members = self.add_formed_squad()
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertEqual(self.ai.wave_start_strength, 4)
        self.assertTrue(all(unit.target_pos == (
            self.game.player_base.x, self.game.player_base.y
        ) for unit in members))

    def test_maximum_rally_time_prevents_permanent_waiting(self):
        member = self.game.add_unit("swordsman", "red", 170, 100)
        self.ai.make_decision()
        self.ai.rally_elapsed = self.ai.MAX_RALLY_WAIT - self.ai.decision_interval
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertIn(member.uid, self.ai.squad)

    def test_squad_members_advance_together_with_reasonable_tolerance(self):
        members = self.add_formed_squad()
        self.ai.make_decision()
        for _ in range(32):
            for member in members:
                self.game.update_unit(member, .25)
            self.ai.make_decision()
        xs = [member.x for member in members]
        self.assertLess(max(xs) - min(xs), self.ai.WAVE_COHESION_TOLERANCE + 1)
        self.assertLess(max(xs), self.ai.rally_point[0] - 4)

    def test_casualties_trigger_recovery_and_cleanup_bookkeeping(self):
        members = self.add_formed_squad()
        self.ai.make_decision()
        members[0].health = 0
        members[1].health = 0
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertNotIn(members[0].uid, self.ai.squad)
        self.assertNotIn(members[1].uid, self.ai.formation_roles)

    def test_successive_attack_waves_are_possible(self):
        first_wave = self.add_formed_squad()
        self.ai.make_decision()
        self.assertEqual(self.ai.wave_number, 1)
        for unit in first_wave[:2]:
            unit.health = 0
        self.ai.make_decision()
        self.ai.recovery_elapsed = self.ai.RECOVERY_DURATION
        self.ai.make_decision()
        for unit in list(self.game.units):
            if unit.team == "red":
                unit.health = 0
        self.ai.make_decision()
        second_wave = [
            self.game.add_unit(kind, "red", 170, 100 + index)
            for index, kind in enumerate(
                ("swordsman", "swordsman", "swordsman", "archer")
            )
        ]
        self.ai.make_decision()
        for unit in second_wave:
            unit.x, unit.y = self.ai._formation_destination(unit)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertEqual(self.ai.wave_number, 2)
        self.assertEqual(len(self.ai.wave_history), 2)


class EnemyDefenseTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.game.units.clear()
        self.ai = self.game.enemy_ai
        self.ai.recruitment_timer = 999

    def add_red(self, count=4, start_x=170):
        return [
            self.game.add_unit(
                "archer" if index == count - 1 else "swordsman",
                "red", start_x + index * .2, 98 + index,
            )
            for index in range(count)
        ]

    def add_threat(self, kind="swordsman", x=164, target_base=False):
        unit = self.game.add_unit(kind, "green", x, 100)
        if target_base:
            unit.target = self.game.enemy_base
            unit.target_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        return unit

    def test_approaching_unit_enters_defending_but_distant_unit_is_ignored(self):
        self.add_red()
        distant = self.add_threat(x=140)
        distant.target = self.game.enemy_base
        distant.target_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        self.ai.make_decision()
        self.assertNotEqual(self.ai.state, AIState.DEFENDING)
        distant.x = 164
        distant.target_pos = (self.game.enemy_base.x, self.game.enemy_base.y)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.DEFENDING)

    def test_reserve_engages_before_attackers_are_recalled(self):
        reds = self.add_red(6)
        self.ai.make_decision()
        reserve = set(self.ai.reserve)
        attackers = set(self.ai.squad)
        self.assertEqual(len(reserve), self.ai.DEFENSIVE_RESERVE_SIZE)
        self.add_threat(kind="archer", x=164)
        self.ai.make_decision()
        self.assertTrue(reserve <= self.ai.defenders)
        self.assertTrue(attackers.isdisjoint(self.ai.defenders))
        self.assertTrue(all(
            unit.target_pos != (self.game.player_base.x, self.game.player_base.y)
            for unit in reds if unit.uid in reserve
        ))

    def test_attackers_recalled_only_for_dangerous_threat(self):
        self.add_red()
        self.ai.make_decision()
        for unit in self.ai._squad_units():
            unit.x = 140
        self.ai._launch_wave()
        attackers = set(self.ai.squad)
        self.add_threat(kind="archer", x=164)
        self.ai.make_decision()
        self.assertTrue(attackers.isdisjoint(self.ai.defenders))

        self.game.units = [unit for unit in self.game.units if unit.team == "red"]
        for offset in range(3):
            self.add_threat(x=165 + offset, target_base=True)
        self.ai.make_decision()
        self.assertTrue(attackers & self.ai.defenders)

    def test_emergency_melee_recruitment_respects_essence_and_cost(self):
        self.game.add_unit("archer", "red", 173, 100)
        for offset in range(2):
            self.add_threat(x=174 + offset, target_base=True)
        self.game.enemy_essence = UNIT_COSTS["swordsman"]
        self.ai.make_decision()
        self.assertEqual(self.game.enemy_essence, 0)
        self.assertEqual(
            sum(unit.team == "red" and unit.kind == "swordsman"
                for unit in self.game.units), 1
        )

        game = Game(enemy_rng=random.Random(7))
        game.units.clear()
        game.enemy_ai.recruitment_timer = 999
        game.add_unit("archer", "red", 173, 100)
        for offset in range(2):
            threat = game.add_unit("swordsman", "green", 174 + offset, 100)
            threat.target = game.enemy_base
        game.enemy_essence = UNIT_COSTS["swordsman"] - 1
        game.enemy_ai.make_decision()
        self.assertFalse(any(
            unit.team == "red" and unit.kind == "swordsman" for unit in game.units
        ))

    def test_defensive_target_priority_favors_immediate_base_danger(self):
        defender = self.game.add_unit("archer", "red", 172, 100)
        near = self.add_threat(x=174)
        attacker = self.add_threat(x=169, target_base=True)
        self.ai.defenders.add(defender.uid)
        self.ai.transition_to(AIState.DEFENDING)
        self.assertIs(self.ai.choose_target(defender), attacker)
        self.assertIsNot(attacker, near)

    def test_defense_has_clear_cooldown_and_returns_to_strategy(self):
        self.add_red()
        threat = self.add_threat(x=165)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.DEFENDING)
        threat.x = 130
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.DEFENDING)
        decisions = int(self.ai.DEFENSE_CLEAR_COOLDOWN / self.ai.decision_interval)
        for _ in range(decisions - 1):
            self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RALLYING)
        self.assertTrue(self.ai.reserve)

    def test_boundary_hysteresis_prevents_rapid_state_switching(self):
        self.add_red()
        threat = self.add_threat(x=163.5)
        self.ai.make_decision()
        for x in (162.5, 163.5, 162.5, 163.5):
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
            game.units.clear()
            ai = game.enemy_ai
            ai.recruitment_timer = 999
            for index in range(4):
                game.add_unit("swordsman", "red", 170, 98 + index)
            ai.transition_to(AIState.RALLYING)
            ai._assign_available_units()
            if starting_state == AIState.ATTACKING:
                ai._launch_wave()
            elif starting_state == AIState.RECOVERING:
                ai._launch_wave()
                ai._begin_recovery()
            threat = game.add_unit("swordsman", "green", 175, 100)
            threat.target = game.enemy_base
            ai.make_decision()
            self.assertEqual(ai.state, AIState.DEFENDING)
            self.assertEqual(ai.pre_defense_state, starting_state)


class EnemyTacticalPositioningTests(GameTestCase):
    def set_units(self, *units):
        self.game.units.clear()
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
        self.assertEqual(sword.health, 70)

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
        self.assertEqual(sword.health, 70)
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
        self.assertAlmostEqual(fine, coarse, delta=1.0)

    def test_tactical_movement_stays_within_map_boundaries(self):
        archer, threat = self.set_units(
            ("archer", "red", .5, .5),
            ("swordsman", "green", 1.5, .5),
        )
        for _ in range(20):
            self.game.update_unit(archer, .1)
        self.assertGreaterEqual(archer.x, .5)
        self.assertGreaterEqual(archer.y, .5)
        self.assertLessEqual(archer.x, 199.5)
        self.assertLessEqual(archer.y, 199.5)

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
        self.assertEqual(threat.health, 70)
        self.assertIsNone(player.tactical_pos)


class EnemySimulationHarnessTests(unittest.TestCase):
    def test_headless_simulation_is_deterministic_and_reports_health_metrics(self):
        first = simulate(7, "idle", duration=30, dt=.05)
        second = simulate(7, "idle", duration=30, dt=.05)
        self.assertEqual(first, second)
        self.assertLess(first["first_attack"], 10)
        self.assertEqual(first["stalled_units"], 0)
        self.assertEqual(first["invalid_target_frames"], 0)
        self.assertEqual(first["stale_ai_unit_ids"], 0)


if __name__ == "__main__":
    unittest.main()
