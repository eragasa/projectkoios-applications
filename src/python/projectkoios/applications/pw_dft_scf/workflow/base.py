"""Application-facing status for calculator-neutral SCF workflows."""

from __future__ import annotations

from enum import StrEnum


class PwDftScfWorkflowStatus(StrEnum):
    """Project a private marking into coarse application-facing progress."""

    ready = "ready"
    awaiting_registration = "awaiting-registration"
    awaiting_submission = "awaiting-submission"
    waiting_for_completion = "waiting-for-completion"
    analyzing = "analyzing"
    terminated = "terminated"
