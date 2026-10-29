from app.domain.constants import CRITICAL_MAX_LEVEL, GOAL_NODE, MAX_PATIENTS
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient

State = frozenset[str]
Successor = tuple[State | str, int, str | None]


class Problem:
    def __init__(
        self,
        patients: list[Patient],
        goal: Goal,
        start_attended: State = frozenset(),
        t0: int = 0,
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
        self.goal = goal
        self.start_state = start_attended
        self.t0 = t0
        self._time_cache: dict[State, int] = {}

    def initial_state(self) -> State:
        return self.start_state

    def patient(self, patient_id: str) -> Patient:
        return self.by_id[patient_id]

    def pending(self, state: State) -> list[Patient]:
        return [p for p in self.patients if p.patient_id not in state]

    def time_of(self, state: State) -> int:
        if state not in self._time_cache:
            attended_now = state - self.start_state
            self._time_cache[state] = self.t0 + sum(
                self.by_id[pid].duration for pid in attended_now
            )
        return self._time_cache[state]

    def horizon_end(self) -> int | None:
        if self.goal.type != GoalType.HORIZON:
            return None
        return self.t0 + self.goal.value

    def fits_horizon(self, patient: Patient, t: int) -> bool:
        end = self.horizon_end()
        return end is None or t + patient.duration <= end

    def is_goal(self, state: State) -> bool:
        pending = self.pending(state)
        goal_type = self.goal.type
        if goal_type == GoalType.ALL:
            return not pending
        if goal_type == GoalType.CRITICAL:
            return all(p.level > CRITICAL_MAX_LEVEL for p in pending)
        if goal_type == GoalType.K:
            return len(state) - len(self.start_state) == self.goal.value
        if goal_type == GoalType.HORIZON:
            t = self.time_of(state)
            return not any(self.fits_horizon(p, t) for p in pending)
        return self.goal.value <= state

    def closing_order(self, state: State) -> list[Patient]:
        return sorted(self.pending(state), key=lambda p: (p.level, -p.wait))

    def closing_cost(self, state: State) -> int:
        t = self.time_of(state)
        total = 0
        for patient in self.closing_order(state):
            total += patient.penalty_at(t)
            t += patient.duration
        return total

    def successors(self, state: State) -> list[Successor]:
        if self.is_goal(state):
            return [(GOAL_NODE, self.closing_cost(state), None)]
        t = self.time_of(state)
        return [
            (state | {p.patient_id}, p.penalty_at(t), p.patient_id)
            for p in self.pending(state)
            if self.fits_horizon(p, t)
        ]
