# Verdant Crown

A compact, self-contained medieval RTS built with Python and pygame-ce. Defend the green Verdant Keep, raise swordsmen and archers, and destroy the red Crimson Hold across a 200 x 200 tile battlefield.

## Run

```bash
python -m pip install -r requirements.txt
python main.py
```

## Controls

- **Left click** a friendly unit to select it; drag a box to select several.
- **Right click** issues a move/attack-move order.
- **1 / 2** select every swordsman / archer. **3** selects all units.
- **WASD**, arrow keys, or moving the mouse to a screen edge pans the camera.
- **Mouse wheel** zooms. **Space** jumps back to the Verdant Keep.
- Click the unit cards to spend essence and recruit units.
- **Esc** pauses; **R** restarts after victory or defeat.

Fog is explored permanently, but only currently visible enemies can be seen. Friendly units reveal 8 tiles and the keep reveals 12.
