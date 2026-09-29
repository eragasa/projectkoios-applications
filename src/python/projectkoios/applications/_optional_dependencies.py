"""Explicit guards for optional application capability dependencies."""

from __future__ import annotations

import importlib


class ApplicationCapabilityDependencyError(ImportError):
    """An explicitly selected application capability lacks its dependency extra."""


def require_simulation_contract(module: str) -> None:
    """Require calculator-neutral simulation contracts for a simulation capability."""
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as error:
        raise ApplicationCapabilityDependencyError(
            "simulation application dependencies are unavailable; install "
            "projectkoios-applications[simulations]"
        ) from error
