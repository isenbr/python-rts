import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import Game, UNIT_COSTS, UNIT_KINDS


class EnemyAICharacterizationTests(unittest.TestCase):
    """Current behaviors that later AI balance changes are expected to replace."""

    def setUp(self):
        self.game = Game(enemy_rng=random.Random(101))
        self.game.units[:] = [
            unit for unit in self.game.units if unit.is_king_objective
        ]
        self.ai = self.game.enemy_ai
        self.ai._known_red_uids.clear()
        self.ai.recruitment_timer = 999

    def observe_player_army(self, kinds):
        red_king = self.game.team_king("red")
        self.game.add_unit("swordsman", "red", red_king.x - 2, red_king.y)
        for index, kind in enumerate(kinds):
            self.game.add_unit(
                kind,
                "green",
                red_king.x - 5,
                red_king.y + index,
            )
        self.ai._update_strategic_knowledge()

    def test_bootstrap_attack_waits_for_6000_essence(self):
        units = [
            self.game.add_unit("swordsman", "red", 40, 40 + index)
            for index in range(20)
        ]
        squad_essence = sum(UNIT_COSTS[unit.kind] for unit in units)

        self.ai._assign_available_units()

        self.assertLess(squad_essence, self.ai.TARGET_GROUP_ESSENCE)
        self.assertFalse(self.ai._launch_strength_gate())
        self.assertEqual(self.ai.last_launch_gate["decision"], "bootstrap_wait")
        self.assertEqual(self.ai.last_launch_gate["squad_essence"], squad_essence)

    def test_observing_player_army_does_not_change_production_target_shares(self):
        neutral = self.ai.production_target_shares()

        self.observe_player_army(("swordsman",))

        self.assertEqual(
            neutral, {"swordsman": .20, "archer": .50, "shield": .30}
        )
        self.assertEqual(self.ai.production_target_shares(), neutral)

    def test_observing_only_player_shields_keeps_neutral_target(self):
        self.observe_player_army(("shield", "shield"))

        self.assertEqual(self.ai.production_target_shares(), {
            "swordsman": .20, "archer": .50, "shield": .30,
        })

    def test_standard_targets_requested_invested_essence_shares(self):
        for kind in ("swordsman", "archer", "shield"):
            self.game.add_unit(kind, "red", 40, 40)
        invested = self.ai.production_essence_investment()
        total_invested = sum(invested.values())

        balance = self.ai._production_balance()

        self.assertEqual(
            invested,
            {kind: UNIT_COSTS[kind] for kind in UNIT_KINDS},
        )
        self.assertEqual(
            balance["target_shares"],
            {"swordsman": .20, "archer": .50, "shield": .30},
        )
        self.assertEqual(
            balance["target_essence"],
            {
                "swordsman": total_invested * .20,
                "archer": total_invested * .50,
                "shield": total_invested * .30,
            },
        )


if __name__ == "__main__":
    unittest.main()
