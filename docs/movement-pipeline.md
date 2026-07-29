# Existing movement pipeline

This document describes movement after shared local separation and before
dynamic pathfinding is implemented.

## Call graph

```text
Game.update(dt)
├── EnemyAI.update(dt)
│   └── EnemyAI.make_decision()
│       ├── assigns strategic `Unit.target_pos` values
│       └── may assign or clear combat `Unit.target` values
└── Game.update_unit(unit, dt), once per unit in list order
    ├── king objective: restore `home_position`, acquire/attack locally, return
    ├── autonomous guard
    │   ├── Game.autonomous_guard_target()
    │   ├── Game.guard_chase_destination(), or use `home_position`
    │   └── Game.move_unit_toward()
    └── purchasable army unit
        ├── red: EnemyAI.choose_target()
        ├── green: Game.find_target()
        ├── red only: EnemyAI.tactical_destination()
        │   ├── archer retreat/hold
        │   └── melee archer-screen position
        ├── Game.move_unit_toward(tactical_pos), if usable
        ├── chase/attack `target`, if present
        └── Game.move_unit_toward(target_pos), otherwise
            └── preferred velocity + Game.unit_separation_vector()
```

`Game.move_unit_toward` is the common movement primitive. It combines normalized
preferred travel with a local separation velocity, clamps the result to the
map, and records whether displacement occurred. It has no blocked timer, route
search, or waypoint state.

## Destination sources

### Player orders and formation offsets

`Game.issue_order` collects selected, commandable green army units. Clicking a
visible red unit within 1.5 tiles assigns that object as every selected unit's
`target` and copies its current position to `target_pos`.

A ground order clears combat targets and lays the selected units out in a
square-ish grid. The column count is `ceil(sqrt(count))`; each slot is spaced
1.15 world tiles apart. Every resulting destination is clamped by
`clamp_to_map`. The offsets affect only destinations, so units whose routes
converge or cross receive no separation while traveling.

### Enemy strategic and tactical destinations

`EnemyAI.make_decision` supplies red strategic destinations according to its
state. Building and rallying use `_formation_destination`; attacking advances
the formation toward the green king; defending assigns threats, archer offsets,
or reserve positions; recovering sends most units to the rally point and keeps
selected recovery guards in place. Formation destinations use explicit rank
roles and 1.45 lateral spacing, then clamp to the map.

On every red army-unit update, `EnemyAI.tactical_destination` may temporarily
override that strategic destination. Archers can retreat from close melee and
melee units can screen a nearby allied archer. Tactical positions are
constrained to the current strategic posture and clamped to the map. Separation
is no longer produced here, preventing double application.

### Guards returning to posts

Knights are autonomous guards rather than army-commandable units. Their
`home_position` is their post. A guard without a valid local target, or one
whose previous target has escaped the leash, moves directly home. Within .08
tiles it snaps exactly to the post and clears `target_pos`.

### Chasing and attacking

Army units acquire a local automatic target before movement: red uses
`EnemyAI.choose_target`, while green uses `Game.find_target` and therefore
requires visibility. An explicit live target is preserved unless target
selection replaces it. If the target is inside attack range, the unit attacks
when its cooldown permits and does not move. Otherwise its current coordinates
are copied into `target_pos`, and the unit moves directly toward them.

Guards use the same range/attack decision but clamp their pursuit destination
to the guard leash. Kings never move and only attack local targets.

### Archer movement locks

Every archer attack sets `movement_lock_timer` to 4/3 seconds. `update_unit`
decrements the timer and suppresses both tactical and ordinary movement while
it remains positive. Target acquisition and attacks still run. A red archer
with a safe in-range shot also declines tactical shuffling, and an archer may
attack only if it has not already moved in that update.

### Map-boundary clamping

Ground-order destinations, red formation destinations, and constrained red
tactical positions are clamped when created. Independently,
`Game.move_unit_toward` clamps every actual position after its straight-line
step. Thus even a manually assigned out-of-bounds `target_pos` cannot move a
unit beyond `WORLD_MIN` or `WORLD_MAX`.

### Shared local separation

All actual movement uses `Game.unit_separation_vector`. Living units of either
team, including kings and guards, contribute as local obstacles. Only a unit
that already has a reason to move is displaced, except that idle commandable
army units may resolve excessive overlap. Kings and guards standing at their
home posts remain fixed.

The permitted soft overlap is ignored. Beyond it, a smoothstep response blends
increasing separation velocity with preferred travel. Shallow penetration
therefore preserves strategic progress, while deep or exact overlap can
dominate. Corrections below `.02` tiles are ignored, so a negligible correction
cannot consume an update. Exact-coordinate pairs use opposite deterministic
UID-derived directions.

`Game.update` builds one spatial hash before moving any unit. The hash stores
immutable coordinate tuples as well as unit references, so every unit reads the
same pre-movement frame even though movement is applied sequentially. Direct
calls to the movement primitive rebuild the snapshot for predictable tests.

This is steering, not pathfinding. A perfectly symmetric wall can cancel every
lateral separation component and halt forward progress; selecting a detour is
intentionally reserved for the pathfinding stage.

## Reserved shared constants

The module-level movement constants use conservative values around the existing
1.15 formation/separation spacing and roughly one-tile melee range:

- separation radius: 1.15 tiles;
- permitted soft overlap: .15 tiles (1.0 tile minimum desired separation);
- neighbor-query radius: 2.3 tiles;
- blocked threshold: .75 seconds;
- pathfinding cell size: 1.0 tile;
- waypoint arrival tolerance: .12 tiles;
- path recalculation interval: .5 seconds.

The separation radius, soft overlap, and neighbor query are active. Blocked
timing, pathfinding cells, waypoints, and recalculation timing remain reserved
for the pathfinding stage.
