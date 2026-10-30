from dataclasses import dataclass

from app.domain.constants import (
    CRITICAL_MAX_LEVEL,
    GOAL_NODE,
    IMMEDIATE_LEVEL,
    MAX_DOCTORS,
    MAX_PATIENTS,
    MIN_DOCTORS,
)
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient


@dataclass(frozen=True)
class State:
    attended: frozenset[str]
    free_at: tuple[int, ...]

    @property
    def next_start(self) -> int:
        return self.free_at[0]


Successor = tuple[State | str, int, str | None]


class Problem:
    def __init__(
        self,
        patients: list[Patient],
        goal: Goal,
        start_attended: frozenset[str] = frozenset(),
        t0: int = 0,
        doctors: int = 1,
        doctors_free_at: tuple[int, ...] | None = None,
        critical_first: bool = True,
        max_patients: int = MAX_PATIENTS,
    ) -> None:
        self.patients = tuple(patients)
        self.by_id = {p.patient_id: p for p in patients}
        if len(patients) > max_patients:
            raise DomainError(
                ErrorCode.TOO_MANY_PATIENTS,
                f"Máximo {max_patients} pacientes",
                "patients",
            )
        if len(self.by_id) != len(patients):
            raise DomainError(
                ErrorCode.DUPLICATE_PATIENT_ID,
                "Hay ids de pacientes repetidos",
                "patients",
            )
        all_ids = set(self.by_id)
        if not start_attended <= all_ids:
            raise DomainError(
                ErrorCode.UNKNOWN_PATIENT,
                "Hay pacientes atendidos que no están en la lista",
                "start.attended",
            )
        if goal.type == GoalType.SUBSET and not goal.value <= all_ids:
            raise DomainError(
                ErrorCode.UNKNOWN_PATIENT,
                "El subconjunto tiene pacientes que no están en la lista",
                "goal.value",
            )
        pending_ids = all_ids - start_attended
        if not pending_ids:
            raise DomainError(
                ErrorCode.NO_PENDING_PATIENTS,
                "No hay pacientes por ser atendidos",
                "start.attended",
            )
        if goal.type == GoalType.K and goal.value > len(pending_ids):
            raise DomainError(
                ErrorCode.INVALID_GOAL_VALUE,
                f"K no puede ser mayor que {len(pending_ids)} pendientes",
                "goal.value",
            )
        if any(self.by_id[pid].wait + t0 < 0 for pid in pending_ids):
            raise DomainError(
                ErrorCode.PATIENT_NOT_ARRIVED,
                "Hay pacientes que aún no llegaban en t0",
                "patients",
            )
        if doctors < MIN_DOCTORS or doctors > MAX_DOCTORS:
            raise DomainError(
                ErrorCode.INVALID_DOCTORS,
                f"El número de médicos debe estar entre {MIN_DOCTORS} y {MAX_DOCTORS}",
                "doctors",
            )
        free_at = doctors_free_at if doctors_free_at is not None else (t0,) * doctors
        if len(free_at) != doctors:
            raise DomainError(
                ErrorCode.INVALID_DOCTORS,
                "Debe indicarse a qué minuto se libera cada médico",
                "doctors_free_at",
            )
        if any(minute < t0 for minute in free_at):
            raise DomainError(
                ErrorCode.INVALID_DOCTORS,
                "Ningún médico puede liberarse antes de t0",
                "doctors_free_at",
            )
        self.goal = goal
        self.t0 = t0
        self.doctors = doctors
        self.critical_first = critical_first
        self.start_state = State(start_attended, tuple(sorted(free_at)))

    def initial_state(self) -> State:
        return self.start_state

    def patient(self, patient_id: str) -> Patient:
        return self.by_id[patient_id]

    def pending(self, state: State) -> list[Patient]:
        return [p for p in self.patients if p.patient_id not in state.attended]

    def time_of(self, state: State) -> int:
        return state.next_start

    def horizon_end(self) -> int | None:
        if self.goal.type != GoalType.HORIZON:
            return None
        return self.t0 + self.goal.value

    def fits_horizon(self, patient: Patient, t: int) -> bool:
        end = self.horizon_end()
        return end is None or t + patient.duration <= end

    def assign(self, state: State, patient: Patient) -> State:
        t = state.next_start
        free_at = tuple(sorted(state.free_at[1:] + (t + patient.duration,)))
        return State(state.attended | {patient.patient_id}, free_at)

    def candidates(self, state: State) -> list[Patient]:
        t = self.time_of(state)
        fitting = [p for p in self.pending(state) if self.fits_horizon(p, t)]
        if self.critical_first:
            immediate = [p for p in fitting if p.level == IMMEDIATE_LEVEL]
            if immediate:
                return immediate
        return fitting

    def is_goal(self, state: State) -> bool:
        pending = self.pending(state)
        goal_type = self.goal.type
        if goal_type == GoalType.ALL:
            return not pending
        if goal_type == GoalType.CRITICAL:
            return all(p.level > CRITICAL_MAX_LEVEL for p in pending)
        if goal_type == GoalType.K:
            attended_now = len(state.attended) - len(self.start_state.attended)
            return attended_now == self.goal.value
        if goal_type == GoalType.HORIZON:
            t = self.time_of(state)
            return not any(self.fits_horizon(p, t) for p in pending)
        return self.goal.value <= state.attended

    def closing_order(self, state: State) -> list[Patient]:
        return sorted(self.pending(state), key=lambda p: (p.level, -p.wait))

    def closing_cost(self, state: State) -> int:
        total = 0
        for patient in self.closing_order(state):
            total += patient.penalty_at(state.next_start)
            state = self.assign(state, patient)
        return total

    def successors(self, state: State) -> list[Successor]:
        if self.is_goal(state):
            return [(GOAL_NODE, self.closing_cost(state), None)]
        t = self.time_of(state)
        return [
            (self.assign(state, p), p.penalty_at(t), p.patient_id)
            for p in self.candidates(state)
        ]
