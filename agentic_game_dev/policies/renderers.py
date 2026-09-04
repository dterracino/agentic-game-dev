from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RendererProfile:
    """Capabilities and implementation rules for a selected rendering backend."""

    name: str
    default_strategy: str
    requirements: tuple[str, ...]

    def prompt_section(self) -> str:
        rules = "\n".join(f"- {requirement}" for requirement in self.requirements)
        return (
            f"Renderer profile ({self.name}; selected by the user):\n"
            f"Default strategy: {self.default_strategy}\n{rules}"
        )


PYGAME_PROFILE = RendererProfile(
    name="pygame",
    default_strategy=(
        "Use pygame-ce surfaces, sprites, fonts, and draw operations for a clear 2D presentation."
    ),
    requirements=(
        "Use pygame-ce as the rendering and windowing backend.",
        "Choose proportionate CPU-rendered techniques for requested visual effects; do not add "
        "ModernGL unless the selected renderer changes.",
        "Keep presentation code separate from domain and gameplay state.",
        "Document how each requested visual effect is implemented and how it can be observed.",
    ),
)


MODERNGL_PROFILE = RendererProfile(
    name="moderngl",
    default_strategy=(
        "Use pygame-ce for the window, input, and audio and a real ModernGL context for rendering."
    ),
    requirements=(
        "Create and use a real ModernGL context and shader program; listing the dependency without "
        "using it is a contract failure.",
        "Translate technology-neutral visual descriptions into appropriate GPU techniques. Prefer "
        "fragment shader passes for per-pixel or full-screen effects, vertex shaders for geometric "
        "transforms, and instancing for large repeated particle or sprite workloads.",
        "Do not force an effect into a shader when a simpler draw operation is clearer and fast "
        "enough; record the chosen technique and rationale in the rendering contract.",
        "Define render-pass order, framebuffer and texture ownership, resize behavior, uniforms, "
        "blending, and cleanup. Establish one texture-coordinate/orientation convention and flip "
        "at most once.",
        "Keep GLSL source in dedicated rendering/shader modules rather than mixing it into "
        "gameplay state. The current generator emits Python files, so dedicated Python "
        "shader-source modules are acceptable.",
        "Map every visual effect requested by the brief or specification to an owner, concrete "
        "technique, and observable validation method.",
        "Keep simulation and gameplay rules independent from the GPU context.",
    ),
)


_PROFILES = {
    PYGAME_PROFILE.name: PYGAME_PROFILE,
    MODERNGL_PROFILE.name: MODERNGL_PROFILE,
}


def get_renderer_profile(renderer: str) -> RendererProfile:
    try:
        return _PROFILES[renderer]
    except KeyError as exc:
        choices = ", ".join(sorted(_PROFILES))
        raise ValueError(f"Unknown renderer {renderer!r}; expected one of: {choices}") from exc
