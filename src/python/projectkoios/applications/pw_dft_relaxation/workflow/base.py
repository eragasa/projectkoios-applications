"""Application-facing structural-relaxation workflow status."""

from enum import StrEnum


class PwDftRelaxationWorkflowStatus(StrEnum):
    """Project CPN progress without exposing an engine representation."""

    READY = "ready"
    AWAITING_PROJECTION = "awaiting-projection"
    INPUT_PROJECTED = "input-projected"
    EXTERNAL_AUTHORITY_REQUIRED = "external-authority-required"
    TERMINATED = "terminated"
