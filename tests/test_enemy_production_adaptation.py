import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import AIState, CombatAssessment, CombatAdvantage, Game, UNIT_COSTS


NEUTRAL = {"swordsman": 1 / 3, "archer": 1 / 3, "shield": 1 / 3}


class EnemyProductionAdaptationTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(303))
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        self.ai = self.game.enemy_ai
        self.ai._known_red_uids.clear()
        self.ai.recruitment_timer = 999

    def encounter(self, player_kinds, red_kinds=("swordsman",)):
        reds = [
            self.game.add_unit(kind, "red", 40, 40 + index * .2)
            for index, kind in enumerate(red_kinds)
        ]
        players = [
            self.game.add_unit(kind, "green", 44, 40 + index * .2)
            for index, kind in enumerate(player_kinds)
        ]
        self.ai.squad = {unit.uid for unit in reds}
        self.ai.formation_roles = {
            unit.uid: self.ai.FORMATION_ROLE_BY_KIND[unit.kind]
            for unit in reds
        }
        self.ai.wave_start_strength = len(reds)
        self.ai.state = AIState.ATTACKING
        self.ai._update_strategic_knowledge()
        self.ai.combat_opponent_uids = {unit.uid for unit in players}
        return reds, players

    def test_shield_sighting_and_player_loss_leave_neutral_target(self):
        _, players = self.encounter(("shield",))
        self.assertEqual(self.ai.production_target_shares(), NEUTRAL)
        players[0].health = 0
        self.ai._update_strategic_knowledge()
        self.ai._begin_recovery()
        self.assertEqual(self.ai.production_target_shares(), NEUTRAL)

    def test_shield_army_defeating_wave_teaches_all_swordsmen(self):
        reds, _ = self.encounter(("shield",), ("swordsman", "swordsman"))
        reds[0].health = 0
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": 1.0, "archer": 0.0, "shield": 0.0,
        })

    def test_fresh_weaker_retreat_without_casualties_teaches_counter(self):
        self.encounter(("shield",) * 8)
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": 1.0, "archer": 0.0, "shield": 0.0,
        })

    def test_unequal_counts_but_equal_costs_produce_half_counters(self):
        # Three 500-cost archers and five 300-cost shields each invest 1500.
        self.assertTrue(self.ai._learn_victorious_player_composition({
            "swordsman": 0,
            "archer": 3 * UNIT_COSTS["archer"],
            "shield": 5 * UNIT_COSTS["shield"],
        }))
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": .5, "archer": 0.0, "shield": .5,
        })

    def test_stale_or_missing_assessment_cannot_teach(self):
        _, players = self.encounter(("shield",))
        stale = CombatAssessment(
            tuple(self.ai.squad),
            (players[0].uid,),
            1,
            10,
            .1,
            CombatAdvantage.WEAKER,
            self.ai.elapsed,
            self.ai.combat_observation_revision,
            self.ai.elapsed - 20,
            True,
        )
        self.ai._begin_recovery(
            self.ai._fresh_victorious_player_composition(stale)
        )
        self.assertEqual(self.ai.production_target_shares(), NEUTRAL)

    def test_noncombat_hard_safety_recovery_cannot_teach(self):
        self.encounter(("shield",))
        self.game.team_king("green").x = float("inf")
        self.ai.make_decision()
        self.assertEqual(self.ai.state, AIState.RECOVERING)
        self.assertEqual(self.ai.production_target_shares(), NEUTRAL)

    def test_sighting_preserves_learning_until_later_confirmed_defeat(self):
        self.ai._learn_victorious_player_composition({
            "swordsman": 0,
            "archer": 0,
            "shield": 3 * UNIT_COSTS["shield"],
        })
        first = self.ai.production_target_shares()
        self.encounter(("archer",))
        self.assertEqual(self.ai.production_target_shares(), first)
        self.ai._begin_recovery({
            "swordsman": 0,
            "archer": 2 * UNIT_COSTS["archer"],
            "shield": 0,
        })
        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": 0.0, "archer": 0.0, "shield": 1.0,
        })

    def test_empty_invalid_snapshot_does_not_erase_learning(self):
        self.ai._learn_victorious_player_composition({
            "swordsman": 0,
            "archer": 0,
            "shield": UNIT_COSTS["shield"],
        })
        learned = self.ai.production_target_shares()
        self.assertFalse(self.ai._learn_victorious_player_composition({}))
        self.assertFalse(self.ai._learn_victorious_player_composition({
            "swordsman": 0, "archer": 0, "shield": 0,
        }))
        self.assertEqual(self.ai.production_target_shares(), learned)

    def test_production_history_changes_only_after_confirmed_loss(self):
        self.game.enemy_essence = 10_000
        self.ai.recruitment_timer = 0
        self.ai._run_production(0)
        self.encounter(("shield",))
        self.ai.recruitment_timer = 0
        self.ai._run_production(0)
        self.ai._begin_recovery({
            "swordsman": 0,
            "archer": 0,
            "shield": UNIT_COSTS["shield"],
        })
        self.ai.recruitment_timer = 0
        self.ai._run_production(0)
        self.assertEqual(self.ai.production_history[0]["target_shares"], NEUTRAL)
        self.assertEqual(self.ai.production_history[1]["target_shares"], NEUTRAL)
        self.assertEqual(self.ai.production_history[2]["target_shares"], {
            "swordsman": 1.0, "archer": 0.0, "shield": 0.0,
        })


if __name__ == "__main__":
    unittest.main()
