"""Verdant Crown: a small, code-only medieval RTS powered by pygame-ce."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

import pygame

pygame.init()
pygame.display.set_caption("Verdant Crown")

WIDTH, HEIGHT = 1280, 760
MAP_SIZE, HUD_H = 200, 126
FPS = 60
GREEN = (67, 139, 79)
RED = (164, 61, 55)
GOLD = (234, 191, 78)
CREAM = (239, 228, 194)
INK = (39, 35, 31)


def clamp(value, low, high):
    return max(low, min(high, value))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Unit:
    kind: str
    team: str
    x: float
    y: float
    health: float = field(init=False)
    max_health: float = field(init=False)
    speed: float = field(init=False)
    damage: float = field(init=False)
    cooldown: float = field(init=False)
    attack_range: float = field(init=False)
    target_pos: Optional[tuple[float, float]] = None
    target: object = None
    attack_timer: float = 0
    flash: float = 0
    selected: bool = False
    uid: int = 0

    def __post_init__(self):
        if self.kind == "swordsman":
            self.max_health, self.speed, self.damage = 100, 1, 5
            self.cooldown, self.attack_range = .5, 1.02
        else:
            self.max_health, self.speed, self.damage = 20, 2, 30
            self.cooldown, self.attack_range = 1, 5
        self.health = self.max_health


@dataclass
class Base:
    team: str
    x: float
    y: float
    health: float = 250
    max_health: float = 250
    attack_timer: float = 0
    flash: float = 0


class Button:
    def __init__(self, rect, text, sub=""):
        self.rect = pygame.Rect(rect)
        self.text, self.sub = text, sub

    def draw(self, surf, mouse, enabled=True):
        hover = self.rect.collidepoint(mouse)
        color = (88, 73, 53) if enabled else (60, 57, 53)
        if hover and enabled:
            color = (112, 91, 60)
        pygame.draw.rect(surf, (29, 27, 24), self.rect.inflate(4, 4), border_radius=9)
        pygame.draw.rect(surf, color, self.rect, border_radius=7)
        pygame.draw.rect(surf, GOLD if hover and enabled else (145, 119, 75), self.rect, 2, border_radius=7)
        font = pygame.font.Font(None, 25)
        small = pygame.font.Font(None, 18)
        text = font.render(self.text, True, CREAM if enabled else (130, 126, 116))
        if self.sub:
            text_rect = text.get_rect(topleft=(self.rect.x + 12, self.rect.y + 8))
        else:
            text_rect = text.get_rect(center=self.rect.center)
        surf.blit(text, text_rect)
        if self.sub:
            surf.blit(small.render(self.sub, True, (215, 185, 108) if enabled else (110, 105, 97)), (self.rect.x + 12, self.rect.y + 34))


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.big = pygame.font.Font(None, 72)
        self.title = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 25)
        self.small = pygame.font.Font(None, 19)
        self.state = "menu"
        self.play_btn = Button((WIDTH // 2 - 100, HEIGHT // 2 + 85, 200, 62), "Play!")
        self.reset()

    def reset(self):
        self.units: list[Unit] = []
        self.player_base = Base("green", 18, 100)
        self.enemy_base = Base("red", 177, 100)
        self.essence = 400.0
        self.enemy_essence = 500.0
        self.spawn_timer = 2.0
        self.uid = 0
        self.camera = [20.5, 100.5]
        self.zoom = 13.0
        self.explored = set()
        self.visible = set()
        self.drag_start = None
        self.drag_now = None
        self.arrows = []
        self.particles = []
        self.message = "Destroy the Crimson Hold"
        self.message_time = 4
        self.winner = None
        self.essence_tick = 0
        self.reveal_tick = 0
        self.terrain = self.make_terrain()
        self.add_unit("swordsman", "green", 24, 99)
        self.add_unit("swordsman", "green", 24, 102)
        self.add_unit("archer", "green", 26, 100.5)
        for y in (98, 100, 102):
            self.add_unit("swordsman", "red", 171, y)
        self.add_unit("archer", "red", 169, 100)

    def make_terrain(self):
        rng = random.Random(4729)
        terrain = {}
        for _ in range(900):
            x, y = rng.randrange(MAP_SIZE), rng.randrange(MAP_SIZE)
            terrain[(x, y)] = rng.choice(("grass", "grass", "flower", "stone", "scrub"))
        for x in range(5, 195):
            y = int(100 + math.sin(x / 17) * 2)
            terrain[(x, y)] = "road"
            terrain[(x, y + 1)] = "road"
        return terrain

    def add_unit(self, kind, team, x, y):
        self.uid += 1
        unit = Unit(kind, team, x, y, uid=self.uid)
        self.units.append(unit)
        return unit

    def world_to_screen(self, x, y):
        w, h = self.screen.get_size()
        return (w / 2 + (x - self.camera[0]) * self.zoom,
                (h - HUD_H) / 2 + (y - self.camera[1]) * self.zoom)

    def screen_to_world(self, pos):
        w, h = self.screen.get_size()
        return (self.camera[0] + (pos[0] - w / 2) / self.zoom,
                self.camera[1] + (pos[1] - (h - HUD_H) / 2) / self.zoom)

    def recruit(self, kind, team="green"):
        cost = 200 if kind == "swordsman" else 500
        wallet = self.essence if team == "green" else self.enemy_essence
        if wallet < cost:
            if team == "green":
                self.message, self.message_time = "Not enough essence", 1.5
            return False
        if team == "green":
            self.essence -= cost
            base, direction = self.player_base, 1
        else:
            self.enemy_essence -= cost
            base, direction = self.enemy_base, -1
        count = sum(u.team == team for u in self.units)
        y = base.y + 1.5 + (count % 4) * 1.25
        u = self.add_unit(kind, team, base.x + direction * 4, y)
        if team == "red":
            u.target_pos = (self.player_base.x, self.player_base.y)
        return True

    def select_kind(self, kind=None):
        for u in self.units:
            u.selected = u.team == "green" and (kind is None or u.kind == kind)

    def issue_order(self, world):
        selected = [u for u in self.units if u.selected and u.team == "green"]
        if not selected:
            return
        visible_enemies = [u for u in self.units if u.team == "red" and self.is_visible(u.x, u.y)]
        candidates = visible_enemies + ([self.enemy_base] if self.is_visible(self.enemy_base.x, self.enemy_base.y) else [])
        clicked = min(candidates, key=lambda e: dist((e.x, e.y), world), default=None)
        if clicked and dist((clicked.x, clicked.y), world) < 1.5:
            for u in selected:
                u.target, u.target_pos = clicked, (clicked.x, clicked.y)
            return
        cols = math.ceil(math.sqrt(len(selected)))
        for i, u in enumerate(selected):
            offset = ((i % cols - (cols - 1) / 2) * 1.15, (i // cols) * 1.15)
            u.target = None
            u.target_pos = (clamp(world[0] + offset[0], .5, 199.5), clamp(world[1] + offset[1], .5, 199.5))

    def currently_visible_enemy(self, enemy):
        return self.is_visible(enemy.x, enemy.y)

    def is_visible(self, x, y):
        return (int(x), int(y)) in self.visible

    def update_visibility(self):
        self.visible.clear()
        sources = [(self.player_base.x, self.player_base.y, 12)]
        sources += [(u.x, u.y, 8) for u in self.units if u.team == "green"]
        for sx, sy, radius in sources:
            for x in range(max(0, int(sx - radius)), min(MAP_SIZE, int(sx + radius) + 1)):
                for y in range(max(0, int(sy - radius)), min(MAP_SIZE, int(sy + radius) + 1)):
                    if (x - sx) ** 2 + (y - sy) ** 2 <= radius ** 2:
                        self.visible.add((x, y))
        self.explored.update(self.visible)

    def find_target(self, unit):
        opponents = [u for u in self.units if u.team != unit.team and u.health > 0]
        enemy_base = self.enemy_base if unit.team == "green" else self.player_base
        if unit.team == "green":
            opponents = [u for u in opponents if self.currently_visible_enemy(u)]
        in_range = [e for e in opponents if dist((unit.x, unit.y), (e.x, e.y)) <= unit.attack_range]
        if dist((unit.x, unit.y), (enemy_base.x, enemy_base.y)) <= unit.attack_range + 2.5:
            in_range.append(enemy_base)
        return min(in_range, key=lambda e: dist((unit.x, unit.y), (e.x, e.y)), default=None)

    def attack(self, attacker, target):
        target.health -= attacker.damage
        target.flash = .12
        attacker.attack_timer = attacker.cooldown
        if attacker.kind == "archer":
            self.arrows.append([attacker.x, attacker.y, target.x, target.y, .22, attacker.team])
        else:
            mx, my = (attacker.x + target.x) / 2, (attacker.y + target.y) / 2
            self.particles.append([mx, my, .25, attacker.team])

    def update_unit(self, u, dt):
        u.attack_timer = max(0, u.attack_timer - dt)
        u.flash = max(0, u.flash - dt)
        target = u.target
        if target is not None and getattr(target, "health", 0) <= 0:
            u.target = target = None
        auto = self.find_target(u)
        if auto is not None:
            target = auto
            u.target = auto
        if target is not None:
            target_range = u.attack_range + (2.3 if isinstance(target, Base) else 0)
            d = dist((u.x, u.y), (target.x, target.y))
            if d <= target_range:
                if u.attack_timer <= 0:
                    self.attack(u, target)
                return
            u.target_pos = (target.x, target.y)
        if u.target_pos:
            dx, dy = u.target_pos[0] - u.x, u.target_pos[1] - u.y
            d = math.hypot(dx, dy)
            if d < .08:
                u.target_pos = None
            else:
                step = min(d, u.speed * dt)
                u.x = clamp(u.x + dx / d * step, .5, 199.5)
                u.y = clamp(u.y + dy / d * step, .5, 199.5)

    def update(self, dt):
        if self.state != "playing" or self.winner:
            return
        self.message_time = max(0, self.message_time - dt)
        self.essence += 20 * dt
        self.enemy_essence += 20 * dt
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            kind = "archer" if self.enemy_essence >= 500 and random.random() < .4 else "swordsman"
            self.recruit(kind, "red")
            self.spawn_timer = random.uniform(5.5, 8.5)
        for u in list(self.units):
            self.update_unit(u, dt)
            if u.team == "red" and not u.target and not u.target_pos:
                u.target_pos = (self.player_base.x, self.player_base.y + random.uniform(-2, 2))
        self.units[:] = [u for u in self.units if u.health > 0]
        for a in self.arrows:
            a[4] -= dt
        self.arrows[:] = [a for a in self.arrows if a[4] > 0]
        for p in self.particles:
            p[2] -= dt
        self.particles[:] = [p for p in self.particles if p[2] > 0]
        self.reveal_tick -= dt
        if self.reveal_tick <= 0:
            self.update_visibility()
            self.reveal_tick = .12
        if self.enemy_base.health <= 0:
            self.winner = "VICTORY"
        elif self.player_base.health <= 0:
            self.winner = "DEFEAT"

    def draw_terrain(self):
        w, h = self.screen.get_size()
        view_h = h - HUD_H
        self.screen.fill((70, 101, 55))
        left, top = self.screen_to_world((0, 0))
        right, bottom = self.screen_to_world((w, view_h))
        x0, x1 = max(0, int(left) - 1), min(MAP_SIZE, int(right) + 2)
        y0, y1 = max(0, int(top) - 1), min(MAP_SIZE, int(bottom) + 2)
        tile = max(1, int(self.zoom + 1))
        for x in range(x0, x1):
            for y in range(y0, y1):
                sx, sy = self.world_to_screen(x, y)
                tone = 2 if (x * 13 + y * 7) % 5 else -2
                color = (76 + tone, 109 + tone, 60 + tone)
                kind = self.terrain.get((x, y))
                if kind == "road": color = (137, 118, 77)
                pygame.draw.rect(self.screen, color, (int(sx), int(sy), tile, tile))
                if self.zoom >= 10 and kind in ("flower", "stone", "scrub"):
                    cx, cy = int(sx + self.zoom * .5), int(sy + self.zoom * .5)
                    c = {"flower": (219, 202, 105), "stone": (101, 103, 91), "scrub": (48, 82, 43)}[kind]
                    pygame.draw.circle(self.screen, c, (cx, cy), max(1, int(self.zoom * .12)))
        border = self.world_to_screen(0, 0)
        pygame.draw.rect(self.screen, (39, 54, 35), (border[0], border[1], MAP_SIZE * self.zoom, MAP_SIZE * self.zoom), max(2, int(self.zoom * .15)))

    def draw_base(self, base):
        if base.team == "red" and not self.is_visible(base.x, base.y):
            return
        color = GREEN if base.team == "green" else RED
        sx, sy = self.world_to_screen(base.x - 2.5, base.y - 2.5)
        size = 5 * self.zoom
        r = pygame.Rect(int(sx), int(sy), int(size), int(size))
        pygame.draw.rect(self.screen, (43, 39, 34), r, border_radius=max(2, int(self.zoom * .25)))
        inset = r.inflate(-int(self.zoom * .7), -int(self.zoom * .7))
        pygame.draw.rect(self.screen, color if base.flash <= 0 else CREAM, inset, border_radius=3)
        # Corner towers and keep roof.
        for px, py in ((r.left, r.top), (r.right, r.top), (r.left, r.bottom), (r.right, r.bottom)):
            pygame.draw.circle(self.screen, (67, 63, 54), (px, py), max(3, int(self.zoom * .42)))
        roof = [(r.centerx, r.top + int(size * .16)), (r.left + int(size * .22), r.centery), (r.right - int(size * .22), r.centery)]
        pygame.draw.polygon(self.screen, (39, 76, 45) if base.team == "green" else (105, 38, 34), roof)
        # Health bar.
        bar = pygame.Rect(r.left, r.top - 10, r.width, 6)
        pygame.draw.rect(self.screen, (42, 32, 31), bar, border_radius=3)
        fill = bar.copy(); fill.width = int(bar.width * max(0, base.health / base.max_health))
        pygame.draw.rect(self.screen, color, fill, border_radius=3)

    def draw_cracks(self, rect, ratio, seed):
        if ratio > .78:
            return
        random.seed(seed)
        stages = 1 if ratio > .5 else 2 if ratio > .25 else 3
        cx, cy = rect.center
        for branch in range(stages * 3):
            angle = random.random() * math.tau
            length = rect.width * (.18 + .09 * stages) * random.uniform(.7, 1.1)
            ex, ey = cx + math.cos(angle) * length, cy + math.sin(angle) * length
            pygame.draw.line(self.screen, (38, 31, 27), (cx, cy), (ex, ey), max(1, rect.width // 13))
            if stages > 1:
                bx, by = (cx + ex) / 2, (cy + ey) / 2
                pygame.draw.line(self.screen, (38, 31, 27), (bx, by), (bx + math.cos(angle + 1) * length * .35, by + math.sin(angle + 1) * length * .35), max(1, rect.width // 16))

    def draw_unit(self, u):
        if u.team == "red" and not self.is_visible(u.x, u.y):
            return
        sx, sy = self.world_to_screen(u.x - .5, u.y - .5)
        size = max(5, int(self.zoom))
        rect = pygame.Rect(int(sx), int(sy), size, size)
        color = GREEN if u.team == "green" else RED
        if u.flash > 0: color = CREAM
        if u.selected:
            pygame.draw.circle(self.screen, GOLD, rect.center, int(size * .68), max(1, size // 9))
        pygame.draw.rect(self.screen, (32, 31, 28), rect.inflate(2, 2), border_radius=max(2, size // 4))
        pygame.draw.rect(self.screen, color, rect, border_radius=max(2, size // 4))
        if u.kind == "swordsman":
            pygame.draw.line(self.screen, (225, 223, 202), (rect.left + size * .28, rect.bottom - size * .2), (rect.right - size * .2, rect.top + size * .2), max(1, size // 7))
            pygame.draw.line(self.screen, (92, 65, 39), (rect.left + size * .2, rect.centery), (rect.centerx, rect.bottom - size * .2), max(1, size // 8))
        else:
            arc = pygame.Rect(rect.left + size * .18, rect.top + size * .14, size * .58, size * .72)
            pygame.draw.arc(self.screen, (109, 67, 35), arc, -math.pi / 2, math.pi / 2, max(1, size // 7))
            pygame.draw.line(self.screen, CREAM, (arc.centerx, arc.top), (arc.centerx, arc.bottom), max(1, size // 11))
        self.draw_cracks(rect, u.health / u.max_health, u.uid)

    def draw_effects(self):
        for x1, y1, x2, y2, life, team in self.arrows:
            t = 1 - life / .22
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            sx, sy = self.world_to_screen(x, y)
            pygame.draw.circle(self.screen, GOLD, (int(sx), int(sy)), max(2, int(self.zoom * .13)))
        for x, y, life, team in self.particles:
            sx, sy = self.world_to_screen(x, y)
            radius = max(2, int(self.zoom * (1 - life / .25) * .4))
            pygame.draw.circle(self.screen, CREAM, (int(sx), int(sy)), radius, 1)

    def draw_fog(self):
        w, h = self.screen.get_size(); view_h = h - HUD_H
        fog = pygame.Surface((w, view_h), pygame.SRCALPHA)
        left, top = self.screen_to_world((0, 0)); right, bottom = self.screen_to_world((w, view_h))
        for x in range(max(0, int(left) - 1), min(MAP_SIZE, int(right) + 2)):
            for y in range(max(0, int(top) - 1), min(MAP_SIZE, int(bottom) + 2)):
                if (x, y) in self.visible: continue
                sx, sy = self.world_to_screen(x, y)
                alpha = 145 if (x, y) in self.explored else 235
                pygame.draw.rect(fog, (15, 20, 18, alpha), (int(sx), int(sy), int(self.zoom + 1), int(self.zoom + 1)))
        self.screen.blit(fog, (0, 0))

    def draw_hud(self):
        w, h = self.screen.get_size(); top = h - HUD_H
        pygame.draw.rect(self.screen, (34, 31, 27), (0, top, w, HUD_H))
        pygame.draw.line(self.screen, (129, 102, 62), (0, top), (w, top), 3)
        pygame.draw.circle(self.screen, (92, 188, 205), (34, top + 29), 12)
        self.screen.blit(self.font.render(f"{int(self.essence):,} essence", True, CREAM), (55, top + 18))
        self.screen.blit(self.small.render("+20 each second", True, (172, 158, 128)), (55, top + 44))
        sword_btn = Button((245, top + 16, 180, 62), "Raise Swordsman", "200 essence  •  [S]")
        archer_btn = Button((440, top + 16, 180, 62), "Raise Archer", "500 essence  •  [A]")
        sword_btn.draw(self.screen, pygame.mouse.get_pos(), self.essence >= 200)
        archer_btn.draw(self.screen, pygame.mouse.get_pos(), self.essence >= 500)
        self.hud_buttons = [(sword_btn, "swordsman"), (archer_btn, "archer")]
        counts = {k: sum(u.team == "green" and u.kind == k for u in self.units) for k in ("swordsman", "archer")}
        selected = sum(u.selected for u in self.units)
        info = f"Army: {counts['swordsman']} swordsmen  •  {counts['archer']} archers  •  {selected} selected"
        self.screen.blit(self.small.render(info, True, (190, 180, 153)), (245, top + 90))
        controls = "[1] All swords   [2] All archers   [3] All army   •   Right-click: order"
        label = self.small.render(controls, True, (165, 155, 132))
        self.screen.blit(label, (w - label.get_width() - 20, top + 94))
        # Base vitality at right.
        self.screen.blit(self.small.render("VERDANT KEEP", True, (165, 198, 165)), (w - 210, top + 18))
        self.screen.blit(self.font.render(f"{max(0, int(self.player_base.health))} / 250", True, CREAM), (w - 210, top + 39))

    def draw_menu(self):
        w, h = self.screen.get_size()
        self.screen.fill((27, 42, 31))
        # Decorative banner and sword field.
        for i in range(70):
            random.seed(i)
            x, y = random.randrange(w), random.randrange(h)
            pygame.draw.circle(self.screen, (42, 67, 45), (x, y), random.randrange(1, 4))
        banner = pygame.Rect(w // 2 - 310, 100, 620, 310)
        pygame.draw.rect(self.screen, (45, 40, 33), banner, border_radius=20)
        pygame.draw.rect(self.screen, (150, 119, 67), banner, 4, border_radius=20)
        title = self.big.render("VERDANT CROWN", True, CREAM)
        self.screen.blit(title, (w // 2 - title.get_width() // 2, 155))
        sub = self.title.render("A MEDIEVAL RTS", True, GOLD)
        self.screen.blit(sub, (w // 2 - sub.get_width() // 2, 225))
        lore = self.font.render("Raise your banners. Break the Crimson Hold.", True, (191, 181, 152))
        self.screen.blit(lore, (w // 2 - lore.get_width() // 2, 294))
        self.play_btn.rect.center = (w // 2, h // 2 + 110)
        self.play_btn.draw(self.screen, pygame.mouse.get_pos())
        hint = self.small.render("Mouse + keyboard  •  Press Play to begin", True, (145, 157, 137))
        self.screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 80))

    def draw_game(self):
        self.draw_terrain()
        self.draw_base(self.player_base); self.draw_base(self.enemy_base)
        for u in self.units: self.draw_unit(u)
        self.draw_effects(); self.draw_fog()
        if self.drag_start and self.drag_now:
            rect = pygame.Rect(self.drag_start, (self.drag_now[0] - self.drag_start[0], self.drag_now[1] - self.drag_start[1])); rect.normalize()
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA); overlay.fill((102, 192, 112, 45)); self.screen.blit(overlay, rect)
            pygame.draw.rect(self.screen, (134, 211, 142), rect, 1)
        self.draw_hud()
        if self.message_time > 0:
            label = self.font.render(self.message, True, CREAM)
            box = label.get_rect(center=(self.screen.get_width() // 2, 34)).inflate(28, 16)
            pygame.draw.rect(self.screen, (28, 27, 24), box, border_radius=8)
            self.screen.blit(label, label.get_rect(center=box.center))
        if self.winner:
            shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA); shade.fill((12, 14, 12, 190)); self.screen.blit(shade, (0, 0))
            color = GOLD if self.winner == "VICTORY" else (213, 91, 78)
            label = self.big.render(self.winner, True, color)
            self.screen.blit(label, label.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 25)))
            sub = self.font.render("Press R to fight again  •  Esc for menu", True, CREAM)
            self.screen.blit(sub, sub.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 35)))

    def camera_input(self, dt):
        keys = pygame.key.get_pressed(); mx, my = pygame.mouse.get_pos(); w, h = self.screen.get_size()
        speed = 25 * dt * (13 / self.zoom)
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT] or mx > w - 5) - (keys[pygame.K_a] or keys[pygame.K_LEFT] or mx < 5)
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN] or my > h - HUD_H - 5) - (keys[pygame.K_w] or keys[pygame.K_UP] or my < 5)
        self.camera[0] = clamp(self.camera[0] + dx * speed, 0, MAP_SIZE)
        self.camera[1] = clamp(self.camera[1] + dy * speed, 0, MAP_SIZE)

    def handle_game_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1: self.select_kind("swordsman")
            elif event.key == pygame.K_2: self.select_kind("archer")
            elif event.key == pygame.K_3: self.select_kind()
            elif event.key == pygame.K_s: self.recruit("swordsman")
            elif event.key == pygame.K_a: self.recruit("archer")
            elif event.key == pygame.K_SPACE: self.camera[:] = [self.player_base.x, self.player_base.y]
            elif event.key == pygame.K_r and self.winner: self.reset()
            elif event.key == pygame.K_ESCAPE: self.state = "menu"
        elif event.type == pygame.MOUSEWHEEL:
            old_world = self.screen_to_world(pygame.mouse.get_pos())
            self.zoom = clamp(self.zoom * (1.13 ** event.y), 5, 30)
            new_world = self.screen_to_world(pygame.mouse.get_pos())
            self.camera[0] += old_world[0] - new_world[0]; self.camera[1] += old_world[1] - new_world[1]
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                for button, kind in getattr(self, "hud_buttons", []):
                    if button.rect.collidepoint(event.pos): self.recruit(kind); return
                if event.pos[1] < self.screen.get_height() - HUD_H:
                    self.drag_start = self.drag_now = event.pos
            elif event.button == 3 and event.pos[1] < self.screen.get_height() - HUD_H:
                self.issue_order(self.screen_to_world(event.pos))
        elif event.type == pygame.MOUSEMOTION and self.drag_start:
            self.drag_now = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag_start:
            rect = pygame.Rect(self.drag_start, (event.pos[0] - self.drag_start[0], event.pos[1] - self.drag_start[1])); rect.normalize()
            additive = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if not additive:
                for u in self.units: u.selected = False
            if rect.width < 6 and rect.height < 6:
                world = self.screen_to_world(event.pos)
                friends = [u for u in self.units if u.team == "green"]
                hit = min(friends, key=lambda u: dist((u.x, u.y), world), default=None)
                if hit and dist((hit.x, hit.y), world) < .9: hit.selected = True
            else:
                for u in self.units:
                    if u.team == "green" and rect.collidepoint(self.world_to_screen(u.x, u.y)): u.selected = True
            self.drag_start = self.drag_now = None

    def run(self):
        running = True
        while running:
            dt = min(.05, self.clock.tick(FPS) / 1000)
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                elif self.state == "menu":
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.play_btn.rect.collidepoint(event.pos):
                        self.reset(); self.state = "playing"; self.update_visibility()
                    elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.reset(); self.state = "playing"; self.update_visibility()
                else: self.handle_game_event(event)
            if self.state == "playing":
                self.camera_input(dt); self.update(dt); self.draw_game()
            else: self.draw_menu()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
