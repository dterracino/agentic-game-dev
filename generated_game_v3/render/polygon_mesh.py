"""GPU triangle mesh primitive for filled claimed-area visuals.

This module knows nothing about gamelib objects; it only consumes flat
sequences of floats (x, y pairs) representing already-triangulated
geometry in normalized-device or screen space (as decided by the caller /
shader). It wraps a moderngl.Program + VBO + VAO and exposes a minimal
upload/draw API.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import moderngl


class PolygonMesh:
    """A dynamic triangle mesh uploaded to the GPU each frame (or as needed)."""

    def __init__(self, ctx: moderngl.Context, program: moderngl.Program) -> None:
        self._ctx = ctx
        self._program = program
        self._vbo: moderngl.Buffer | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vertex_count: int = 0

        # Attribute name expected in the vertex shader. This must match the
        # `in_position` attribute declared in render/shaders.py's fallback
        # vertex shader (and any custom shaders_src/*.vert files), which is
        # also used by LineBatch so the same fallback vertex shader can be
        # shared across primitives.
        self._pos_attr = "in_position"

        # Pre-allocate a small buffer to avoid None checks before first upload.
        initial = np.zeros(6, dtype="f4")
        self._vbo = ctx.buffer(initial.tobytes(), dynamic=True)
        self._vao = ctx.vertex_array(
            self._program,
            [(self._vbo, "2f", self._pos_attr)],
        )

    def upload_triangles(self, flat_tris: Sequence[float]) -> None:
        """Upload a flat sequence of (x, y, x, y, ...) triangle vertices.

        The length of flat_tris must be a multiple of 6 (3 verts * 2 floats)
        for well-formed triangles, but this function does not enforce that
        strictly beyond truncating to a multiple of 2 floats per vertex.
        """
        data = np.asarray(flat_tris, dtype="f4")
        if data.size == 0:
            self._vertex_count = 0
            return

        vertex_count = data.size // 2
        needed_bytes = vertex_count * 2 * 4

        if self._vbo is None or self._vbo.size < needed_bytes:
            if self._vbo is not None:
                self._vbo.release()
            if self._vao is not None:
                self._vao.release()
            self._vbo = self._ctx.buffer(data.tobytes(), dynamic=True)
            self._vao = self._ctx.vertex_array(
                self._program,
                [(self._vbo, "2f", self._pos_attr)],
            )
        else:
            self._vbo.write(data.tobytes())

        self._vertex_count = vertex_count

    def draw(self) -> None:
        if self._vao is None or self._vertex_count == 0:
            return
        self._vao.render(moderngl.TRIANGLES, vertices=self._vertex_count)

    def release(self) -> None:
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._vbo is not None:
            self._vbo.release()
            self._vbo = None
