"""Content-independent example wrapper around one mutable local SNAKES net."""

from __future__ import annotations

from typing import Any


class LocalSnakesRun:
    """Expose bounded firing and detached token snapshots without the net."""

    __slots__ = ("_maximum_firings", "_net")

    def __init__(self, net: Any, *, maximum_firings: int) -> None:
        """Retain a private net and a positive internal firing bound."""
        if maximum_firings <= 0:
            raise ValueError("maximum_firings must be positive")
        self._net = net
        self._maximum_firings = maximum_firings

    def add_token(self, place_name: str, token: object) -> None:
        """Insert one typed domain event at a named boundary place."""
        self._net.place(place_name).add(token)

    def tokens(self, place_name: str) -> tuple[object, ...]:
        """Return a detached deterministic token snapshot."""
        return tuple(sorted(self._net.place(place_name).tokens, key=repr))

    def drain_unique(self) -> tuple[str, ...]:
        """Fire uniquely enabled transitions until external input is required."""
        fired: list[str] = []
        while len(fired) < self._maximum_firings:
            enabled = tuple(
                (transition, transition.modes())
                for transition in self._net.transition()
                if transition.modes()
            )
            if not enabled:
                return tuple(fired)
            if len(enabled) != 1 or len(enabled[0][1]) != 1:
                raise RuntimeError(
                    "example requires exactly one enabled transition and binding"
                )
            transition, modes = enabled[0]
            transition.fire(modes[0])
            fired.append(transition.name)
        raise RuntimeError("example exceeded its internal transition firing bound")
