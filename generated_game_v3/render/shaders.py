"""
Loads and compiles vertex/fragment shader pairs from render/shaders_src/
into moderngl programs.

Shader source files are expected to live alongside this module in a
`shaders_src` directory, named `<name>.vert` and `<name>.frag`.

If a requested shader pair does not exist on disk, a minimal built-in
fallback (flat-color 2D shader) is used instead so the renderer can
always obtain a valid program without touching the filesystem in a
surprising way.

All filesystem access is confined to paths relative to this file's
directory (Path(__file__).parent-relative), per project constraints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import moderngl

_SHADERS_DIR = Path(__file__).parent / "shaders_src"

# Cache of compiled programs keyed by (id(ctx), name) so repeated calls
# for the same context/name don't recompile shaders needlessly.
_program_cache: Dict[tuple, moderngl.Program] = {}

_FALLBACK_VERTEX_SRC = """
#version 330

in vec2 in_position;

uniform vec2 u_resolution;

void main() {
    // Convert pixel-space coordinates to normalized device coordinates.
    vec2 zero_to_one = in_position / u_resolution;
    vec2 zero_to_two = zero_to_one * 2.0;
    vec2 clip_space = zero_to_two - 1.0;
    // Flip Y so that +Y is down, matching typical 2D screen coordinates.
    gl_Position = vec4(clip_space.x, -clip_space.y, 0.0, 1.0);
}
"""

_FALLBACK_FRAGMENT_SRC = """
#version 330

uniform vec4 u_color;

out vec4 fragColor;

void main() {
    fragColor = u_color;
}
"""


def _read_source(name: str, ext: str) -> str | None:
    """Read a shader source file if it exists; otherwise return None."""
    path = _SHADERS_DIR / f"{name}.{ext}"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def load_program(ctx: moderngl.Context, name: str) -> moderngl.Program:
    """
    Load and compile a vertex/fragment shader pair named `name` from
    render/shaders_src/ (files `<name>.vert` and `<name>.frag`).

    Falls back to a built-in flat-color 2D shader if the files are not
    found on disk, so callers always receive a usable program.

    Compiled programs are cached per (context, name) pair.
    """
    cache_key = (id(ctx), name)
    cached = _program_cache.get(cache_key)
    if cached is not None:
        return cached

    vertex_src = _read_source(name, "vert")
    fragment_src = _read_source(name, "frag")

    if vertex_src is None:
        vertex_src = _FALLBACK_VERTEX_SRC
    if fragment_src is None:
        fragment_src = _FALLBACK_FRAGMENT_SRC

    program = ctx.program(
        vertex_shader=vertex_src,
        fragment_shader=fragment_src,
    )

    _program_cache[cache_key] = program
    return program
