from app.api.schemas.common import AlertOut, PatientIn, StepOut
from app.api.schemas.rooms import (
    PatientOut,
    RoomDetailOut,
    RoomOut,
    RoomSolveResponse,
    SnapshotOut,
    SnapshotPatientOut,
    SolveDetailOut,
    SolveSummaryOut,
    StoredAlertOut,
    StoredResultOut,
)
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
from app.ports.room_repository import (
    PatientRecord,
    RoomRecord,
    SolveRecord,
    SolveResultRecord,
)
from app.search.engine import TraceRow
from app.search.heuristics import AlgorithmName
from app.search.report import ScheduleStep
from app.services.room_service import RoomSnapshot, RoomSolveOutcome
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


def to_room_out(room: RoomRecord) -> RoomOut:
    return RoomOut(
        id=room.id,
        name=room.name,
        shift_started_at=room.shift_started_at,
        doctors=room.doctors,
        status=room.status,
        created_at=room.created_at,
    )


def to_patient_out(patient: PatientRecord) -> PatientOut:
    return PatientOut(
        id=patient.id,
        label=patient.label,
        level=patient.level,
        duration_min=patient.duration_min,
        arrived_at=patient.arrived_at,
        attended_at=patient.attended_at,
        doctor=patient.doctor,
        created_at=patient.created_at,
    )


def to_snapshot_out(snapshot: RoomSnapshot) -> SnapshotOut:
    return SnapshotOut(
        at=snapshot.now,
        t0=snapshot.t0,
        doctors_free_at=list(snapshot.doctors_free_at),
        patients=[
            SnapshotPatientOut(
                id=p.patient_id,
                level=p.level,
                wait=p.wait,
                duration=p.duration,
                attended=p.patient_id in snapshot.attended,
                waiting_now=p.wait_at(snapshot.t0),
                limit=p.limit,
                minutes_to_limit=p.limit - p.wait_at(snapshot.t0),
            )
            for p in snapshot.patients
        ],
        not_arrived=snapshot.not_arrived,
    )


def to_room_detail_out(
    room: RoomRecord, patients: list[PatientRecord], snapshot: RoomSnapshot | None
) -> RoomDetailOut:
    return RoomDetailOut(
        **to_room_out(room).model_dump(),
        patients=[to_patient_out(p) for p in patients],
        snapshot=to_snapshot_out(snapshot) if snapshot is not None else None,
    )


def to_room_solve_response(result: RoomSolveOutcome) -> RoomSolveResponse:
    base = to_solve_response(result.problem, result.outcome)
    return RoomSolveResponse(
        **base.model_dump(),
        solve_id=result.solve.id,
        room_id=result.solve.room_id,
        computed_at=result.solve.computed_at,
        t0=result.snapshot.t0,
        doctors_free_at=list(result.snapshot.doctors_free_at),
        not_arrived=result.snapshot.not_arrived,
    )


def stored_step_out(step: dict) -> StepOut:
    return StepOut(
        patient=step["patient_id"],
        level=step["level"],
        doctor=step["doctor"],
        start=step["start"],
        end=step["end"],
        delay=step["delay"],
        penalty=step["penalty"],
        after_goal=step["after_goal"],
    )


def to_solve_summary_out(solve: SolveRecord) -> SolveSummaryOut:
    return SolveSummaryOut(
        id=solve.id,
        computed_at=solve.computed_at,
        created_at=solve.created_at,
        t0=solve.t0_min,
        doctors=solve.doctors,
        critical_first=solve.critical_first,
        goal_type=solve.goal_type,
        goal_value=solve.goal_value,
        reference=solve.reference,
        cost=solve.cost,
        baseline_cost=solve.baseline_cost,
        same_cost=solve.same_cost,
        baseline_gap_pct=solve.baseline_gap_pct,
    )


def to_solve_detail_out(
    solve: SolveRecord, results: list[SolveResultRecord]
) -> SolveDetailOut:
    order = {name.value: i for i, name in enumerate(AlgorithmName)}
    return SolveDetailOut(
        **to_solve_summary_out(solve).model_dump(),
        doctors_free_at=solve.doctors_free_at,
        input_snapshot=solve.input_snapshot,
        baseline_order=solve.baseline_order,
        alerts=[
            StoredAlertOut(
                patient=a["patient_id"], code=a["code"], minutes=a["minutes"]
            )
            for a in solve.alerts
        ],
        results=[
            StoredResultOut(
                algorithm=r.algorithm,
                status=r.status,
                weight=r.weight,
                cost=r.cost,
                expanded=r.expanded,
                max_frontier=r.max_frontier,
                ms=r.elapsed_ms,
                reopened=r.reopened,
                steps=[stored_step_out(s) for s in r.steps],
                left_out=[stored_step_out(s) for s in r.left_out],
                limit_attempts=[
                    AttemptOut(
                        weight=a["weight"],
                        expanded=a["expanded"],
                        max_frontier=a["max_frontier"],
                        ms=a["elapsed_ms"],
                    )
                    for a in r.limit_attempts
                ],
            )
            for r in sorted(results, key=lambda r: order.get(r.algorithm, len(order)))
        ],
    )
