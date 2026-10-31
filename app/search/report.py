from dataclasses import dataclass
from enum import Enum

from app.domain.constants import CRITICAL_MAX_LEVEL, NEAR_LIMIT_MARGIN
from app.domain.patient import Patient
from app.domain.problem import Problem


@dataclass(frozen=True)
class ScheduleStep:
    patient_id: str
    level: int
    doctor: int
    start: int
    end: int
    delay: int
    penalty: int
    after_goal: bool


@dataclass(frozen=True)
class Schedule:
    steps: list[ScheduleStep]
    left_out: list[ScheduleStep]

    @property
    def cost(self) -> int:
        return sum(step.penalty for step in self.steps + self.left_out)

    @property
    def all_steps(self) -> list[ScheduleStep]:
        return self.steps + self.left_out


class AlertCode(str, Enum):
    ALREADY_LATE = "ALREADY_LATE"
    EXCEEDS_LIMIT = "EXCEEDS_LIMIT"
    NEAR_LIMIT = "NEAR_LIMIT"
    LEFT_OUT = "LEFT_OUT"
    LEFT_OUT_CRITICAL = "LEFT_OUT_CRITICAL"


@dataclass(frozen=True)
class Alert:
    patient_id: str
    code: AlertCode
    minutes: int


class DoctorBoard:
    def __init__(self, free_at: tuple[int, ...]) -> None:
        self.free_at = list(free_at)

    def take(self, start: int, duration: int) -> int:
        index = min(range(len(self.free_at)), key=lambda i: (self.free_at[i], i))
        if self.free_at[index] != start:
            raise RuntimeError(
                "La agenda no coincide con el médico que se libera primero"
            )
        self.free_at[index] = start + duration
        return index + 1


def build_schedule(problem: Problem, order: list[str]) -> Schedule:
    board = DoctorBoard(problem.doctors_free_at)
    state = problem.initial_state()
    steps = []
    for patient_id in order:
        patient = problem.patient(patient_id)
        steps.append(_step(patient, state.next_start, board, after_goal=False))
        state = problem.assign(state, patient)
    left_out = []
    for patient in problem.closing_order(state):
        left_out.append(_step(patient, state.next_start, board, after_goal=True))
        state = problem.assign(state, patient)
    return Schedule(steps, left_out)


def _step(
    patient: Patient, start: int, board: DoctorBoard, after_goal: bool
) -> ScheduleStep:
    return ScheduleStep(
        patient_id=patient.patient_id,
        level=patient.level,
        doctor=board.take(start, patient.duration),
        start=start,
        end=start + patient.duration,
        delay=patient.delay_at(start),
        penalty=patient.penalty_at(start),
        after_goal=after_goal,
    )


def build_alerts(
    problem: Problem, schedule: Schedule, margin: int = NEAR_LIMIT_MARGIN
) -> list[Alert]:
    alerts = []
    pending_ids = {p.patient_id for p in problem.pending(problem.initial_state())}
    for p in problem.patients:
        if p.patient_id in pending_ids and p.wait_at(problem.t0) > p.limit:
            alerts.append(
                Alert(
                    p.patient_id,
                    AlertCode.ALREADY_LATE,
                    p.wait_at(problem.t0) - p.limit,
                )
            )
    for step in schedule.all_steps:
        patient = problem.patient(step.patient_id)
        if step.delay > 0:
            alerts.append(Alert(step.patient_id, AlertCode.EXCEEDS_LIMIT, step.delay))
        else:
            remaining = patient.limit - patient.wait_at(step.start)
            if remaining <= margin:
                alerts.append(Alert(step.patient_id, AlertCode.NEAR_LIMIT, remaining))
        if step.after_goal:
            code = (
                AlertCode.LEFT_OUT_CRITICAL
                if step.level <= CRITICAL_MAX_LEVEL
                else AlertCode.LEFT_OUT
            )
            alerts.append(Alert(step.patient_id, code, step.delay))
    return alerts


def reduction_pct(ucs_expanded: int, other_expanded: int) -> float:
    if ucs_expanded == 0:
        return 0.0
    return round(100 * (1 - other_expanded / ucs_expanded), 2)


def baseline_gap_pct(baseline_cost: int, optimal_cost: int) -> float | None:
    if optimal_cost == 0:
        return 0.0 if baseline_cost == 0 else None
    return round(100 * (baseline_cost - optimal_cost) / optimal_cost, 2)


def doctor_loads(schedule: Schedule) -> dict[int, list[str]]:
    loads: dict[int, list[str]] = {}
    for step in schedule.all_steps:
        loads.setdefault(step.doctor, []).append(step.patient_id)
    return dict(sorted(loads.items()))
