# Verdant Crown

A compact, self-contained medieval RTS built with Python and pygame-ce. Keep
the green Verdant King alive, raise swordsmen, archers, and shields, and kill
the red Crimson King across five battlefields.

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

The level selector shows one battlefield at a time. Use **Left / Right** or the
Previous/Next buttons to browse, **1–5** to jump directly to a level, and
**Enter** to play the selected page. Page dots are clickable, **Esc** returns to
the title, and the last selected page is remembered after the first visit.
On levels three through five, use **H** or the opponent-AI button to switch
between Standard and Hard mode. Hard mode uses a player-style strategic
controller that recruits toward deliberate army compositions, rallies before
attacking, defends its king, keeps reserves, captures holds, and uses flanking
routes where appropriate.
Level five is presented only as the large, clickable title **Last Stand**;
its ordinary selector details and controls are intentionally hidden.

## Level editor

Choose **Level Editor** on the title screen to build and play a custom battle.
The editor opens with an expanded 200×200 map and supports 60×60, 120×120,
160×160, 200×200, and 240×240 battlefields.

- **Paint** plains, forests, mountains, and fast roads directly on the map.
  Place or remove up to 12 holds, and click new Verdant and Crimson starting
  positions.
- **Randomize** generates new terrain, roads, holds, and starting positions
  while preserving economy, fog, and army settings. Its sliders control map
  size, hold count, the percentage of holds connected to roads, path amount,
  and the relative plains, forest, and mountain ratios.
- **Settings** changes map size, Verdant and Crimson income, and whether fog of
  war is enabled for the custom level. It also selects Standard or Hard enemy
  AI, and that choice is stored with the saved custom battlefield.
- **Armies** chooses the player-recruitable unit roster and the starting unit
  counts for both sides.
- **Save** writes `custom_level.json`; it is loaded automatically the next time
  the game starts. **Play** immediately launches the current draft, while
  **Reset** restores the expanded starter battlefield.

In custom battles, the Crimson AI targets the nearest uncaptured hold. After
capturing it, 15 survivors stay behind as a garrison while every surplus unit
joins the force assembling to attack the next-nearest hold. The Crimson King
also keeps a permanent 10-unit home garrison, replenished before new attacks.

Fog is explored permanently, but only currently visible enemies can be seen.
Friendly army units have a sight budget of 8 and the Verdant King has 16. The HUD
shows only your king's health; the hidden Crimson King's health is never
revealed. Sight follows a straight grid ray and spends that radius as a budget:
crossing a mountain tile costs `0.75`, plains and path tiles cost `1`, and a
forest tile costs `5`. The same terrain sight rules apply to enemy observers.
Red combat vision is shared across the enemy team, but hidden player positions
are not tracked live; enemies retain only the last position their team saw.
Kill the Crimson King to win. If the Verdant King dies, you lose.

Terrain also affects combat. Archers standing on mountains automatically gain
`+1` attack range and deal `20%` more damage to targets on any non-mountain
terrain. Units in forests take `30%` less ranged damage. Units on paths take
`20%` more damage from every attack, while plains have no combat modifier.

When either king reaches half health, he immediately abandons combat and
returns to his starting position. Nearby enemies cannot interrupt this return;
once home, the king heals and may attack or chase only inside a seven-tile
perimeter. His normal engagement range returns at full health.

## Unit navigation

Move orders assign stable formation slots. Units normally travel directly
toward those slots while a shared local separation force gently resolves
crowding for both armies. A slight overlap is intentional: units behave as
soft obstacles, which keeps formations and congested melee groups moving
without producing rigid gaps or constant jitter.

Ground orders are attack-move orders. Player units engage visible enemies that
come within five tiles, then resume their formation destinations when the fight
ends or the target escapes.

Every map cell is traversable terrain. Mountains are rugged gray ground and
halve movement speed (`0.5x`); forests are dense green ground and slow movement
to `0.75x`; golden paths double movement speed (`2.0x`); and open plains use the
normal speed (`1.0x`). Levels two through five generate a fresh asymmetric mix of
large terrain regions and a branching road network whenever a level is begun.
Across generated maps, ordinary terrain averages one third plains, one third
forest, and one third mountain, excluding roads and protected starting zones.
Restarting after a result preserves that battlefield for a fair retry, while
king, guard, and recruitment areas always remain plains. Level one stays a
fixed all-plains tutorial. Visual variations within each terrain kind are
cosmetic and never affect gameplay.

Level four expands the war to a 160×160 battlefield with three ancient
checkpoints. A dwarven mountain hold, elven forest hold, and orc plains hold
each begin with five native defenders, add one defender every 30 seconds while
native-owned, and cap at 15. On reaching 15, a hold sends 10 troops to raid the
nearest other native hold or living king, then rebuilds from the five left
behind. Clear a hold and keep troops uncontested beside it
for five seconds to capture it. Green begins at 10 gold per second, red at 15,
and every checkpoint adds 5 gold per second to its current green or red owner.
Checkpoints placed in a custom level instead add 10 gold per second.
An owned hold also reveals a fixed 12-tile circle through all terrain and heals
friendly purchasable army units within four tiles at 1 health per second. Kings,
royal guards, and native troops cannot receive this healing.

The moment a hostile green or red army unit enters the 2.5-tile capture circle,
the hold is under attack: its income and healing stop immediately, even before
capture progress begins. Its owner keeps the 12-tile vision until ownership
actually changes. Captured holds remain vulnerable to recapture, while their
native production changes allegiance after a main-faction capture. A captured
hold raises one troop from its native roster for its Verdant or Crimson owner
every 45 seconds, up to five living troops for that owner. Fallen troops can be
replaced while the hold remains owned.

