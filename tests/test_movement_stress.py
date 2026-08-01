import math
import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    UNIT_SEPARATION_RADIUS,
    UNIT_SOFT_OVERLAP,
    WORLD_MAX,
    WORLD_MIN,
    Game,
    TerrainCell,
    dist,
)


class MovementStressTests(unittest.TestCase):
    DT = .05

    def game(self):
        game = Game(enemy_rng=random.Random(73))
        game.state = "playing"
        game.enemy_ai.recruitment_timer = 999
        game.units.clear()
        game.terrain = {
            position: TerrainCell("plains", 0)
            for position in game.terrain
        }
        return game

    def run_fixed(self, game, seconds, before_step=None):
        starts = {unit.uid: (unit.x, unit.y) for unit in game.units}
        maximum_penetration = 0.0
        for step in range(round(seconds / self.DT)):
            if before_step is not None:
                before_step(step, game)
            game.navigation_time += self.DT
            game.rebuild_unit_spatial_hash()
            game._movement_snapshot_active = True
            try:
                for unit in list(game.units):
                    game.update_unit(unit, self.DT)
            finally:
                game._movement_snapshot_active = False
            living = [unit for unit in game.units if unit.health > 0]
            for index, first in enumerate(living):
                for second in living[index + 1:]:
                    penetration = (
                        UNIT_SEPARATION_RADIUS - UNIT_SOFT_OVERLAP
                        - dist((first.x, first.y), (second.x, second.y))
                    )
                    maximum_penetration = max(maximum_penetration, penetration)
        result = (
            tuple(
                (
                    unit.uid,
                    round(unit.x, 7),
                    round(unit.y, 7),
                    round(unit.health, 7),
                    unit.target_pos,
                )
                for unit in game.units
            ),
            round(maximum_penetration, 7),
            game.path_calculation_count,
        )
        self.assertTrue(all(
            math.isfinite(value)
            for unit in game.units
            for value in (unit.x, unit.y)
        ))
        return starts, result

    def assert_deterministic(self, factory, seconds, before_step=None):
        first_game, observed = factory()
        starts, first = self.run_fixed(
            first_game, seconds,
            None if before_step is None else before_step(observed),
        )
        second_game, observed_again = factory()
        _, second = self.run_fixed(
            second_game, seconds,
            None if before_step is None else before_step(observed_again),
        )
        self.assertEqual(first, second)
        return first_game, observed, starts, first

    def test_two_friendly_groups_cross_at_right_angles(self):
        def scenario():
            game = self.game()
            movers = []
            for offset in (-1.2, 0, 1.2):
                horizontal = game.add_unit("swordsman", "green", 15, 30 + offset)
                vertical = game.add_unit("swordsman", "green", 30 + offset, 15)
                horizontal.target_pos = (45, 30 + offset)
                vertical.target_pos = (30 + offset, 45)
                movers += [horizontal, vertical]
            return game, movers

        game, movers, starts, result = self.assert_deterministic(scenario, 18)
        self.assertLess(result[1], .82)
        self.assertLess(result[2], 90)
        self.assertTrue(all(
            dist(starts[unit.uid], (unit.x, unit.y)) > 12 for unit in movers
        ))

    def test_opposing_groups_engage_head_on_with_bounded_melee_overlap(self):
        def scenario():
            game = self.game()
            greens, reds = [], []
            for offset in (-1.2, 0, 1.2):
                green = game.add_unit("shield", "green", 25, 40 + offset)
                red = game.add_unit("shield", "red", 35, 40 + offset)
                green.attack_timer = red.attack_timer = 999
                green.target, green.target_pos = red, (red.x, red.y)
                red.target, red.target_pos = green, (green.x, green.y)
                greens.append(green)
                reds.append(red)
            return game, greens + reds

        _, movers, starts, result = self.assert_deterministic(scenario, 10)
        self.assertLess(result[1], .72)
        self.assertLess(result[2], 80)
        self.assertTrue(any(
            dist(starts[unit.uid], (unit.x, unit.y)) > 2 for unit in movers
        ))

    def test_many_units_make_progress_through_one_narrow_gap(self):
        def scenario():
            game = self.game()
            movers = [
                game.add_unit(
                    "swordsman", "green",
                    15 - (index // 4) * 1.05,
                    48.35 + (index % 4) * 1.05,
                )
                for index in range(12)
            ]
            for y in list(range(43, 49)) + list(range(52, 58)):
                game.add_unit("king", "green", 30.5, y + .5)
            for unit in movers:
                unit.target_pos = (45, 50)
            return game, movers

        _, movers, starts, result = self.assert_deterministic(scenario, 32)
        self.assertLess(result[1], .9)
        self.assertLess(result[2], 300)
        self.assertGreater(sum(unit.x - starts[unit.uid][0] for unit in movers), 65)

    def test_fast_unit_eventually_routes_around_slow_ally(self):
        def scenario():
            game = self.game()
            slow = game.add_unit("shield", "green", 22, 65)
            fast = game.add_unit("swordsman", "green", 20.7, 65)
            slow.target_pos = fast.target_pos = (42, 65)
            return game, (slow, fast)

        _, (slow, fast), starts, result = self.assert_deterministic(scenario, 18)
        self.assertGreater(fast.x - starts[fast.uid][0], 10)
        self.assertGreater(fast.x, slow.x - 1.5)
        self.assertLess(result[2], 35)

    def test_dense_melee_surrounding_one_target_has_bounded_penetration(self):
        def scenario():
            game = self.game()
            target = game.add_unit("king", "red", 60, 60)
            target.health = 100000
            target.speed = 0
            attackers = []
            for index in range(16):
                angle = index * math.tau / 16
                unit = game.add_unit(
                    "swordsman", "green",
                    60 + math.cos(angle) * 4,
                    60 + math.sin(angle) * 4,
                )
                unit.target = target
                unit.target_pos = (target.x, target.y)
                attackers.append(unit)
            return game, attackers

        _, attackers, starts, result = self.assert_deterministic(scenario, 12)
        self.assertLess(result[1], .86)
        self.assertLess(result[2], 130)
        self.assertTrue(all(
            dist(starts[unit.uid], (unit.x, unit.y)) > 1.5
            for unit in attackers
        ))

    def test_nearby_formation_slots_settle_without_jitter(self):
        def scenario():
            game = self.game()
            units = []
            for index in range(9):
                slot = (70 + (index % 3) * 1.15, 70 + (index // 3) * 1.15)
                unit = game.add_unit(
                    "swordsman", "green",
                    slot[0] + (.04 if index % 2 else -.04),
                    slot[1],
                )
                unit.target_pos = slot
                units.append(unit)
            return game, units

        _, units, _, result = self.assert_deterministic(scenario, 6)
        self.assertLess(result[1], .2)
        self.assertLess(result[2], 10)
        self.assertTrue(all(
            dist((unit.x, unit.y), unit.target_pos) < .13
            for unit in units if unit.target_pos is not None
        ))

    def test_identical_spawns_and_corner_trap_remain_finite_and_in_bounds(self):
        def scenario():
            game = self.game()
            units = [
                game.add_unit("swordsman", "green", WORLD_MIN, WORLD_MIN)
                for _ in range(8)
            ]
            for unit in units:
                unit.target_pos = (WORLD_MIN, WORLD_MIN)
            return game, units

        _, units, _, result = self.assert_deterministic(scenario, 8)
        self.assertLess(result[1], 1.01)
        self.assertLess(result[2], 160)
        self.assertTrue(all(
            WORLD_MIN <= coordinate <= WORLD_MAX
            for unit in units for coordinate in (unit.x, unit.y)
        ))

    def test_route_hysteresis_survives_repeated_blocker_and_preserves_order(self):
        destination = (60, 85)

        def scenario():
            game = self.game()
            mover = game.add_unit("swordsman", "green", 20, 85)
            blocker = game.add_unit("king", "green", 27, 88)
            mover.target_pos = destination
            return game, (mover, blocker)

        def toggle(pair):
            _, blocker = pair

            def before(step, _game):
                blocker.x, blocker.y = (
                    (27, 85) if (step // 8) % 2 == 0 else (27, 88)
                )

            return before

        _, (mover, _), starts, result = self.assert_deterministic(
            scenario, 16, toggle
        )
        self.assertEqual(mover.target_pos, destination)
        self.assertGreater(mover.x - starts[mover.uid][0], 10)
        self.assertLess(result[2], 45)

    def test_safe_ranged_unit_does_not_repath_while_firing(self):
        def scenario():
            game = self.game()
            archer = game.add_unit("archer", "green", 50, 100)
            target = game.add_unit("shield", "red", 54, 100)
            target.health = 100000
            archer.target = target
            archer.target_pos = (target.x, target.y)
            game.visible.add((54, 100))
            return game, archer

        _, archer, _, result = self.assert_deterministic(scenario, 8)
        self.assertEqual(result[2], 0)
        self.assertEqual((archer.x, archer.y), (50, 100))


if __name__ == "__main__":
    unittest.main()
