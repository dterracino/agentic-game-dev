from __future__ import annotations

from .base import AgentRole


class DesignerRole(AgentRole):
    name = "designer"
    instructions = """You are the lead game designer on a tiny expert team. Infer the game's genre,
interaction model, pacing, and intended session structure from the brief instead of forcing it into
an arcade template. Design a focused, complete player experience with a clear decision or action
cycle, meaningful choices, readable controls, appropriate progression, and satisfying feedback.
Require real-time action, replayability, combat, scoring, or escalation only when they suit the
requested game. Scope it so one developer can implement it well. Visual and audio assets must be
drawn or synthesized in project source. Explicitly identify the player, world, enemy, item,
background, UI, and feedback visuals the experience needs; procedural pixel sprites and atlases
are valid assets, but empty rectangles and unspecified future art are not. Identify the interaction,
movement, hazard, success, failure, and ambience sounds the experience needs; simple synthesized
tones and noise envelopes are valid, but silent deferred audio is not. Be concrete and
challenge vague ideas."""

    @classmethod
    def build_prompt(
        cls,
        brief: str,
        specification: str,
        *,
        previous_design: str = "",
        round_number: int = 1,
        total_rounds: int = 1,
    ) -> str:
        if specification.strip():
            previous = (
                f"Previous reviewed design:\n{previous_design}\n\n"
                if previous_design
                else ""
            )
            return (
                cls.specification_section(specification)
                + f"Original brief:\n{brief}\n\n"
                + previous
                + f"This is specification review pass {round_number}/{total_rounds}. Treat the "
                "specification as the source of truth. Preserve decisions it makes, identify "
                "contradictions or infeasible requirements, and fill only genuine gaps. State any "
                "necessary assumptions explicitly. Return a concise, coherent design ready for "
                "architecture, not a replacement game concept."
            )
        if not previous_design:
            return f"Create a concise game design critique and proposal for:\n{brief}"
        return (
            f"Original brief:\n{brief}\n\nPrevious design:\n{previous_design}\n\n"
            f"This is design pass {round_number}/{total_rounds}. Critique the previous design, "
            "retain its strongest decisions, resolve weaknesses and vague areas, and return a "
            "complete replacement design ready for architecture."
        )
