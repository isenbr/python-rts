import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    ARCHER_DAMAGE_VS_KING_MULTIPLIER,
    ARCHER_DAMAGE_VS_KNIGHT_MULTIPLIER,
    GUARD_LEASH_DISTANCE,
    KING_SLASH_LIFETIME,
    RECRUIT_FORWARD_OFFSET,
    Game,
    dist,
)


class KingGuardCombatTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(11))
        self.game.state = "playing"
        self.game.units.clear()

    def add_guard(self, team="green", x=20, y=20):
        guard = self.game.add_unit("knight", team, x, y)
        guard.home_position = (x, y)
        return guard

    def test_king_attacks_on_exact_cadence(self):
        king = self.game.add_unit("king", "green", 10, 10)
        king.home_position = (10, 10)
        enemy = self.game.add_unit("swordsman", "red", 11.5, 10)
        king.target_pos = (40, 40)
        king.tactical_pos = (30, 30)

        self.game.update_unit(king, 0)
        self.assertEqual((king.x, king.y), (10, 10))
        self.assertEqual(enemy.health, enemy.max_health - king.damage)
        self.assertEqual(king.attack_timer, king.cooldown)

        self.game.update_unit(king, .2)
        self.assertEqual(enemy.health, enemy.max_health - king.damage)
        self.game.update_unit(king, .2)
        self.assertEqual(enemy.health, enemy.max_health - 2 * king.damage)
        self.assertEqual((king.x, king.y), king.home_position)
        self.assertIsNone(king.target_pos)
        self.assertIsNone(king.tactical_pos)

    def test_king_uses_nearest_then_uid_tie_breaking(self):
        king = self.game.add_unit("king", "green", 10, 10)
        king.home_position = (10, 10)
        first = self.game.add_unit("knight", "red", 11, 10)
        second = self.game.add_unit("king", "red", 9, 10)
        farther = self.game.add_unit("swordsman", "red", 11.4, 10)

        self.game.update_unit(king, 0)
        self.assertIs(king.target, first)
        self.assertEqual(first.health, first.max_health - king.damage)
        self.assertEqual(second.health, second.max_health)
        self.assertEqual(farther.health, farther.max_health)

    def test_guard_acquires_nearest_target_within_home_defense_radius(self):
        guard = self.add_guard()
        farther = self.game.add_unit("swordsman", "red", 39, 20)
        nearest = self.game.add_unit("knight", "red", 35, 20)

        self.game.update_unit(guard, 0)
        self.assertIs(guard.target, nearest)
        self.assertEqual(guard.target_pos, (nearest.x, nearest.y))
        self.assertEqual(farther.health, farther.max_health)

    def test_guard_nearest_target_tie_breaks_by_uid(self):
        guard = self.add_guard()
        first = self.game.add_unit("king", "red", 21.5, 20)
        second = self.game.add_unit("knight", "red", 18.5, 20)

        self.game.update_unit(guard, 0)
        self.assertIs(guard.target, first)
        self.assertLess(first.uid, second.uid)

    def test_guard_pursues_inside_leash_and_clamps_boundary_pursuit(self):
        guard = self.add_guard()
        inside = self.game.add_unit("swordsman", "red", 22.5, 20)
        self.game.update_unit(guard, 1)
        self.assertEqual((guard.x, guard.y), (21, 20))
        self.assertLessEqual(
            dist(guard.home_position, (guard.x, guard.y)),
            GUARD_LEASH_DISTANCE,
        )

        inside.x = 20 + GUARD_LEASH_DISTANCE - .01
        for _ in range(40):
            self.game.update_unit(guard, .5)
            self.assertLessEqual(
                dist(guard.home_position, (guard.x, guard.y)),
                GUARD_LEASH_DISTANCE + 1e-9,
            )
        self.assertLessEqual(
            dist(guard.home_position, (guard.x, guard.y)),
            GUARD_LEASH_DISTANCE,
        )
        self.assertLess(inside.health, inside.max_health)

    def test_guard_drops_escaped_target_and_returns_exactly_home(self):
        guard = self.add_guard()
        target = self.game.add_unit("swordsman", "red", 22.5, 20)
        self.game.update_unit(guard, 1)
        target.x = 20 + GUARD_LEASH_DISTANCE + .01

        self.game.update_unit(guard, .5)
        self.assertIsNone(guard.target)
        self.assertLess(guard.x, 21)
        self.game.update_unit(guard, 1)
        self.assertEqual((guard.x, guard.y), guard.home_position)
        self.assertIsNone(guard.target_pos)

    def test_king_chases_within_radius_then_returns_home(self):
        king = self.game.add_unit("king", "green", 20, 20)
        king.home_position = (20, 20)
        target = self.game.add_unit("swordsman", "red", 35, 20)

        self.game.update_unit(king, 1)
        self.assertEqual((king.x, king.y), (21, 20))
        self.assertIs(king.target, target)

        target.x = 20 + GUARD_LEASH_DISTANCE + .01
        self.game.update_unit(king, 1)
        self.assertIsNone(king.target)
        self.assertLess(king.x, 21)
        self.game.update_unit(king, 1)
        self.assertEqual((king.x, king.y), king.home_position)
        self.assertIsNone(king.target_pos)

    def test_arrows_are_resisted_by_kings_and_knights_only(self):
        archer = self.game.add_unit("archer", "red", 10, 10)
        king = self.game.add_unit("king", "green", 11, 10)
        knight = self.game.add_unit("knight", "green", 12, 10)

        self.game.attack(archer, king)
        archer.attack_timer = 0
        self.game.attack(archer, knight)

        self.assertEqual(
            king.health,
            king.max_health - archer.damage * ARCHER_DAMAGE_VS_KING_MULTIPLIER,
        )
        self.assertEqual(
            knight.health,
            knight.max_health
            - archer.damage * ARCHER_DAMAGE_VS_KNIGHT_MULTIPLIER,
        )

    def test_guard_targets_another_enemy_immediately_after_a_kill(self):
        guard = self.add_guard()
        first = self.game.add_unit("swordsman", "red", 22.5, 20)
        self.game.update_unit(guard, 1)
        first.health = 0
        second = self.game.add_unit("king", "red", 24, 20)

        self.game.update_unit(guard, .5)
        self.assertIs(guard.target, second)
        self.assertEqual(guard.target_pos, (second.x, second.y))
        self.assertGreaterEqual(guard.x, 21)

    def test_guard_retargets_if_an_enemy_appears_while_returning_home(self):
        guard = self.add_guard()
        escaped = self.game.add_unit("swordsman", "red", 22.5, 20)
        self.game.update_unit(guard, 1)
        escaped.x = 20 + GUARD_LEASH_DISTANCE + .01

        self.game.update_unit(guard, .25)
        self.assertIsNone(guard.target)
        returning_x = guard.x
        self.assertLess(returning_x, 21)

        replacement = self.game.add_unit("archer", "red", 23, 20)
        self.game.update_unit(guard, .25)

        self.assertIs(guard.target, replacement)
        self.assertEqual(guard.target_pos, (replacement.x, replacement.y))
        self.assertGreater(guard.x, returning_x)

    def test_guard_ignores_player_orders_and_enemy_ai_destinations(self):
        green = self.add_guard("green", 20, 20)
        red = self.add_guard("red", 50, 20)
        green.selected = red.selected = True
        green.target_pos = red.target_pos = (80, 80)
        green.tactical_pos = red.tactical_pos = (70, 70)
        self.game.issue_order((60, 60))

        self.game.update_unit(green, 1)
        self.game.update_unit(red, 1)
        self.assertEqual((green.x, green.y), green.home_position)
        self.assertEqual((red.x, red.y), red.home_position)
        self.assertIsNone(green.tactical_pos)
        self.assertIsNone(red.tactical_pos)
        self.assertIsNone(self.game.enemy_ai.tactical_destination(red, 1))

    def test_normal_units_use_declared_range_against_kings_and_guards(self):
        attacker = self.game.add_unit("swordsman", "red", 10, 10)
        king = self.game.add_unit("king", "green", 12, 10)
        guard = self.add_guard("green", 14, 10)
        attacker.target = king

        self.game.update_unit(attacker, 0)
        self.assertEqual(king.health, king.max_health)
        self.assertEqual(attacker.target_pos, (king.x, king.y))

        attacker.x = king.x - attacker.attack_range
        self.game.update_unit(attacker, 0)
        self.assertEqual(king.health, king.max_health - attacker.damage)
        attacker.attack_timer = 0
        attacker.target = guard
        attacker.x = guard.x - attacker.attack_range
        self.game.update_unit(attacker, 0)
        self.assertEqual(guard.health, guard.max_health - attacker.damage)

    def test_deterministic_end_to_end_guard_and_objective_lifecycle(self):
        """Cover the complete special-unit flow without timing or randomness."""
        self.game = Game(enemy_rng=random.Random(73), ai_decision_interval=999)
        self.game.state = "playing"

        for team in ("green", "red"):
            self.assertEqual(
                sum(unit.team == team and unit.kind == "king"
                    for unit in self.game.units),
                1,
            )
            self.assertEqual(
                sum(unit.team == team and unit.kind == "knight"
                    for unit in self.game.units),
                2,
            )

        self.game.essence = self.game.enemy_essence = 10_000
        for team, direction in (("green", 1), ("red", -1)):
            king = self.game.team_king(team)
            self.assertTrue(self.game.recruit("swordsman", team))
            recruit = self.game.units[-1]
            self.assertEqual(
                recruit.x,
                king.x + direction * RECRUIT_FORWARD_OFFSET,
            )

        guard = next(
            unit for unit in self.game.units
            if unit.team == "green" and unit.kind == "knight"
        )
        post = guard.home_position
        intruder = self.game.add_unit(
            "swordsman", "red", guard.x + 2.5, guard.y
        )
        self.game.update_unit(guard, 1)
        self.assertIs(guard.target, intruder)
        self.assertNotEqual((guard.x, guard.y), post)
        intruder.health = 0
        self.game.update_unit(guard, 1)
        self.assertEqual((guard.x, guard.y), post)
        self.assertIsNone(guard.target)
        self.assertIsNone(guard.target_pos)

        king = self.game.team_king("green")
        attacker = self.game.add_unit(
            "swordsman", "red", king.x + king.attack_range, king.y
        )
        self.game.update_unit(king, 0)
        self.assertEqual(attacker.health, attacker.max_health - king.damage)
        self.assertEqual(len(self.game.king_slashes), 1)
        self.assertEqual(self.game.particles, [])
        self.game.update(KING_SLASH_LIFETIME)
        self.assertEqual(self.game.king_slashes, [])

        self.game.team_king("red").health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "VICTORY")

        self.game.reset()
        self.game.state = "playing"
        self.game.team_king("green").health = 0
        self.game.update(0)
        self.assertEqual(self.game.winner, "DEFEAT")


if __name__ == "__main__":
    unittest.main()
