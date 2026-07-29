# Verdant Crown

A compact, self-contained medieval RTS built with Python and pygame-ce. Keep
the green Verdant King alive, raise swordsmen, archers, and shields, and kill
the red Crimson King across a 120 x 120 tile battlefield.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

## Controls

- **Left click** a friendly unit to select it; drag a box to select several.
- **Right click** issues a move/attack-move order.
- **1 / 2 / 4** select every swordsman / archer / shield. **3** selects all units.
- **WASD**, arrow keys, or moving the mouse to a screen edge pans the camera.
- **Mouse wheel** zooms. **Space** jumps back to the Verdant King.
- Click the unit cards to spend essence and recruit units. **S / A / Q** recruits a swordsman / archer / shield.
- **Esc** pauses; **R** restarts after victory or defeat.

Fog is explored permanently, but only currently visible enemies can be seen.
Friendly army units reveal 8 tiles and the Verdant King reveals 12. The HUD
shows only your king's health; the hidden Crimson King's health is never
revealed. Kill the Crimson King to win. If the Verdant King dies, you lose.

## Enemy production tuning

Before seeing a player army, enemy recruitment aims to invest one third of its
army essence in each unit kind. After a sighting, it totals the last-seen
living player units by their recruitment costs and maps those essence shares
through the counters: swordsmen produce an archer target, archers a shield
target, and shields a swordsman target.

Each deterministic decision projects the cost of every possible next unit and
chooses the purchase with the smallest total error from those target essence
shares. Unit-kind order breaks exact ties, avoiding rapid boundary oscillation;
long sequences are expected to fall within a three-percentage-point rounding
tolerance. The AI saves when its preferred counter is not yet affordable.
Unavailable kinds are omitted, and a serious close-range defense may buy the
best affordable emergency alternative.

## Enemy casualty retreat precedence

Enemy attack-wave decisions use this order:

1. Hard-safety rules end the attack first, including no viable combat units or no valid and reachable objective.
2. A casualty-triggered retreat is overridden only by a current assessment (no older than the evaluator's one-second refresh interval), using non-stale opponent intelligence, when the enemy's measured combat-strength ratio is strictly greater than `EnemyAI.CASUALTY_ADVANTAGE_MARGIN` (currently `1.5`). Casualty changes invalidate the assessment cache and force immediate reevaluation.
3. A weaker assessment causes retreat.
4. Missing, uncertain, or stale evidence uses the conservative fallback: a casualty-hit attacker retreats (and an already recovering group remains at its rally point).

The override is limited to the casualty trigger; defense recalls and all other retreat or termination rules retain their normal behavior.
