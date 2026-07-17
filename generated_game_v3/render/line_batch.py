"""GPU line-strip drawing primitive for border/trail visuals.

This module wraps a moderngl VBO/VAO pair for drawing 2D line strips
(or other line-based primitives) with a single flat color. It consumes
only primitive tuples/floats/colors, never gamelib objects, per the
project's layering rules.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

import numpy as np
import moderngl


class LineBatch:
    """A reusable GPU line-strip primitive.

    Usage:
        batch = LineBatch(ctx, program)
        batch.upload(points, color)
        batch.draw()
    """

    def __init__(self, ctx: moderngl.Context, program: moderngl.Program) -> None:
        self._ctx = ctx
        self._program = program
        self._vbo: moderngl.Buffer | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vertex_count: int = 0
        # Pre-allocate a small buffer capacity; grows as needed.
        self._capacity: int = 0

        # Attribute name expected in the vertex shader for position data.
        self._pos_attr = "in_position"
        self._color_uniform_name = "u_color"

    def upload(self, points: Sequence[Tuple[float, float]], color: Tuple[float, float, float, float]) -> None:
        """Upload a new set of 2D points and a flat RGBA color to the GPU.

        points: sequence of (x, y) tuples in world/screen space (as expected
            by the shader's transform); may be empty, in which case draw()
            becomes a no-op.
        color: (r, g, b, a) floats in [0, 1].
        """
        pts = list(points)
        self._vertex_count = len(pts)

        if self._vertex_count == 0:
            return

        data = np.asarray(pts, dtype="f4").reshape(-1, 2)
        flat = np.ascontiguousarray(data, dtype="f4")

        required_bytes = flat.nbytes

        if self._vbo is None or required_bytes > self._capacity:
            # (Re)allocate buffer with some headroom.
            self._capacity = max(required_bytes, 4096)
            if self._vbo is not None:
                self._vbo.release()
            if self._vao is not None:
                self._vao.release()
                self._vao = None
            self._vbo = self._ctx.buffer(reserve=self._capacity, dynamic=True)
            self._vao = self._ctx.vertex_array(
                self._program,
                [(self._vbo, "2f", self._pos_attr)],
            )

        self._vbo.write(flat.tobytes())

        if self._color_uniform_name in self._program:
            self._program[self._color_uniform_name].value = tuple(color)

    def draw(self, mode: int = moderngl.LINE_STRIP) -> None:
        """Draw the currently uploaded line data using the given GL mode."""
        if self._vao is None or self._vertex_count == 0:
            return
        self._vao.render(mode=mode, vertices=self._vertex_count)

    def release(self) -> None:
        """Release GPU resources held by this batch."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._vbo is not None:
            self._vbo.release()
            self._vbo = None
