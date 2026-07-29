import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import AIState, Game
from simulate_enemy_ai import simulate_integrated_decision_scenario


class CombatStateTransitionTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(41))
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.ai = self.game.enemy_ai
        self.ai._known_red_uids.clear()
        self.ai.recruitment_timer = 999

    def unit_group(self, team, count, x, health=1.0):
        units = [
            self.game.add_unit("swordsman", team, x, 40 + index * .2)
            for index in range(count)
        ]
        for unit in units:
            unit.health *= health
        return units

    def attack(self, red_count, green_count):
        red = self.unit_group("red", red_count, 40)
        green = self.unit_group("green", green_count, 44)
        self.ai.squad = {unit.uid for unit in red}
        self.ai.formation_roles = {
            unit.uid: self.ai.FORMATION_ROLE_BY_KIND[unit.kind]
            for unit in red
        }
        self.ai.wave_start_strength = len(red)
        self.ai.state = AIState.ATTACKING
        self.ai._update_strategic_knowledge()
        return red, green

    def decide_after_interval(self):
        self.ai.elapsed += self.ai.COMBAT_DECISION_INTERVAL
        self.ai.make_decision()

    def test_weaker_group_retreats(self):
        self.attack(1, 4)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_stronger_group_remains_engaged(self):
        self.attack(4, 1)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_even_match_holds_current_state(self):
        self.attack(2, 2)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_retreating_group_receives_reinforcements_and_reengages(self):
        self.attack(1, 4)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.unit_group("red", 10, 41)
        self.decide_after_interval()
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_new_opponent_reinforcements_force_retreat(self):
        self.attack(4, 1)
        self.ai.make_decision()
        self.unit_group("green", 10, 44)
        self.ai._update_strategic_knowledge()
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_casualties_can_reverse_decisions_in_either_direction(self):
        red, green = self.attack(5, 4)
        self.ai.make_decision()
        red[0].health = 0
        red[1].health = 0
        self.decide_after_interval()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

        green[0].health = 0
        green[1].health = 0
        green[2].health = 0
        self.ai._update_strategic_knowledge()
        self.decide_after_interval()
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_lost_vision_and_stale_intelligence_retreats_conservatively(self):
        _, green = self.attack(4, 1)
        self.ai.make_decision()
        green[0].x = 100
        self.ai._update_strategic_knowledge()
        self.ai.elapsed += self.ai.combat_evaluator.STALE_AFTER + .01
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertTrue(next(iter(self.ai.latest_combat_assessments.values())).stale)

    def test_dead_player_unit_is_removed_from_combat_memory_immediately(self):
        red, green = self.attack(1, 1)
        target = green[0]
        self.assertIn(target.uid, self.ai.combat_observations)
        self.ai.combat_opponent_uids.add(target.uid)
        target.health = 0
        self.game.state = "playing"

        self.game.update(0)

        self.assertNotIn(target, self.game.units)
        self.assertNotIn(target.uid, self.ai.player_knowledge)
        self.assertNotIn(target.uid, self.ai.combat_observations)
        self.assertNotIn(target.uid, self.ai._currently_observed_player_uids)
        self.assertNotIn(target.uid, self.ai.combat_opponent_uids)
        self.assertEqual(len(red), 1)

    def test_hysteresis_prevents_oscillation_near_threshold(self):
        red, green = self.attack(4, 5)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        green[0].health = 0
        self.ai._update_strategic_knowledge()
        self.decide_after_interval()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_periodic_reassessment_without_observation_event(self):
        self.attack(4, 1)
        self.ai.make_decision()
        first = self.ai.latest_combat_assessments[tuple(sorted(self.ai.squad))]
        self.decide_after_interval()
        second = self.ai.latest_combat_assessments[tuple(sorted(self.ai.squad))]
        self.assertIsNot(first, second)
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_high_casualties_continue_when_freshly_and_clearly_stronger(self):
        red, _ = self.attack(6, 1)
        for unit in red[:3]:
            unit.health = 0
        self.ai.make_decision()
        assessment = self.ai.latest_combat_assessments[tuple(sorted(self.ai.squad))]
        self.assertGreater(
            assessment.advantage_ratio, self.ai.CASUALTY_ADVANTAGE_MARGIN
        )
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.ai.elapsed += self.ai.decision_interval
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)

    def test_high_casualties_retreat_when_the_losses_make_group_weaker(self):
        red, _ = self.attack(6, 4)
        for unit in red[:3]:
            unit.health = 0
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_nearby_attackers_finish_low_health_base_despite_casualties(self):
        red, _ = self.attack(4, 1)
        for unit in red:
            unit.x = self.game.team_king("green").x + unit.attack_range
            unit.y = self.game.team_king("green").y
        red[0].health = 0
        red[1].health = 0
        self.game.team_king("green").health = 20
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.assertIsNotNone(red[2].target_pos)

    def test_finish_override_yields_to_overwhelming_live_defenders(self):
        red, green = self.attack(4, 8)
        for unit in red:
            unit.x = self.game.team_king("green").x + 3
            unit.y = self.game.team_king("green").y
        for index, unit in enumerate(green):
            unit.x = self.game.team_king("green").x + 4
            unit.y = self.game.team_king("green").y + index * .1
        self.game.team_king("green").health = 20
        self.ai._update_strategic_knowledge()
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_later_reassessment_reverses_casualty_override(self):
        red, _ = self.attack(6, 1)
        for unit in red[:3]:
            unit.health = 0
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.ATTACKING)
        self.unit_group("green", 5, 44)
        self.ai._update_strategic_knowledge()
        self.decide_after_interval()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_casualty_override_rejects_uncertain_or_stale_intelligence(self):
        for mode in ("uncertain", "stale"):
            with self.subTest(mode=mode):
                self.setUp()
                red, green = self.attack(6, 1)
                for unit in red[:3]:
                    unit.health = 0
                if mode == "uncertain":
                    green[0].health = 2.4 * green[0].max_health
                    self.ai._update_strategic_knowledge()
                else:
                    green[0].x = 100
                    self.ai._update_strategic_knowledge()
                    self.ai.elapsed += self.ai.combat_evaluator.STALE_AFTER + .01
                self.ai.make_decision()
                self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_no_viable_combat_units_is_hard_safety(self):
        red, _ = self.attack(4, 1)
        for unit in red:
            unit.health = 0
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_no_valid_or_reachable_target_is_hard_safety(self):
        red, _ = self.attack(6, 1)
        for unit in red[:3]:
            unit.health = 0
        self.game.team_king("green").x = float("nan")
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_hard_safety_precedes_strong_casualty_override(self):
        red, _ = self.attack(6, 1)
        for unit in red[:3]:
            unit.health = 0
        self.ai._attack_objective_is_reachable = lambda: False
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_casualty_override_does_not_affect_unrelated_retreat_reason(self):
        self.attack(1, 4)
        self.ai.wave_start_strength = 1
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)

    def test_integrated_production_retreat_reengage_and_casualty_scenario(self):
        first = simulate_integrated_decision_scenario(73)
        second = simulate_integrated_decision_scenario(73)
        self.assertEqual(first, second)
        self.assertEqual(first["production"]["archer_threat_choice"], "shield")
        self.assertGreater(first["production"]["shield_score_shift"], 0)
        self.assertLess(first["production"]["swordsman_score_shift"], 0)
        self.assertEqual(
            [
                (stage["stage"], stage["state"], stage["classification"])
                for stage in first["combat"]
            ],
            [
                ("initial_weaker", "RECOVERING", "WEAKER"),
                ("reinforced_reengage", "ATTACKING", "STRONGER"),
                ("casualty_override", "ATTACKING", "STRONGER"),
                ("final_weaker_retreat", "RECOVERING", "WEAKER"),
            ],
        )
        self.assertGreater(
            first["combat"][2]["ratio"],
            self.ai.CASUALTY_ADVANTAGE_MARGIN,
        )


if __name__ == "__main__":
    unittest.main()
