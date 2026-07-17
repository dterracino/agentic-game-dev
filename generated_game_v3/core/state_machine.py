"""Drives the current State: dispatches events/update/render and swaps
states based on State.next().

This module has no knowledge of pygame beyond the primitive event list
passed through from main.py, and no knowledge of gamelib/render internals.
It only depends on states/base.py's State Protocol and StateID enum.
"""

from __future__ import annotations

from typing import Any, List, Optional

from states.base import State, StateID


class StateMachine:
    """Owns the currently active State and manages transitions.

    The machine is constructed with a mapping from StateID to a factory
    callable that produces a State instance, plus the id of the initial
    state. States are lazily instantiated the first time they are
    entered, unless the caller supplies pre-built instances.
    """

    def __init__(
        self,
        context: Any,
        state_factories: dict,
        initial_state_id: StateID,
    ) -> None:
        self._context = context
        self._factories = state_factories
        self._current_id: Optional[StateID] = None
        self._current_state: Optional[State] = None
        self._switch_to(initial_state_id)

    @property
    def current_state_id(self) -> Optional[StateID]:
        return self._current_id

    @property
    def current_state(self) -> Optional[State]:
        return self._current_state

    def _build_state(self, state_id: StateID) -> State:
        factory = self._factories.get(state_id)
        if factory is None:
            raise KeyError(f"No factory registered for state {state_id!r}")
        return factory(self._context)

    def _switch_to(self, state_id: StateID) -> None:
        if self._current_state is not None:
            self._current_state.on_exit()
        new_state = self._build_state(state_id)
        self._current_id = state_id
        self._current_state = new_state
        self._current_state.on_enter()

    def handle_events(self, events: List[Any]) -> None:
        if self._current_state is None:
            return
        self._current_state.handle_events(events)

    def update(self, dt: float) -> None:
        if self._current_state is None:
            return
        self._current_state.update(dt)
        self._check_transition()

    def render(self) -> None:
        if self._current_state is None:
            return
        self._current_state.render()

    def _check_transition(self) -> None:
        if self._current_state is None:
            return
        next_id = self._current_state.next()
        if next_id is not None and next_id != self._current_id:
            self._switch_to(next_id)
