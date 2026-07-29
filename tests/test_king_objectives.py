import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import AIState, Game, UNIT_KINDS, dist


class KingObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(41), ai_decision_interval=999)
        self.game.state = "playing"

    def test_each_king_death_sets_the_corresponding_result_and_removes_it(self):
        for team, result in (("red", "VICTORY"), ("green", "DEFEAT")):
            with self.subTest(team=team):
                self.game.reset()
                self.game.state = "playing"
                king = self.game.team_king(team)
                king.health = 0
                self.game.update(0)
                self.assertEqual(self.game.winner, result)
                self.assertNotIn(king, self.game.units)
                self.assertIsNone(self.game.team_king(team))
                self.game.draw_hud()
                self.assertIn("Verdant King", self.game.hud_text["king"])

    def test_simultaneous_king_deaths_are_a_defeat(self):
        """Mutual destruction is deterministic: preserving your king is required."""
        self.game.team_king("green").health = 0
        self.game.team_king("red").health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "DEFEAT")

    def test_dead_objectives_and_guards_clear_stale_orders_before_later_updates(self):
        red_king = self.game.team_king("red")
        guard = next(
            unit for unit in self.game.units
            if unit.team == "red" and unit.is_autonomous_guard
        )
        attacker = self.game.add_unit(
            "swordsman", "green",
            red_king.x - attacker_range("swordsman"), red_king.y,
        )
        follower = self.game.add_unit("archer", "green", red_king.x - 4, red_king.y)
        follower.target = red_king
        follower.target_pos = (red_king.x, red_king.y)
        red_king.health = attacker.damage
        attacker.target = red_king
        guard.health = 0
        self.game.update(0)
        self.assertNotIn(red_king, self.game.units)
        self.assertNotIn(guard, self.game.units)
        self.assertIsNone(follower.target)
        self.assertIsNone(follower.target_pos)
        self.game.update(1)
        self.assertEqual(self.game.winner, "VICTORY")

    def test_ai_reachability_rally_and_defense_are_king_anchored(self):
        ai = self.game.enemy_ai
        red = self.game.team_king("red")
        green = self.game.team_king("green")
        self.assertTrue(ai._attack_objective_is_reachable())
        self.assertLess(dist(ai.rally_point, (red.x, red.y)), dist(ai.rally_point, (green.x, green.y)))
        threat = self.game.add_unit("swordsman", "green", red.x - 2, red.y)
        threat.target = red
        self.assertIn(threat, [unit for unit, _ in ai._player_threats()])
        green.x = float("nan")
        self.assertFalse(ai._attack_objective_is_reachable())

    def test_king_threat_gets_defense_priority(self):
        ai = self.game.enemy_ai
        defender = self.game.add_unit("swordsman", "red", 90, 60)
        king = self.game.team_king("red")
        urgent = self.game.add_unit("swordsman", "green", 89, 59)
        ordinary = self.game.add_unit("swordsman", "green", 89, 61)
        urgent.target = king
        self.assertGreater(
            ai.target_score(defender, urgent),
            ai.target_score(defender, ordinary),
        )

    def test_fog_and_composition_never_reveal_or_count_special_units(self):
        ai = self.game.enemy_ai
        red_king = self.game.team_king("red")
        red_king.health = 1
        self.game.update_visibility()
        self.game.draw_hud()
        self.assertNotIn("CRIMSON", " ".join(self.game.hud_text.values()))
        ai._update_strategic_knowledge()
        self.assertTrue(all(kind in UNIT_KINDS for kind, _ in ai.player_knowledge.values()))

        before_scores = ai.production_scores().copy()
        self.game.add_unit("king", "green", red_king.x - 2, red_king.y)
        green_knight = self.game.add_unit(
            "knight", "green", red_king.x - 3, red_king.y
        )
        ai._update_strategic_knowledge()
        self.assertEqual(ai.last_seen_player_composition()[0], {
            kind: 0 for kind in UNIT_KINDS
        })
        self.assertEqual(ai.production_scores(), before_scores)

        soldier = self.game.add_unit("swordsman", "red", 100, 60)
        red_knight = self.game.add_unit("knight", "red", 101, 60)
        ai.squad = {soldier.uid, red_king.uid, red_knight.uid, green_knight.uid}
        ai.state = AIState.RALLYING
        ai._launch_wave()
        self.assertEqual(ai.wave_history[-1]["composition"], {
            "swordsman": 1, "archer": 0, "shield": 0
        })


def attacker_range(kind):
    from main import UNIT_STATS
    return UNIT_STATS[kind]["attack_range"]


if __name__ == "__main__":
    unittest.main()
