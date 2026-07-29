"""Deterministic headless integration scenarios for the Verdant Crown enemy AI."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import AIState, Game, UNIT_COSTS, UNIT_KINDS, dist, offset_from


def _scenario_idle(game):
    """Leave the starting player army at home."""


def _scenario_player_assault(game):
    """Send a larger starting army across the map to force field combat."""
    game.recruit("swordsman")
    game.recruit("swordsman")
    for unit in game.units:
        if unit.team == "green":
            unit.target_pos = (game.enemy_base.x, game.enemy_base.y)


def _scenario_base_pressure(game):
    """Place a visible attack group near the Crimson Hold to exercise recall."""
    for index, kind in enumerate(("swordsman", "swordsman", "swordsman", "archer")):
        x, y = offset_from(
            (game.enemy_base.x, game.enemy_base.y),
            (-17 + index * .4, -2 + index),
        )
        unit = game.add_unit(kind, "green", x, y)
        unit.target = game.enemy_base
        unit.target_pos = (game.enemy_base.x, game.enemy_base.y)


SCENARIOS = {
    "idle": _scenario_idle,
    "player_assault": _scenario_player_assault,
    "base_pressure": _scenario_base_pressure,
}


def _shares(values):
    total = sum(values.values())
    return {
        kind: round(values[kind] / total, 4) if total else 0.0
        for kind in UNIT_KINDS
    }


def _produce_fixed_sequence(ai, game, purchases):
    game.enemy_essence = 1_000_000
    for _ in range(purchases):
        kind = ai.choose_production()
        if kind is None or not game.recruit(kind, "red"):
            raise RuntimeError("deterministic production sequence stalled")
    return ai.production_essence_investment()


def _observe_army(game, kinds):
    ai = game.enemy_ai
    observed = [
        game.add_unit(
            kind, "green",
            game.enemy_base.x - 5,
            game.enemy_base.y - 4 + index * .4,
        )
        for index, kind in enumerate(kinds)
    ]
    ai._update_strategic_knowledge()
    return observed


def simulate_integration_review(seed=73, purchases=60):
    """Report the six deterministic enemy-AI integration review scenarios."""
    # 1. With no sightings, spending converges by essence rather than unit count.
    default_game = Game(enemy_rng=random.Random(seed))
    default_game.units.clear()
    default_ai = default_game.enemy_ai
    default_ai._known_red_uids.clear()
    default_spending = _produce_fixed_sequence(
        default_ai, default_game, purchases
    )

    # 2-3. Equal observed archer/shield essence maps to equal shield/sword
    # counters, then a new swordsman sighting redirects the target to archers.
    counter_game = Game(enemy_rng=random.Random(seed))
    counter_game.units.clear()
    counter_ai = counter_game.enemy_ai
    counter_ai._known_red_uids.clear()
    first_players = _observe_army(
        counter_game, ("archer",) * 3 + ("shield",) * 5
    )
    for unit in first_players:
        unit.x = counter_game.player_base.x
    counter_ai._update_strategic_knowledge()
    first_observed = counter_ai.last_seen_player_composition()[1]
    first_target = counter_ai.production_target_shares()
    first_spending = _produce_fixed_sequence(
        counter_ai, counter_game, purchases
    )
    for unit in first_players:
        unit.x = counter_game.enemy_base.x - 5
        unit.health = 0
    counter_ai._update_strategic_knowledge()
    counter_game.units[:] = [
        unit for unit in counter_game.units if unit.team == "green"
    ]
    counter_ai._known_red_uids.clear()
    _observe_army(counter_game, ("swordsman",) * 5)
    counter_ai._update_strategic_knowledge()
    changed_observed = counter_ai.last_seen_player_composition()[1]
    changed_target = counter_ai.production_target_shares()
    changed_spending = _produce_fixed_sequence(
        counter_ai, counter_game, purchases
    )

    # 4-5. A weak rally group is held until counter reinforcements clear the
    # exact same last-seen-army strength gate.
    gate = simulate_launch_gate_scenario(seed)

    # 6. Compare deterministic rank ordering at the rally and attack anchors.
    formation_game = Game(enemy_rng=random.Random(seed))
    formation_game.units.clear()
    formation_ai = formation_game.enemy_ai
    formation_ai._known_red_uids.clear()
    members = [
        formation_game.add_unit(kind, "red", 90, 58 + index)
        for index, kind in enumerate(("shield", "swordsman", "archer"))
    ]
    formation_ai.squad = {unit.uid for unit in members}
    formation_ai.formation_roles = {
        unit.uid: formation_ai.FORMATION_ROLE_BY_KIND[unit.kind]
        for unit in members
    }

    def rank_order(anchor):
        destinations = {
            unit.kind: formation_ai._formation_destination(
                unit, members, anchor=anchor
            )
            for unit in members
        }
        # Red advances toward decreasing x, so the lowest x is the front rank.
        return {
            "front_to_back": sorted(
                destinations, key=lambda kind: destinations[kind][0]
            ),
            "destinations": {
                kind: [round(value, 3) for value in destinations[kind]]
                for kind in UNIT_KINDS
            },
        }

    observed_counts, _ = counter_ai.last_seen_player_composition()
    return {
        "seed": seed,
        "production_samples": purchases,
        "no_player_information": {
            "observed_player_essence_shares": {
                kind: 0.0 for kind in UNIT_KINDS
            },
            "desired_ai_counter_shares": {
                kind: round(1 / len(UNIT_KINDS), 4)
                for kind in UNIT_KINDS
            },
            "actual_ai_spending_shares": _shares(default_spending),
        },
        "equal_archer_shield_essence": {
            "observed_player_essence_shares": _shares(first_observed),
            "desired_ai_counter_shares": {
                kind: round(first_target[kind], 4) for kind in UNIT_KINDS
            },
            "actual_ai_spending_shares": _shares(first_spending),
        },
        "new_sighting": {
            "observed_player_counts": observed_counts,
            "observed_player_essence_shares": _shares(changed_observed),
            "desired_ai_counter_shares": {
                kind: round(changed_target[kind], 4) for kind in UNIT_KINDS
            },
            "actual_ai_spending_shares": _shares(changed_spending),
        },
        "launch_gate": {
            "held": {
                "strength_ratio": round(gate["held"]["ratio"], 4),
                "decision": gate["held"]["decision"],
            },
            "after_counter_production": {
                "strength_ratio": round(gate["permitted"]["ratio"], 4),
                "decision": gate["permitted"]["decision"],
            },
            "wave_composition": gate["wave_composition"],
        },
        "formation_rank_ordering": {
            "rally": rank_order(formation_ai.rally_point),
            "advance": rank_order((
                formation_game.player_base.x,
                formation_game.player_base.y,
            )),
        },
    }


def simulate_launch_gate_scenario(seed=73):
    """Deterministically hold a weak wave, then permit counter reinforcements."""
    game = Game(enemy_rng=random.Random(seed))
    game.units.clear()
    ai = game.enemy_ai
    ai._known_red_uids.clear()
    ai.recruitment_timer = 999

    players = [
        game.add_unit(
            "archer", "green",
            game.enemy_base.x - 5, game.enemy_base.y + index,
        )
        for index in range(4)
    ]
    ai._update_strategic_knowledge()
    for unit in players:
        unit.x = 10
    ai._update_strategic_knowledge()

    red = [
        game.add_unit("shield", "red", 90, 45 + index)
        for index in range(2)
    ]
    ai.make_decision()
    held = ai.last_launch_gate.copy()
    red.extend(
        game.add_unit("shield", "red", 90, 50 + index)
        for index in range(6)
    )
    ai.make_decision()
    for unit in red:
        if unit.uid in ai.squad:
            unit.x, unit.y = ai._formation_destination(unit)
    ai.make_decision()
    return {
        "seed": seed,
        "held": held,
        "permitted": ai.wave_history[-1]["launch_gate"],
        "wave_composition": ai.wave_history[-1]["composition"],
        "state": ai.state.name,
    }


def simulate_integrated_decision_scenario(seed=73):
    """Exercise production and combat-decision precedence in one fixed setup."""
    game = Game(enemy_rng=random.Random(seed))
    game.units.clear()
    game.state = "playing"
    ai = game.enemy_ai
    ai._known_red_uids.clear()
    ai.recruitment_timer = 999
    game.enemy_essence = 10_000

    for index in range(2):
        game.add_unit("swordsman", "red", 40, 38 + index)
    ordinary_scores = ai.production_scores().copy()
    ordinary_choice = ai.choose_production()

    revealed_archers = [
        game.add_unit(
            "archer", "green",
            game.enemy_base.x - 5, game.enemy_base.y - 3 + index,
        )
        for index in range(ai.ARCHER_THREAT_HIGH_THRESHOLD)
    ]
    ai._update_strategic_knowledge()
    archer_scores = ai.production_scores().copy()
    archer_choice = ai.choose_production()

    # Keep the production sighting in strategic memory, but remove those units
    # from this controlled field engagement so only legitimate nearby sightings
    # affect its strength assessment.
    game.units = [
        unit for unit in game.units if unit not in revealed_archers
    ]
    red_group = [
        game.add_unit("swordsman", "red", 40, 42 + index * .2)
        for index in range(4)
    ]
    opponents = [
        game.add_unit("swordsman", "green", 44, 42 + index * .2)
        for index in range(7)
    ]
    ai.squad = {unit.uid for unit in red_group}
    ai.formation_roles = {
        unit.uid: ai.FORMATION_ROLE_BY_KIND[unit.kind]
        for unit in red_group
    }
    ai.wave_start_strength = len(red_group)
    ai.state = AIState.ATTACKING
    ai._update_strategic_knowledge()
    ai.make_decision()
    initial = ai.latest_combat_assessments[tuple(sorted(ai.squad))]

    reinforcements = [
        game.add_unit("swordsman", "red", 41, 42 + index * .2)
        for index in range(12)
    ]
    ai.elapsed += ai.COMBAT_DECISION_INTERVAL
    ai.make_decision()
    reinforced = ai.latest_combat_assessments[tuple(sorted(ai.squad))]

    for unit in red_group[:2]:
        unit.health = 0
    for unit in opponents[:2]:
        unit.health = 0
    ai._update_strategic_knowledge()
    ai.elapsed += ai.COMBAT_DECISION_INTERVAL
    ai.make_decision()
    casualty_override = ai.latest_combat_assessments[tuple(sorted(ai.squad))]

    for unit in reinforcements[:10]:
        unit.health = 0
    for unit in red_group[2:3]:
        unit.health = 0
    ai._update_strategic_knowledge()
    ai.elapsed += ai.COMBAT_DECISION_INTERVAL
    ai.make_decision()
    final = ai.latest_combat_assessments[tuple(sorted(ai.squad))]

    return {
        "seed": seed,
        "production": {
            "ordinary_choice": ordinary_choice,
            "archer_threat_choice": archer_choice,
            "shield_score_shift": (
                archer_scores["shield"] - ordinary_scores["shield"]
            ),
            "swordsman_score_shift": (
                archer_scores["swordsman"] - ordinary_scores["swordsman"]
            ),
        },
        "combat": [
            {
                "stage": "initial_weaker",
                "state": AIState.RECOVERING.name,
                "classification": initial.classification.name,
                "ratio": round(initial.advantage_ratio, 4),
            },
            {
                "stage": "reinforced_reengage",
                "state": AIState.ATTACKING.name,
                "classification": reinforced.classification.name,
                "ratio": round(reinforced.advantage_ratio, 4),
            },
            {
                "stage": "casualty_override",
                "state": AIState.ATTACKING.name,
                "classification": casualty_override.classification.name,
                "ratio": round(casualty_override.advantage_ratio, 4),
            },
            {
                "stage": "final_weaker_retreat",
                "state": ai.state.name,
                "classification": final.classification.name,
                "ratio": round(final.advantage_ratio, 4),
            },
        ],
    }


def simulate(seed, scenario="idle", duration=360.0, dt=.05):
    game = Game(enemy_rng=random.Random(seed))
    game.state = "playing"
    game.update_visibility()
    SCENARIOS[scenario](game)
    elapsed = 0.0
    defensive_steps = 0
    invalid_target_frames = 0
    stalled_units = set()
    samples = {}
    last_sample_bucket = -1

    while elapsed + 1e-9 < duration and not game.winner:
        game.update(min(dt, duration - elapsed))
        elapsed += min(dt, duration - elapsed)
        if game.enemy_ai.state == AIState.DEFENDING:
            defensive_steps += 1
        for unit in game.units:
            if (
                unit.target is not None
                and (unit.target not in game.units and unit.target not in (
                    game.player_base, game.enemy_base
                ) or getattr(unit.target, "health", 0) <= 0)
            ):
                invalid_target_frames += 1
        # Five-second samples flag units ordered to move but making no meaningful
        # progress. Active combat and deliberate cohesion holds are excluded.
        bucket = int(elapsed / 5)
        if bucket != last_sample_bucket:
            last_sample_bucket = bucket
            for unit in game.units:
                previous = samples.get(unit.uid)
                if (
                    previous is not None
                    and unit.target is None
                    and unit.target_pos is not None
                    and dist(previous, (unit.x, unit.y)) < .05
                    and unit.uid in game.enemy_ai.squad
                    and game.enemy_ai.state != AIState.ATTACKING
                ):
                    stalled_units.add(unit.uid)
                samples[unit.uid] = (unit.x, unit.y)

    ai = game.enemy_ai
    living_red_ids = {unit.uid for unit in game.units if unit.team == "red"}
    transition_counts = Counter(state.name for _, state in ai.state_history)
    produced_counter = Counter(entry["kind"] for entry in ai.production_history)
    produced = {kind: produced_counter[kind] for kind in UNIT_KINDS}
    produced_essence = {
        kind: produced[kind] * UNIT_COSTS[kind] for kind in UNIT_KINDS
    }
    total_produced_essence = sum(produced_essence.values())
    living_red_counter = Counter(
        unit.kind for unit in game.units if unit.team == "red" and unit.health > 0
    )
    result = {
        "seed": seed,
        "scenario": scenario,
        "outcome": game.winner or "TIME_LIMIT",
        "duration": round(elapsed, 2),
        "first_attack": (
            round(ai.wave_history[0]["launched_at"], 2)
            if ai.wave_history else None
        ),
        "wave_count": len(ai.wave_history),
        "waves": ai.wave_history,
        "launch_gates": ai.launch_gate_history,
        "defensive_frequency": round(defensive_steps * dt / max(elapsed, dt), 4),
        "produced": produced,
        "produced_essence": produced_essence,
        "produced_essence_shares": {
            kind: round(
                produced_essence[kind] / total_produced_essence, 4
            ) if total_produced_essence else 0.0
            for kind in UNIT_KINDS
        },
        "living_red": {kind: living_red_counter[kind] for kind in UNIT_KINDS},
        "enemy_essence_unspent": round(game.enemy_essence, 2),
        "state_transitions": dict(sorted(transition_counts.items())),
        "stalled_units": len(stalled_units),
        "invalid_target_frames": invalid_target_frames,
        "stale_ai_unit_ids": len(
            (ai.squad | ai.reserve | ai.defenders) - living_red_ids
        ),
        "bases": {
            "player": max(0, round(game.player_base.health, 1)),
            "enemy": max(0, round(game.enemy_base.health, 1)),
        },
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--integration-review",
        action="store_true",
        help="print the deterministic six-scenario integration review",
    )
    parser.add_argument("--seeds", default="1,7,23")
    parser.add_argument("--scenarios", default="idle,player_assault,base_pressure")
    parser.add_argument("--duration", type=float, default=360.0)
    parser.add_argument("--dt", type=float, default=.05)
    args = parser.parse_args()
    if args.integration_review:
        print(json.dumps(simulate_integration_review(), sort_keys=True, indent=2))
        return
    for scenario in args.scenarios.split(","):
        for seed in (int(value) for value in args.seeds.split(",")):
            print(json.dumps(
                simulate(seed, scenario, args.duration, args.dt),
                sort_keys=True,
            ))


if __name__ == "__main__":
    main()
