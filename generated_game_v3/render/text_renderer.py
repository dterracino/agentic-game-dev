"""CPU-rasterized text rendering support for the renderer.

This module uses pygame's font rendering (pygame.font) to rasterize text
to a Surface, then uploads the resulting RGBA pixels as a moderngl texture
which is drawn as a single textured quad. This keeps the dependency
footprint limited to pygame + moderngl (both already declared project
dependencies) and avoids bundling any external font asset files -- the
default pygame system font is used.

This module is part of the render layer: it consumes only primitive
strings/positions/colors, never gamelib or state objects, matching the
layering rules used by renderer.py, line_batch.py, and polygon_mesh.py.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import moderngl
import pygame

Color = Tuple[float, float, float, float]

_TEXT_VERTEX_SRC = """
#version 330

in vec2 in_position;
in vec2 in_uv;

uniform vec2 u_resolution;

out vec2 v_uv;

void main() {
    vec2 zero_to_one = in_position / u_resolution;
    vec2 zero_to_two = zero_to_one * 2.0;
    vec2 clip_space = zero_to_two - 1.0;
    gl_Position = vec4(clip_space.x, -clip_space.y, 0.0, 1.0);
    v_uv = in_uv;
}
"""

_TEXT_FRAGMENT_SRC = """
#version 330

in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec4 u_tint;

out vec4 fragColor;

void main() {
    vec4 sampled = texture(u_tex, v_uv);
    fragColor = vec4(u_tint.rgb, u_tint.a * sampled.a);
}
"""


class TextRenderer:
    """Rasterizes strings via pygame.font and draws them as textured quads.

    A small cache of (text, size) -> moderngl.Texture avoids re-rasterizing
    and re-uploading unchanged strings every frame.
    """

    def __init__(self, ctx: moderngl.Context, window_size: Tuple[int, int]) -> None:
        self._ctx = ctx
        self._window_size = window_size

        if not pygame.font.get_init():
            pygame.font.init()

        self._fonts: Dict[int, "pygame.font.Font"] = {}
        self._texture_cache: Dict[Tuple[str, int, Tuple[int, int, int]], moderngl.Texture] = {}

        self._program = ctx.program(
            vertex_shader=_TEXT_VERTEX_SRC,
            fragment_shader=_TEXT_FRAGMENT_SRC,
        )

        # Reusable quad VBO (positions + uvs interleaved), rewritten per draw.
        self._vbo = ctx.buffer(reserve=4 * (2 + 2) * 4, dynamic=True)
        self._vao = ctx.vertex_array(
            self._program,
            [(self._vbo, "2f 2f", "in_position", "in_uv")],
        )

    def _get_font(self, size: int) -> "pygame.font.Font":
        font = self._fonts.get(size)
        if font is None:
            font = pygame.font.SysFont(None, size)
            self._fonts[size] = font
        return font

    def _get_texture(self, text: str, size: int) -> Tuple[moderngl.Texture, int, int]:
        key = (text, size)
        cached = self._texture_cache.get(key)
        if cached is not None:
            return cached

        font = self._get_font(size)
        # Render in opaque white; tint color is applied in the fragment
        # shader via u_tint, using the rendered glyph alpha as a mask.
        surface = font.render(text if text else " ", True, (255, 255, 255))
        surface = surface.convert_alpha()
        width, height = surface.get_size()

        raw = pygame.image.tostring(surface, "RGBA", False)
        texture = self._ctx.texture((width, height), 4, raw)
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        entry = (texture, width, height)
        self._texture_cache[key] = entry
        return entry

    def draw_text(
        self,
        text: str,
        pos: Tuple[float, float],
        size: int = 24,
        color: Color = (1.0, 1.0, 1.0, 1.0),
        align: str = "center",
    ) -> None:
        """Draw `text` with its top-left (or centered) anchor at `pos`.

        align: "center" centers the text horizontally on pos[0]; "left"
        anchors the left edge of the text at pos[0]. In both cases pos[1]
        is the top of the text.
        """
        if not text:
            return

        texture, width, height = self._get_texture(text, size)

        x, y = float(pos[0]), float(pos[1])
        if align == "center":
            x -= width / 2.0

        x0, y0 = x, y
        x1, y1 = x + width, y + height

        # Two triangles forming the quad, with UVs (V flipped since pygame
        # surfaces are top-down while GL texture origin is bottom-left).
        verts = np.array(
            [
                x0, y0, 0.0, 0.0,
                x1, y0, 1.0, 0.0,
                x1, y1, 1.0, 1.0,
                x0, y0, 0.0, 0.0,
                x1, y1, 1.0, 1.0,
                x0, y1, 0.0, 1.0,
            ],
            dtype="f4",
        )

        needed_bytes = verts.nbytes
        if self._vbo.size < needed_bytes:
            self._vbo.release()
            self._vao.release()
            self._vbo = self._ctx.buffer(verts.tobytes(), dynamic=True)
            self._vao = self._ctx.vertex_array(
                self._program,
                [(self._vbo, "2f 2f", "in_position", "in_uv")],
            )
        else:
            self._vbo.write(verts.tobytes())

        if "u_resolution" in self._program:
            self._program["u_resolution"].value = (
                float(self._window_size[0]),
                float(self._window_size[1]),
            )
        if "u_tint" in self._program:
            self._program["u_tint"].value = (
                float(color[0]), float(color[1]), float(color[2]), float(color[3]),
            )

        texture.use(location=0)
        if "u_tex" in self._program:
            self._program["u_tex"].value = 0

        self._vao.render(mode=moderngl.TRIANGLES, vertices=6)

    def measure(self, text: str, size: int = 24) -> Tuple[int, int]:
        font = self._get_font(size)
        return font.size(text if text else " ")

    def release(self) -> None:
        for texture, _w, _h in self._texture_cache.values():
            texture.release()
        self._texture_cache.clear()
        if self._vao is not None:
            self._vao.release()
        if self._vbo is not None:
            self._vbo.release()
