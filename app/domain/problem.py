from app.domain.constants import CRITICAL_MAX_LEVEL, GOAL_NODE, MAX_PATIENTS
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient

State = frozenset[str]

class Problem:
    def __init__(self, patients: list[Patient], goal: Goal, start_attended: State = frozenset(), t0: int = 0, max_patients: int = MAX_PATIENTS, ) -> None:
        self.patients = tuple(patients)
        self.by_id = {p.patient_id: p for p in patients}
        if len(patients) > max_patients:
            raise DomainError(
                ErrorCode.TOO_MANY_PATIENTS,
                f"Máximo {max_patients} pacientes",
                "patients"
            )
        if len(self.by_id) != len(patients):
            raise DomainError(
                ErrorCode.DUPLICATE_PATIENT_ID,
                "Hay ids de pacientes repetidos",
                "patients"
            ) 
        self.goal = goal
        self.start_state = start_attended
        self.t0 = t0
        self._time_cache: dict[State, int] = {}
        