import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main
from main import Game, HUD_H, TERRAIN_KINDS, TerrainCell


class TerrainRenderTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(terrain_seed=901)
        self.game.reset(3)
        self.game.visible = set(self.game.terrain)

    def test_every_kind_and_variation_has_a_valid_drawing_path(self):
        surfaces = {}
        for kind in TERRAIN_KINDS:
            for variation in range(4):
                with self.subTest(kind=kind, variation=variation):
                    surface = self.game.terrain_tile_surface(
                        kind, variation, (24, 24)
                    )
                    self.assertEqual(surface.get_size(), (24, 24))
                    surfaces[(kind, variation)] = pygame.image.tobytes(
                        surface, "RGB"
                    )
        for kind in TERRAIN_KINDS:
            self.assertEqual(
                len({surfaces[(kind, variation)] for variation in range(4)}),
                4,
            )

    def test_minimum_and_maximum_zoom_render_at_multiple_window_sizes(self):
        for size in ((640, 480), (900, 600), (1280, 720)):
            self.game.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
            fit_zoom = max(
                size[0] / main.MAP_SIZE,
                (size[1] - HUD_H) / main.MAP_SIZE,
            )
            for zoom in (fit_zoom, 30):
                with self.subTest(size=size, zoom=zoom):
                    self.game.zoom = zoom
                    self.game.clamp_camera()
                    self.game.draw_terrain()

    def test_fixed_view_has_deterministic_pixels_and_no_state_mutation(self):
        self.game.screen = pygame.display.set_mode((800, 560), pygame.RESIZABLE)
        self.game.zoom = 13
        self.game.camera[:] = [60, 60]
        terrain_before = dict(self.game.terrain)
        random.seed(4821)
        random_before = random.getstate()
        self.game.screen.fill((255, 0, 255))
        self.game.draw_terrain()
        first = pygame.image.tobytes(self.game.screen, "RGB")
        self.game.screen.fill((255, 0, 255))
        self.game.draw_terrain()
        second = pygame.image.tobytes(self.game.screen, "RGB")
        self.assertEqual(first, second)
        self.assertEqual(self.game.terrain, terrain_before)
        self.assertEqual(random.getstate(), random_before)

    def test_cache_reuse_and_reset_invalidation(self):
        first = self.game.terrain_tile_surface("forest", 2, (13, 13))
        second = self.game.terrain_tile_surface("forest", 2, (13, 13))
        self.assertIs(first, second)
        self.game._terrain_tile_cache[("sentinel",)] = first
        self.game.reset(3)
        self.assertNotIn(("sentinel",), self.game._terrain_tile_cache)
        replacement = self.game.terrain_tile_surface("forest", 2, (13, 13))
        self.assertIsNot(first, replacement)

    def test_detail_mode_follows_zoom_not_rounded_tile_dimensions(self):
        self.game.screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        self.game.zoom = main.TERRAIN_DETAIL_MIN_ZOOM - .25
        self.game.camera[:] = [60, 60]
        self.game.draw_terrain()
        detail_modes = {key[-1] for key in self.game._terrain_tile_cache}
        self.assertEqual(detail_modes, {False})

    def test_draw_terrain_does_not_touch_hud_region(self):
        self.game.screen = pygame.display.set_mode((700, 500), pygame.RESIZABLE)
        hud_top = self.game.screen.get_height() - HUD_H
        sentinel = (241, 7, 193)
        self.game.screen.fill(sentinel)
        self.game.draw_terrain()
        for point in ((0, hud_top), (350, hud_top + 20), (699, 499)):
            self.assertEqual(self.game.screen.get_at(point)[:3], sentinel)

    def test_variation_does_not_change_gameplay_cell_identity(self):
        for kind in TERRAIN_KINDS:
            multipliers = {
                main.terrain_movement_multiplier(TerrainCell(kind, v).kind)
                for v in range(4)
            }
            self.assertEqual(len(multipliers), 1)


if __name__ == "__main__":
    unittest.main()
