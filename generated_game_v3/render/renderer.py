"""High-level draw API consuming only primitive tuples/colors.

This module wraps LineBatch/PolygonMesh and marker circles, and manages
frame begin/end. It never imports gamelib or states modules; it only
consumes primitive tuples/floats/colors.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

import moderngl

from render.line_batch import LineBatch
from render.polygon_mesh import PolygonMesh
from render.shaders import load_program

Color = Tuple[float, float, float, float]
Point = Tuple[float, float]

_DEFAULT_BORDER_COLOR: Color = (0.2, 0.8, 1.0, 1.0)
_DEFAULT_TRAIL_COLOR: Color = (1.0, 0.9, 0.2, 1.0)
_DEFAULT_CLAIM_COLOR: Color = (0.1, 0.4, 0.2, 0.85)
_MARKER_SEGMENTS = 24


class Renderer:
    """High level renderer wrapping GPU primitives.

    Consumes only primitive tuples/floats/colors -- never gamelib objects.
    """

    def __init__(self, ctx: moderngl.Context, window_size: Tuple[int, int]) -> None:
        self._ctx = ctx
        self._window_size = window_size

        self._line_program = load_program(ctx, "line")
        self._poly_program = load_program(ctx, "polygon")

        self._border_batch = LineBatch(ctx, self._line_program)
        self._trail_batch = LineBatch(ctx, self._line_program)
        self._claim_mesh = PolygonMesh(ctx, self._poly_program)
        self._marker_mesh = PolygonMesh(ctx, self._poly_program)

        self._clear_color = (0.03, 0.03, 0.05, 1.0)

    def begin_frame(self) -> None:
        self._ctx.viewport = (0, 0, self._window_size[0], self._window_size[1])
        self._ctx.clear(*self._clear_color)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def draw_border(self, points: Sequence[Point]) -> None:
        if not points or len(points) < 2:
            return
        self._border_batch.upload(list(points), _DEFAULT_BORDER_COLOR)
        self._set_resolution(self._line_program)
        self._border_batch.draw(mode=moderngl.LINE_STRIP)

    def draw_claimed_area(self, tris: Sequence[Point]) -> None:
        if not tris or len(tris) < 3:
            return
        flat: List[float] = []
        for p in tris:
            flat.append(float(p[0]))
            flat.append(float(p[1]))
        self._claim_mesh.upload_triangles(flat)
        self._set_resolution(self._poly_program)
        self._set_color(self._poly_program, _DEFAULT_CLAIM_COLOR)
        self._claim_mesh.draw()

    def draw_trail(self, points: Sequence[Point]) -> None:
        if not points or len(points) < 2:
            return
        self._trail_batch.upload(list(points), _DEFAULT_TRAIL_COLOR)
        self._set_resolution(self._line_program)
        self._trail_batch.draw(mode=moderngl.LINE_STRIP)

    def draw_marker(self, pos: Point, radius: float, color: Color) -> None:
        cx, cy = float(pos[0]), float(pos[1])
        flat: List[float] = []
        prev = None
        first = None
        for i in range(_MARKER_SEGMENTS + 1):
            angle = (i / _MARKER_SEGMENTS) * 2.0 * math.pi
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            if first is None:
                first = (px, py)
            if prev is not None:
                flat.extend([cx, cy, prev[0], prev[1], px, py])
            prev = (px, py)
        self._marker_mesh.upload_triangles(flat)
        self._set_resolution(self._poly_program)
        self._set_color(self._poly_program, color)
        self._marker_mesh.draw()

    def end_frame(self) -> None:
        self._ctx.disable(moderngl.BLEND)

    def _set_resolution(self, program: moderngl.Program) -> None:
        if "u_resolution" in program:
            program["u_resolution"].value = (
                float(self._window_size[0]),
                float(self._window_size[1]),
            )

    def _set_color(self, program: moderngl.Program, color: Color) -> None:
        if "u_color" in program:
            program["u_color"].value = (
                float(color[0]),
                float(color[1]),
                float(color[2]),
                float(color[3]),
            )
