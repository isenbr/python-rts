import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import CombatAdvantage, Game


class CombatStrengthAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(7))
        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.ai = self.game.enemy_ai
        self.ai._known_red_uids.clear()
        self.ai.recruitment_timer = 999

    def add_group(self, kinds, health_fraction=1.0, x=40):
        group = []
        for index, kind in enumerate(kinds):
            unit = self.game.add_unit(kind, "red", x, 40 + index)
            unit.health *= health_fraction
            group.append(unit)
        return group

    def observe(self, kinds, health_fraction=1.0, x=44):
        units = []
        for index, kind in enumerate(kinds):
            unit = self.game.add_unit(kind, "green", x, 40 + index)
            unit.health *= health_fraction
            units.append(unit)
        self.ai._update_strategic_knowledge()
        return units

    def assess(self, group, opponents):
        return self.ai.assess_combat_group(
            group, [unit.uid for unit in opponents]
        )

    def test_clearly_superior_enemy_ai_group(self):
        group = self.add_group(["swordsman"] * 4)
        opponents = self.observe(["swordsman"])
        result = self.assess(group, opponents)
        self.assertEqual(result.classification, CombatAdvantage.STRONGER)
        self.assertGreaterEqual(result.advantage_ratio, 1.25)

    def test_clearly_inferior_enemy_ai_group(self):
        group = self.add_group(["swordsman"])
        opponents = self.observe(["swordsman"] * 4)
        result = self.assess(group, opponents)
        self.assertEqual(result.classification, CombatAdvantage.WEAKER)
        self.assertLessEqual(result.advantage_ratio, .8)

    def test_evenly_matched_groups_are_uncertain(self):
        group = self.add_group(["swordsman", "shield"])
        opponents = self.observe(["swordsman", "shield"])
        result = self.assess(group, opponents)
        self.assertEqual(result.classification, CombatAdvantage.UNCERTAIN)
        self.assertAlmostEqual(result.advantage_ratio, 1.0)

    def test_damage_changes_effective_strength(self):
        group = self.add_group(["swordsman"] * 2, health_fraction=.25)
        opponents = self.observe(["swordsman"] * 2)
        result = self.assess(group, opponents)
        self.assertEqual(result.classification, CombatAdvantage.WEAKER)
        self.assertAlmostEqual(result.advantage_ratio, .25)

    def test_existing_unit_type_matchups_affect_result(self):
        swords = self.add_group(["swordsman"], x=30)
        archers = self.observe(["archer"], x=34)
        sword_result = self.assess(swords, archers)

        self.game.units[:] = [unit for unit in self.game.units if unit.is_king_objective]
        self.ai.combat_observations.clear()
        shields = self.add_group(["shield"], x=30)
        archers = self.observe(["archer"], x=34)
        shield_result = self.assess(shields, archers)
        self.assertGreater(
            shield_result.advantage_ratio, sword_result.advantage_ratio
        )

    def test_newly_observed_reinforcements_on_either_side(self):
        group = self.add_group(["swordsman"])
        opponents = self.observe(["swordsman"])
        baseline = self.assess(group, opponents)

        own_reinforcement = self.game.add_unit("swordsman", "red", 41, 41)
        with_own = self.assess(group, opponents)
        self.assertGreater(with_own.advantage_ratio, baseline.advantage_ratio)

        own_reinforcement.x = 10
        opponent_reinforcement = self.observe(["swordsman"], x=45)[0]
        with_opponent = self.assess(group, opponents)
        self.assertIn(opponent_reinforcement.uid, with_opponent.opponent_uids)
        self.assertLess(with_opponent.advantage_ratio, baseline.advantage_ratio)

    def test_lost_vision_becomes_stale_and_uncertain(self):
        group = self.add_group(["swordsman"] * 4)
        opponents = self.observe(["swordsman"])
        self.assertEqual(
            self.assess(group, opponents).classification,
            CombatAdvantage.STRONGER,
        )
        opponents[0].x = 100
        self.ai._update_strategic_knowledge()
        self.ai.elapsed += self.ai.combat_evaluator.STALE_AFTER + .01
        result = self.assess(group, opponents)
        self.assertTrue(result.stale)
        self.assertEqual(result.classification, CombatAdvantage.UNCERTAIN)

    def test_unchanged_information_is_cached_then_periodically_refreshed(self):
        group = self.add_group(["swordsman"])
        opponents = self.observe(["swordsman"])
        first = self.assess(group, opponents)
        second = self.assess(group, opponents)
        self.assertIs(first, second)
        self.ai.elapsed += self.ai.combat_evaluator.PERIODIC_REFRESH
        third = self.assess(group, opponents)
        self.assertIsNot(first, third)
        self.assertEqual(first.advantage_ratio, third.advantage_ratio)

    def test_hidden_units_never_enter_the_assessment(self):
        group = self.add_group(["swordsman"] * 2)
        observed = self.observe(["swordsman"])
        hidden = self.game.add_unit("archer", "green", 100, 100)
        result = self.assess(group, [*observed, hidden])
        self.assertIn(observed[0].uid, result.opponent_uids)
        self.assertNotIn(hidden.uid, result.opponent_uids)


if __name__ == "__main__":
    unittest.main()
