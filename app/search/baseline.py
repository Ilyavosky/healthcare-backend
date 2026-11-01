import heapq
from dataclasses import dataclass

from app.domain.constants import CRITICAL_MAX_LEVEL
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem, State


@dataclass(frozen=True)
class BaselineResult:
    order: list[str]
    cost: int


def level_key(problem: Problem, patient: Patient) -> tuple[int, int, int]:
    return (patient.level, -patient.wait, problem.capture_index[patient.patient_id])


def order_cost(problem: Problem, order: list[str]) -> int:
    state = problem.initial_state()
    total = 0
    for patient_id in order:
        if problem.is_goal(state):
            break
        state, cost = _attend(problem, state, patient_id)
        total += cost
    if not problem.is_goal(state):
        raise DomainError(
            ErrorCode.INVALID_GOAL_VALUE,
            "El orden termina antes de cumplir la meta",
            "order",
        )
    return total + problem.closing_cost(state)


def level_order(problem: Problem) -> BaselineResult:
    start = problem.initial_state()
    queue = sorted(problem.pending(start), key=lambda p: level_key(problem, p))
    free_at = list(start.free_at)
    tracker = _GoalTracker(problem, queue)
    taken = [False] * len(queue)
    order: list[str] = []
    total = 0
    first = 0
    while not tracker.reached(free_at[0]):
        while taken[first]:
            first += 1
        index = _first_fitting(problem, queue, taken, first, free_at[0])
        patient = queue[index]
        begin = heapq.heappop(free_at)
        heapq.heappush(free_at, begin + patient.duration)
        total += patient.penalty_at(begin)
        taken[index] = True
        tracker.remove(patient)
        order.append(patient.patient_id)
    for index, patient in enumerate(queue):
        if not taken[index]:
            begin = heapq.heappop(free_at)
            heapq.heappush(free_at, begin + patient.duration)
            total += patient.penalty_at(begin)
    return BaselineResult(order, total)


def _first_fitting(
    problem: Problem, queue: list[Patient], taken: list[bool], first: int, t: int
) -> int:
    for index in range(first, len(queue)):
        if not taken[index] and problem.fits_horizon(queue[index], t):
            return index
    raise DomainError(
        ErrorCode.INVALID_GOAL_VALUE, "Nadie cabe en el horizonte", "goal.value"
    )


class _GoalTracker:
    def __init__(self, problem: Problem, pending: list[Patient]) -> None:
        self.problem = problem
        self.goal = problem.goal
        self.remaining = len(pending)
        self.critical = sum(1 for p in pending if p.level <= CRITICAL_MAX_LEVEL)
        self.attended = 0
        self.subset = (
            {p.patient_id for p in pending} & self.goal.value
            if self.goal.type == GoalType.SUBSET
            else set()
        )
        self.durations = sorted(p.duration for p in pending)
        self.removed: dict[int, int] = {}
        self.shortest = 0

    def remove(self, patient: Patient) -> None:
        self.remaining -= 1
        self.attended += 1
        if patient.level <= CRITICAL_MAX_LEVEL:
            self.critical -= 1
        self.subset.discard(patient.patient_id)
        self.removed[patient.duration] = self.removed.get(patient.duration, 0) + 1

    def reached(self, t: int) -> bool:
        kind = self.goal.type
        if kind == GoalType.ALL:
            return self.remaining == 0
        if kind == GoalType.CRITICAL:
            return self.critical == 0
        if kind == GoalType.K:
            return self.attended == self.goal.value
        if kind == GoalType.SUBSET:
            return not self.subset
        return (
            self._min_duration() is None
            or t + self._min_duration() > self.problem.horizon_end()
        )

    def _min_duration(self) -> int | None:
        while self.shortest < len(self.durations):
            duration = self.durations[self.shortest]
            if self.removed.get(duration, 0):
                self.removed[duration] -= 1
                self.shortest += 1
                continue
            return duration
        return None


def _attend(problem: Problem, state: State, patient_id: str) -> tuple[State, int]:
    allowed = {p.patient_id: p for p in problem.candidates(state)}
    if patient_id not in allowed:
        raise DomainError(
            ErrorCode.UNKNOWN_PATIENT,
            f"{patient_id} no se puede atender en ese momento",
            "order",
        )
    patient = allowed[patient_id]
    return problem.assign(state, patient), patient.penalty_at(state.next_start)
