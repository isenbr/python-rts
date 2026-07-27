"""Deterministic headless integration scenarios for the Verdant Crown enemy AI."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import AIState, Game, dist


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
        unit = game.add_unit(kind, "green", 160 + index * .4, 98 + index)
        unit.target = game.enemy_base
        unit.target_pos = (game.enemy_base.x, game.enemy_base.y)


SCENARIOS = {
    "idle": _scenario_idle,
    "player_assault": _scenario_player_assault,
    "base_pressure": _scenario_base_pressure,
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
    produced = Counter(entry["kind"] for entry in ai.production_history)
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
        "defensive_frequency": round(defensive_steps * dt / max(elapsed, dt), 4),
        "produced": dict(sorted(produced.items())),
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
    parser.add_argument("--seeds", default="1,7,23")
    parser.add_argument("--scenarios", default="idle,player_assault,base_pressure")
    parser.add_argument("--duration", type=float, default=360.0)
    parser.add_argument("--dt", type=float, default=.05)
    args = parser.parse_args()
    for scenario in args.scenarios.split(","):
        for seed in (int(value) for value in args.seeds.split(",")):
            print(json.dumps(
                simulate(seed, scenario, args.duration, args.dt),
                sort_keys=True,
            ))


if __name__ == "__main__":
    main()
