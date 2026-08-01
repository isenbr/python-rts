"""Deterministic headless integration scenarios for the Verdant Crown enemy AI."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import (
    AIState,
    Game,
    TerrainCell,
    UNIT_COSTS,
    UNIT_KINDS,
    dist,
    offset_from,
)


def _fill_plain_terrain(game):
    """Give controlled AI scenarios an unobstructed visibility baseline."""
    game.terrain = {
        position: TerrainCell("plains", 0) for position in game.terrain
    }


def _scenario_idle(game):
    """Leave the starting player army at home."""


def _scenario_player_assault(game):
    """Send a larger starting army across the map to force field combat."""
    game.recruit("swordsman")
    game.recruit("swordsman")
    for unit in game.units:
        if unit.is_player_commandable:
            unit.target_pos = (game.team_king("red").x, game.team_king("red").y)


def _scenario_base_pressure(game):
    """Place a visible attack group near the Crimson King to exercise recall."""
    for index, kind in enumerate(("swordsman", "swordsman", "swordsman", "archer")):
        x, y = offset_from(
            (game.team_king("red").x, game.team_king("red").y),
            (-17 + index * .4, -2 + index),
        )
        unit = game.add_unit(kind, "green", x, y)
        unit.target = game.team_king("red")
        unit.target_pos = (game.team_king("red").x, game.team_king("red").y)


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
            game.team_king("red").x - 5,
            game.team_king("red").y - 4 + index * .4,
        )
        for index, kind in enumerate(kinds)
    ]
    ai._update_strategic_knowledge()
    return observed


def simulate_integration_review(seed=73, purchases=60):
    """Report deterministic loss-gated production scenarios A through D."""
    neutral = {kind: 1 / len(UNIT_KINDS) for kind in UNIT_KINDS}

    def encounter(player_count, red_count):
        game = Game(enemy_rng=random.Random(seed))
        _fill_plain_terrain(game)
        game.units[:] = [
            unit for unit in game.units if unit.is_king_objective
        ]
        ai = game.enemy_ai
        ai._known_red_uids.clear()
        ai.recruitment_timer = 999
        reds = [
            game.add_unit("swordsman", "red", 40, 40 + index * .2)
            for index in range(red_count)
        ]
        players = [
            game.add_unit("shield", "green", 44, 40 + index * .2)
            for index in range(player_count)
        ]
        ai.squad = {unit.uid for unit in reds}
        ai.formation_roles = {
            unit.uid: ai.FORMATION_ROLE_BY_KIND[unit.kind]
            for unit in reds
        }
        ai.wave_start_strength = len(reds)
        ai.state = AIState.ATTACKING
        ai._update_strategic_knowledge()
        ai.combat_opponent_uids = {unit.uid for unit in players}
        return game, ai, reds, players

    # A: observation followed by a player loss leaves the neutral target intact.
    loss_game, loss_ai, _, losing_players = encounter(1, 1)
    observed_target = loss_ai.production_target_shares()
    for unit in losing_players:
        unit.health = 0
    loss_ai._update_strategic_knowledge()
    loss_ai._begin_recovery()
    after_player_loss = loss_ai.production_target_shares()

    # B: a surviving all-shield army causes a casualty retreat and is learned.
    win_game, win_ai, losing_wave, _ = encounter(1, 2)
    losing_wave[0].health = 0
    win_ai.make_decision()
    learned_target = win_ai.production_target_shares()
    win_game.units[:] = [
        unit for unit in win_game.units if unit.is_king_objective
    ]
    win_ai.squad.clear()
    win_ai.reserve.clear()
    win_ai.defenders.clear()
    win_ai._known_red_uids.clear()
    learned_spending = _produce_fixed_sequence(win_ai, win_game, purchases)

    # C: a fresh weaker assessment retreats and learns before any casualties.
    retreat_game, retreat_ai, retreat_wave, _ = encounter(8, 1)
    health_before = sum(unit.health for unit in retreat_wave)
    retreat_ai.make_decision()
    health_after = sum(unit.health for unit in retreat_wave)
    assessment = retreat_ai.latest_combat_assessments[
        tuple(sorted(retreat_ai.squad))
    ]

    # D: the normal launch gate holds below its essence target and records a
    # cost-valid launch once another purchasable unit reaches the threshold.
    gate_game = Game(enemy_rng=random.Random(seed))
    gate_game.units[:] = [
        unit for unit in gate_game.units if unit.is_king_objective
    ]
    gate_ai = gate_game.enemy_ai
    gate_ai._known_red_uids.clear()
    gate_ai.recruitment_timer = 999
    sword_cost = UNIT_COSTS["swordsman"]
    below_count = (gate_ai.TARGET_GROUP_ESSENCE - 1) // sword_cost
    gate_members = [
        gate_game.add_unit("swordsman", "red", 90, 40 + index * .1)
        for index in range(below_count)
    ]
    gate_ai.state = AIState.RALLYING
    gate_ai._assign_available_units()
    for unit in gate_members:
        unit.x, unit.y = gate_ai._formation_destination(unit)
    gate_ai.make_decision()
    below_gate = gate_ai.last_launch_gate.copy()
    launched_below = bool(gate_ai.wave_history)
    added = gate_game.add_unit("swordsman", "red", 90, 45)
    gate_members.append(added)
    gate_ai._assign_available_units()
    for unit in gate_members:
        unit.x, unit.y = gate_ai._formation_destination(unit)
    gate_ai.make_decision()
    launched_wave = gate_ai.wave_history[-1]

    return {
        "seed": seed,
        "production_samples": purchases,
        "scenario_a_player_loses": {
            "player_composition": {"shield": "100%"},
            "target_after_observation": observed_target,
            "target_after_player_loss": after_player_loss,
            "remained_neutral": (
                observed_target == neutral and after_player_loss == neutral
            ),
        },
        "scenario_b_player_wins": {
            "player_composition": {"shield": "100%"},
            "ai_state": win_ai.state.name,
            "target_after_ai_defeat": learned_target,
            "subsequent_spending_shares": _shares(learned_spending),
        },
        "scenario_c_weaker_retreat": {
            "player_composition": {"shield": "100%"},
            "assessment": assessment.classification.name,
            "assessment_stale": assessment.stale,
            "ai_state": retreat_ai.state.name,
            "casualties": health_before - health_after,
            "target_before_rebuild": retreat_ai.production_target_shares(),
        },
        "scenario_d_launch_gate": {
            "target_essence": gate_ai.TARGET_GROUP_ESSENCE,
            "below_target_essence": below_gate["squad_essence"],
            "below_target_decision": below_gate["decision"],
            "launched_below_target": launched_below,
            "launched_wave_essence": launched_wave["squad_essence"],
        },
    }


def simulate_launch_gate_scenario(seed=73):
    """Deterministically hold a weak wave, then permit counter reinforcements."""
    game = Game(enemy_rng=random.Random(seed))
    game.units[:] = [unit for unit in game.units if unit.is_king_objective]
    ai = game.enemy_ai
    ai._known_red_uids.clear()
    ai.recruitment_timer = 999

    players = [
        game.add_unit(
            "archer", "green",
            game.team_king("red").x - 5, game.team_king("red").y + index,
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
        for index in range(18)
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
    _fill_plain_terrain(game)
    game.units[:] = [unit for unit in game.units if unit.is_king_objective]
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
            game.team_king("red").x - 5, game.team_king("red").y - 3 + index,
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
    game = Game(enemy_rng=random.Random(seed), terrain_seed=seed)
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
                    game.team_king("green"), game.team_king("red")
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
        "kings": {
            "player": round(game.objective_health("green"), 1),
            "enemy": round(game.objective_health("red"), 1),
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
