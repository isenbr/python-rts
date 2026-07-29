import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import Game, UNIT_COSTS


class LastSeenPlayerArmyTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(enemy_rng=random.Random(17))
        self.game.units.clear()
        self.ai = self.game.enemy_ai
        self.ai._known_red_uids.clear()

    def test_hidden_distant_player_never_enters_snapshot(self):
        hidden = self.game.add_unit("archer", "green", 40, 40)

        self.ai._update_strategic_knowledge()

        self.assertNotIn(hidden.uid, self.ai.last_seen_player_army)

    def test_visible_player_enters_snapshot_with_observed_facts(self):
        self.game.add_unit("swordsman", "red", 40, 40)
        player = self.game.add_unit("shield", "green", 45, 42)
        player.health = 123
        self.ai.elapsed = 7.25

        self.ai._update_strategic_knowledge()

        sighting = self.ai.last_seen_player_army[player.uid]
        self.assertEqual(sighting.uid, player.uid)
        self.assertEqual(sighting.kind, "shield")
        self.assertEqual(sighting.health, 123)
        self.assertEqual(sighting.observed_at, 7.25)

    def test_visible_update_replaces_health_position_and_time(self):
        self.game.add_unit("swordsman", "red", 40, 40)
        player = self.game.add_unit("swordsman", "green", 45, 40)
        self.ai._update_strategic_knowledge()
        first = self.ai.last_seen_player_army[player.uid]

        player.x = 46
        player.y = 41
        player.health = 61
        self.ai.elapsed = 3.5
        self.ai._update_strategic_knowledge()

        updated = self.ai.last_seen_player_army[player.uid]
        self.assertNotEqual(updated, first)
        self.assertEqual((updated.x, updated.y), (46, 41))
        self.assertEqual(updated.health, 61)
        self.assertEqual(updated.observed_at, 3.5)

    def test_visibly_confirmed_death_removes_snapshot(self):
        self.game.add_unit("swordsman", "red", 40, 40)
        player = self.game.add_unit("archer", "green", 45, 40)
        self.ai._update_strategic_knowledge()

        player.health = 0
        self.ai._update_strategic_knowledge()

        self.assertNotIn(player.uid, self.ai.last_seen_player_army)

    def test_losing_vision_and_ttl_expiry_preserves_snapshot(self):
        self.game.add_unit("swordsman", "red", 40, 40)
        player = self.game.add_unit("shield", "green", 45, 40)
        self.ai._update_strategic_knowledge()
        original = self.ai.last_seen_player_army[player.uid]

        player.x = 80
        self.ai.elapsed += self.ai.PLAYER_KNOWLEDGE_TTL + .01
        self.ai._update_strategic_knowledge()

        self.assertEqual(self.ai.last_seen_player_army[player.uid], original)
        self.assertNotIn(player.uid, self.ai.player_knowledge)
        self.assertNotIn(player.uid, self.ai.combat_observations)

    def test_hidden_death_cleanup_does_not_reveal_death(self):
        self.game.add_unit("swordsman", "red", 40, 40)
        player = self.game.add_unit("shield", "green", 45, 40)
        self.ai._update_strategic_knowledge()

        player.x = 80
        player.health = 0
        self.ai.forget_player_unit(player.uid)

        self.assertIn(player.uid, self.ai.last_seen_player_army)

    def test_composition_essence_uses_unit_costs(self):
        self.game.add_unit("swordsman", "red", 40, 40)
        for index, kind in enumerate(("swordsman", "archer", "archer", "shield")):
            self.game.add_unit(kind, "green", 44, 40 + index)
        self.ai._update_strategic_knowledge()

        counts, essence = self.ai.last_seen_player_composition()

        self.assertEqual(
            counts, {"swordsman": 1, "archer": 2, "shield": 1}
        )
        self.assertEqual(essence, {
            "swordsman": UNIT_COSTS["swordsman"],
            "archer": 2 * UNIT_COSTS["archer"],
            "shield": UNIT_COSTS["shield"],
        })
        self.assertNotEqual(essence["archer"], counts["archer"])


if __name__ == "__main__":
    unittest.main()
