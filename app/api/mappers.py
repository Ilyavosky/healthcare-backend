from app.api.schemas.common import AlertOut, PatientIn, StepOut
from app.api.schemas.solve import (
    AlgorithmResultOut,
    AttemptOut,
    BaselineOut,
    GoalIn,
    SolveRequest,
    SolveResponse,
    TraceRowOut,
)
from app.domain.errors import DomainError
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem, State
from app.search.engine import TraceRow
from app.search.report import ScheduleStep
from app.services.solve_service import AlgorithmRun, SolveOutcome

BASELINE_REFERENCE = "baseline"


def to_patient(data: PatientIn, index: int) -> Patient:
    try:
        return Patient(data.id, data.level, data.wait, data.duration)
    except DomainError as error:
        raise DomainError(
            error.code, error.message, f"patients[{index}].{error.field}"
        ) from error


def to_patient_in(patient: Patient) -> PatientIn:
    return PatientIn(
        id=patient.patient_id,
        level=patient.level,
        wait=patient.wait,
        duration=patient.duration,
    )


def to_goal(data: GoalIn) -> Goal:
    value = data.value
    if data.type == GoalType.SUBSET and isinstance(value, list):
        value = frozenset(value)
    return Goal(data.type, value)


def to_problem(request: SolveRequest) -> Problem:
    free_at = request.start.doctors_free_at
    return Problem(
        [to_patient(p, i) for i, p in enumerate(request.patients)],
        to_goal(request.goal),
        frozenset(request.start.attended),
        request.start.t0,
        doctors=request.doctors,
        doctors_free_at=tuple(free_at) if free_at is not None else None,
        critical_first=request.critical_first,
    )


def to_step_out(step: ScheduleStep) -> StepOut:
    return StepOut(
        patient=step.patient_id,
        level=step.level,
        doctor=step.doctor,
        start=step.start,
        end=step.end,
        delay=step.delay,
        penalty=step.penalty,
        after_goal=step.after_goal,
    )


def to_trace_row_out(row: TraceRow) -> TraceRowOut:
    if isinstance(row.state, State):
        return TraceRowOut(
            attended=sorted(row.state.attended),
            free_at=list(row.state.free_at),
            is_goal=False,
            g=row.g,
            h=row.h,
            f=row.f,
        )
    return TraceRowOut(
        attended=None, free_at=None, is_goal=True, g=row.g, h=row.h, f=row.f
    )


def to_algorithm_result_out(run: AlgorithmRun) -> AlgorithmResultOut:
    attempts = [
        AttemptOut(
            weight=limit.weight,
            expanded=limit.expanded,
            max_frontier=limit.max_frontier,
            ms=round(limit.elapsed_ms, 2),
        )
        for limit in run.limits
    ]
    if not run.finished:
        return AlgorithmResultOut(
            status="limit_reached",
            weight=run.weight,
            cost=None,
            closing_cost=None,
            expanded=None,
            max_frontier=None,
            ms=None,
            reopened=None,
            steps=[],
            left_out=[],
            trace=[],
            limit_attempts=attempts,
        )
    result = run.result
    schedule = run.schedule
    return AlgorithmResultOut(
        status="optimal" if run.optimal else "approximate",
        weight=run.weight,
        cost=result.cost,
        closing_cost=sum(step.penalty for step in schedule.left_out),
        expanded=result.expanded,
        max_frontier=result.max_frontier,
        ms=round(result.elapsed_ms, 2),
        reopened=result.reopened,
        steps=[to_step_out(step) for step in schedule.steps],
        left_out=[to_step_out(step) for step in schedule.left_out],
        trace=[to_trace_row_out(row) for row in result.trace],
        limit_attempts=attempts,
    )


def to_solve_response(problem: Problem, outcome: SolveOutcome) -> SolveResponse:
    reference = (
        outcome.reference.value if outcome.reference is not None else BASELINE_REFERENCE
    )
    return SolveResponse(
        reference=reference,
        cost=outcome.cost,
        doctors=problem.doctors,
        results={
            name.value: to_algorithm_result_out(run)
            for name, run in outcome.runs.items()
        },
        baseline=BaselineOut(
            cost=outcome.baseline.cost,
            order=outcome.baseline.order,
            steps=[to_step_out(step) for step in outcome.baseline_schedule.steps],
            left_out=[to_step_out(step) for step in outcome.baseline_schedule.left_out],
        ),
        same_cost=outcome.same_cost,
        reduction_pct={name.value: pct for name, pct in outcome.reduction_pct.items()},
        baseline_gap_pct=outcome.baseline_gap_pct,
        alerts=[
            AlertOut(
                patient=alert.patient_id, code=alert.code.value, minutes=alert.minutes
            )
            for alert in outcome.alerts
        ],
    )
