from app.domain.constants import CRITICAL_MAX_LEVEL, GOAL_NODE, MAX_PATIENTS
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient

State = frozenset[str]


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
