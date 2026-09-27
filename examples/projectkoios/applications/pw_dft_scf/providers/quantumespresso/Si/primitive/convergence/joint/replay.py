"""Compose provider-normalized QE evidence with application replay policy.

The provider owner retains native artifacts and parsing. This example accepts
only the explicit application evidence contract; it neither discovers provider
corpora nor invokes Quantum ESPRESSO.
"""

from __future__ import annotations

from projectkoios.applications.pw_dft_scf.replay import (
    PwDftScfConvergenceReplayEvidence,
    PwDftScfConvergenceReplayer,
    PwDftScfConvergenceReplayResult,
)


def replay(
    evidence: PwDftScfConvergenceReplayEvidence,
) -> PwDftScfConvergenceReplayResult:
    """Replay one already-normalized evidence declaration deterministically."""
    return PwDftScfConvergenceReplayer().replay(evidence)
