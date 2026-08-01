"""Deterministic structural performance probes for movement and navigation."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from main import EnemyAI, Game, TerrainCell, WORLD_MAX, WORLD_MIN, dist


ARMY_SIZES = (25, 50, 100, 200)
FIXED_DT = .05
INTEGRATED_TERRAIN_SEED = 6


def _movement_game(count, seed):
    game = Game(enemy_rng=random.Random(seed))
    game.state = "playing"
    game.units.clear()
    game.enemy_ai.update = lambda dt: None
    # Keep this structural movement benchmark comparable with its historical
    # open-map baseline; terrain integration has a separate deterministic test.
    game.terrain = {
        position: TerrainCell("plains", 0) for position in game.terrain
    }
    columns = 20
    for index in range(count):
        x = 8 + (index % columns) * 2.5
        y = 8 + (index // columns) * 2.5
        unit = game.add_unit("swordsman", "green", x, y)
        unit.target_pos = (min(WORLD_MAX, x + 35), y)
    return game


def simulate_army_scale(count, seconds=2.0, seed=73):
    """Run a spread, unobstructed army and return structural scaling metrics."""
    game = _movement_game(count, seed)
    starts = {unit.uid: (unit.x, unit.y) for unit in game.units}
    candidate_checks = candidate_queries = 0
    maximum_candidates = 0
    steps = round(seconds / FIXED_DT)
    started = time.perf_counter()
    for _ in range(steps):
        game.navigation_time += FIXED_DT
        game.rebuild_unit_spatial_hash()
        game._movement_snapshot_active = True
        try:
            for unit in list(game.units):
                game.update_unit(unit, FIXED_DT)
        finally:
            game._movement_snapshot_active = False
        spatial = game.unit_spatial_hash
        candidate_checks += spatial.candidate_checks
        candidate_queries += spatial.candidate_queries
        maximum_candidates = max(
            maximum_candidates, spatial.maximum_query_candidates
        )
    update_seconds = time.perf_counter() - started
    progress = [
        dist(starts[unit.uid], (unit.x, unit.y)) for unit in game.units
    ]
    return {
        "units": count,
        "simulated_seconds": seconds,
        "average_nearby_candidates": round(
            candidate_checks / max(1, candidate_queries), 4
        ),
        "maximum_nearby_candidates": maximum_candidates,
        "paths_per_simulated_second": round(
            game.path_calculation_count / seconds, 4
        ),
        "expanded_astar_nodes": game.path_expanded_nodes,
        "maximum_astar_expansion": game.path_max_expanded_nodes,
        "movement_update_seconds": round(update_seconds, 6),
        "minimum_progress": round(min(progress), 4),
        "all_coordinates_finite": all(
            math.isfinite(value)
            for unit in game.units for value in (unit.x, unit.y)
        ),
        "all_units_in_bounds": all(
            WORLD_MIN <= value <= WORLD_MAX
            for unit in game.units for value in (unit.x, unit.y)
        ),
    }


def simulate_scaling(sizes=ARMY_SIZES, seconds=2.0, seed=73):
    return [simulate_army_scale(size, seconds, seed) for size in sizes]


def simulate_integrated_battle(frames=300, warmup=60, seed=73):
    """Measure a deterministic, rendered 100-unit dense battle at 60 Hz."""
    # Pin terrain independently from gameplay's fresh-match seeds so benchmark
    # comparisons measure code changes instead of a different random map.
    game = Game(
        enemy_rng=random.Random(seed), terrain_seed=INTEGRATED_TERRAIN_SEED
    )
    game.state = "playing"
    game.units[:] = [
        unit for unit in game.units
        if unit.is_king_objective or unit.is_autonomous_guard
    ]
    for team, start_x, destination in (
        ("green", 42, (65, 52)),
        ("red", 60, (42, 52)),
    ):
        for index in range(47):
            unit = game.add_unit(
                ("swordsman", "archer", "shield")[index % 3],
                team,
                start_x + (index % 10) * .8,
                48 + (index // 10) * .9,
            )
            unit.health = 100000
            unit.target_pos = destination
            if team == "green":
                unit.order_pos = destination
    game.enemy_ai = EnemyAI(game, random.Random(seed), .25)
    game.enemy_ai.recruitment_timer = 999
    game.update_visibility()
    game.draw_game()
    for _ in range(warmup):
        game.update(1 / 60)
        game.draw_game()
    frame_times = []
    for _ in range(frames):
        started = time.perf_counter()
        game.update(1 / 60)
        game.draw_game()
        frame_times.append(time.perf_counter() - started)
    ordered = sorted(frame_times)
    percentile_index = max(0, math.ceil(len(ordered) * .95) - 1)
    average = statistics.mean(frame_times)
    return {
        "units": len(game.units),
        "frames": frames,
        "average_frame_ms": round(average * 1000, 3),
        "p95_frame_ms": round(ordered[percentile_index] * 1000, 3),
        "maximum_frame_ms": round(max(frame_times) * 1000, 3),
        "average_fps": round(1 / average, 3),
        "path_calculations": game.path_calculation_count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--sizes", default="25,50,100,200")
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument("--integrated", action="store_true")
    parser.add_argument("--assert-60fps", action="store_true")
    args = parser.parse_args()
    sizes = tuple(int(value) for value in args.sizes.split(","))
    result = (
        simulate_integrated_battle(seed=args.seed)
        if args.integrated
        else simulate_scaling(sizes, args.seconds, args.seed)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.assert_60fps and args.integrated:
        if result["average_frame_ms"] > 1000 / 60 or result["p95_frame_ms"] > 20:
            raise SystemExit("100-unit integrated benchmark missed its frame budget")


if __name__ == "__main__":
    main()
