"""Private trusted SNAKES topology for one calculator-neutral SCF evaluation."""

from __future__ import annotations

from snakes.nets import (  # type: ignore[import-untyped]
    Expression,
    PetriNet,
    Place,
    Test,
    Transition,
    Variable,
)
from snakes.typing import Instance  # type: ignore[import-untyped]

from projectkoios.simulations.dft.pw.scf.actions import (
    AnalyzePwDftScfOutput,
    RegisterPwDftScfTask,
    SubmitPwDftScfTask,
)
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfRequestReference,
    PwDftScfResult,
    PwDftScfWorkflowFailed,
    PwDftScfWorkflowOutcome,
    PwDftScfWorkflowStart,
    PwDftScfWorkflowSucceeded,
)
from projectkoios.simulations.dft.pw.scf.events import (
    PwDftScfOutputAnalyzed,
    PwDftScfTaskCompleted,
    PwDftScfTaskFailed,
    PwDftScfTaskRegistered,
    PwDftScfTaskSubmitted,
)


def build_dft_pw_scf_net(evaluation_id: str) -> PetriNet:
    """Build the named SCF lifecycle with explicit start and terminal places."""
    net = PetriNet("dft_pw_scf")
    # Only reviewed constructors are injected; declare()/exec is not used.
    net.globals["RegisterPwDftScfTask"] = RegisterPwDftScfTask
    net.globals["SubmitPwDftScfTask"] = SubmitPwDftScfTask
    net.globals["AnalyzePwDftScfOutput"] = AnalyzePwDftScfOutput
    net.globals["PwDftScfResult"] = PwDftScfResult
    net.globals["PwDftScfWorkflowSucceeded"] = PwDftScfWorkflowSucceeded
    net.globals["PwDftScfWorkflowFailed"] = PwDftScfWorkflowFailed

    net.add_place(
        Place(
            "workflow_start",
            [PwDftScfWorkflowStart(evaluation_id)],
            Instance(PwDftScfWorkflowStart),
        )
    )
    net.add_place(
        Place(
            "request",
            [PwDftScfRequestReference(evaluation_id)],
            Instance(PwDftScfRequestReference),
        )
    )
    net.add_place(Place("registration_action", check=Instance(RegisterPwDftScfTask)))
    net.add_place(Place("task_registered", check=Instance(PwDftScfTaskRegistered)))
    net.add_place(Place("submission_action", check=Instance(SubmitPwDftScfTask)))
    net.add_place(Place("task_submitted", check=Instance(PwDftScfTaskSubmitted)))
    net.add_place(Place("task_waiting", check=Instance(PwDftScfTaskSubmitted)))
    net.add_place(Place("task_completed", check=Instance(PwDftScfTaskCompleted)))
    net.add_place(Place("task_failed", check=Instance(PwDftScfTaskFailed)))
    net.add_place(Place("analysis_action", check=Instance(AnalyzePwDftScfOutput)))
    net.add_place(Place("output_analyzed", check=Instance(PwDftScfOutputAnalyzed)))
    net.add_place(Place("terminal_outcome", check=Instance(PwDftScfWorkflowOutcome)))

    net.add_transition(Transition("start_workflow"))
    net.add_input("workflow_start", "start_workflow", Variable("start"))
    net.add_input("request", "start_workflow", Test(Variable("request")))
    net.add_output(
        "registration_action",
        "start_workflow",
        Expression("RegisterPwDftScfTask(start.evaluation_id)"),
    )

    net.add_transition(
        Transition(
            "accept_registration",
            Expression("action.evaluation_id == registered.evaluation_id"),
        )
    )
    net.add_input("registration_action", "accept_registration", Variable("action"))
    net.add_input("task_registered", "accept_registration", Variable("registered"))
    net.add_output(
        "submission_action",
        "accept_registration",
        Expression("SubmitPwDftScfTask(registered.task_id)"),
    )

    net.add_transition(
        Transition(
            "accept_submission",
            Expression("action.task_id == submitted.task_id"),
        )
    )
    net.add_input("submission_action", "accept_submission", Variable("action"))
    net.add_input("task_submitted", "accept_submission", Variable("submitted"))
    net.add_output("task_waiting", "accept_submission", Variable("submitted"))

    net.add_transition(
        Transition(
            "accept_completion",
            Expression("waiting.task_id == completed.task_id"),
        )
    )
    net.add_input("task_waiting", "accept_completion", Variable("waiting"))
    net.add_input("task_completed", "accept_completion", Variable("completed"))
    net.add_output(
        "analysis_action",
        "accept_completion",
        Expression(
            "AnalyzePwDftScfOutput(completed.task_id, completed.output_artifact_id)"
        ),
    )

    net.add_transition(
        Transition(
            "accept_analysis",
            Expression(
                "action.task_id == analyzed.task_id and "
                "analyzed.observation.completed and analyzed.observation.converged"
            ),
        )
    )
    net.add_input("analysis_action", "accept_analysis", Variable("action"))
    net.add_input("output_analyzed", "accept_analysis", Variable("analyzed"))
    net.add_input("request", "accept_analysis", Test(Variable("request")))
    net.add_output(
        "terminal_outcome",
        "accept_analysis",
        Expression(
            "PwDftScfWorkflowSucceeded(PwDftScfResult(request.evaluation_id, "
            "analyzed.task_id, analyzed.observation))"
        ),
    )

    net.add_transition(
        Transition(
            "reject_analysis",
            Expression(
                "action.task_id == analyzed.task_id and "
                "not (analyzed.observation.completed and "
                "analyzed.observation.converged)"
            ),
        )
    )
    net.add_input("analysis_action", "reject_analysis", Variable("action"))
    net.add_input("output_analyzed", "reject_analysis", Variable("analyzed"))
    net.add_input("request", "reject_analysis", Test(Variable("request")))
    net.add_output(
        "terminal_outcome",
        "reject_analysis",
        Expression(
            "PwDftScfWorkflowFailed(request.evaluation_id, "
            "'scf-not-complete-and-converged', "
            "'calculator output did not establish completion and convergence')"
        ),
    )

    net.add_transition(
        Transition(
            "accept_analysis_failure",
            Expression("action.task_id == failed.task_id"),
        )
    )
    net.add_input("analysis_action", "accept_analysis_failure", Variable("action"))
    net.add_input("task_failed", "accept_analysis_failure", Variable("failed"))
    net.add_input("request", "accept_analysis_failure", Test(Variable("request")))
    net.add_output(
        "terminal_outcome",
        "accept_analysis_failure",
        Expression(
            "PwDftScfWorkflowFailed(request.evaluation_id, failed.code, failed.message)"
        ),
    )

    net.add_transition(
        Transition("accept_failure", Expression("waiting.task_id == failed.task_id"))
    )
    net.add_input("task_waiting", "accept_failure", Variable("waiting"))
    net.add_input("task_failed", "accept_failure", Variable("failed"))
    net.add_input("request", "accept_failure", Test(Variable("request")))
    net.add_output(
        "terminal_outcome",
        "accept_failure",
        Expression(
            "PwDftScfWorkflowFailed(request.evaluation_id, failed.code, failed.message)"
        ),
    )
    return net