Level five uses the same 160×160 generation and rules, retaining those three
holds and adding one large hold near each northern/southern edge. A seeded shuffle assigns
the demon and frost-giant factions to the top and bottom. Each large hold starts
with six melee and four ranged defenders, produces every 10 seconds, and can hold
100 defenders. On reaching 70, it sends 50 troops toward the opposite large hold,
falling back to the nearest living king if that hold is no longer native-owned.
Its capture circle is five tiles, defender leash and vision are 24 tiles, and
healing reaches eight tiles. In Level 5, small holds grant 10 gold per second,
large holds grant 20, and Crimson begins with 30 gold per second. Capture time
and healing rate remain unchanged. Crimson attack waves require at least 20
units throughout the level.

Holds are initially unknown. The first time a hold cell enters Verdant vision,
it is discovered permanently; its location and live ownership then remain known.
Level four's top objective bar shows `?` for unknown holds and owner, income,
contest, capture, and progress information for discovered holds. Click a known
entry to center the camera. Visible holds have world-space status labels, and
discovered off-screen holds have directional edge markers. Capture, loss,
contest, and income-restoration alerts appear below the objective bar.

Each native troop has an automatic faction passive:

- **Dwarf Guard:** takes 30% less ranged damage.
- **Dwarf Arbalist:** braces after one stationary second, reducing all damage by
  25% until it moves.
- **Elf Bladedancer:** ignores forest movement slowing.
- **Elf Ranger:** kites toward a 5.5-tile preferred distance and can fire after
  moving, within its current defense or raid leash.
- **Orc Cleaver:** splashes 50% damage to the nearest second enemy within 1.25
  tiles of its target.
- **Orc Spear Thrower:** deals 35% more damage while below half health.
- **Demon Reaver:** heals itself for 50% of the damage it deals.
- **Infernal Warlock:** splashes half damage to the three nearest secondary
  enemies within 1.5 tiles.
- **Frost Colossus:** applies a 40% movement slow for two seconds.
- **Ice Hurler:** applies a 30% two-second movement slow and splashes half damage
  to the three nearest secondary enemies within 1.75 tiles.

Stationary units can trigger grid-based A* detours when a direct route is
blocked or movement has stalled. Moving troops use combat engagement and local
separation instead of being treated as static walls. Paths are cached, refreshed
when their corridor changes, and invalidated immediately by a new destination
or combat target. Routing compares travel time rather than geometric distance,
so a longer path across faster terrain can be preferred. All movement and
waypoints are clamped to the map.

Run the integrated 100-unit update/render benchmark with
`python3 simulate_performance.py --integrated --assert-60fps`.

## Enemy production tuning

Normal AI attack groups require at least 6,000 essence of purchasable units.
Composition percentages are percentages of recruitment cost. The initial
production target is 20% swordsmen, 30% shields, and 50% archers.

Seeing a player army does not by itself change production. The AI learns a
counter composition only from a player army that defeats an AI attack wave. A
player army that loses does not change the current production target. A learned
composition maps the victorious army's essence shares through the counters:
swordsmen produce an archer target, archers a shield target, and shields a
swordsman target.

Each deterministic decision projects the cost of every possible next unit and
chooses the purchase with the smallest total error from those target essence
shares. Unit-kind order breaks exact ties, avoiding rapid boundary oscillation;
long sequences are expected to fall within a three-percentage-point rounding
tolerance. The AI saves when its preferred counter is not yet affordable.
Unavailable kinds are omitted, and a serious close-range defense may buy the
best affordable emergency alternative.

For a native hold, the AI temporarily uses faction-specific essence
targets while building and rallying: dwarf assaults use 50% archers / 30%
swordsmen / 20% shields; elf assaults use 55% shields / 30% swordsmen / 15%
archers; and orc assaults strongly favor 70% archers / 20% shields / 10%
swordsmen, including while the attack is underway. Once that target changes
ownership, learned or standard production resumes.

Checkpoint launch authorization follows a cached terrain-fastest route from the
rally point. Its ETA uses the slowest squad member and projects every native
spawn due before arrival, up to the 15-defender cap. A wave still needs at least
15 units and 1.35× projected defender strength; waiting out the formation
timer never bypasses that strength requirement. During travel, a shared route
anchor advances at the slowest member's speed only while at least 75% of the
squad remains within formation tolerance.

Checkpoint strength also rewards ranged formations: each ranged unit gains 10%
effective strength per ranged ally within four tiles, with no maximum bonus.

## Enemy casualty retreat precedence

Enemy attack-wave decisions use this order:

1. Hard-safety rules end the attack first, including no viable combat units or no valid and reachable objective.
2. Once any living attack-squad member is within 20 tiles of the Verdant King, the wave remains committed and cannot take a casualty- or strength-triggered retreat.
3. A casualty-triggered retreat is otherwise overridden only by a current assessment (no older than the evaluator's one-second refresh interval), using non-stale opponent intelligence, when the enemy's measured combat-strength ratio is strictly greater than `EnemyAI.CASUALTY_ADVANTAGE_MARGIN` (currently `1.5`). Casualty changes invalidate the assessment cache and force immediate reevaluation.
4. A weaker assessment causes retreat.
5. Missing, uncertain, or stale evidence uses the conservative fallback: a casualty-hit attacker retreats (and an already recovering group remains at its rally point).

The strong-evidence override is limited to the casualty trigger. The 20-tile commitment rule blocks both casualty and strength retreats, but defense recalls and hard-safety termination rules retain their normal behavior.
