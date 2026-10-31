from dataclasses import dataclass

from app.domain.errors import DomainError, ErrorCode
from app.domain.patient import Patient
from app.domain.problem import Problem, State


@dataclass(frozen=True)
class BaselineResult:
    order: list[str]
    cost: int


def level_key(problem: Problem, patient: Patient) -> tuple[int, int, int]:
    return (patient.level, -patient.wait, problem.patients.index(patient))


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
    state = problem.initial_state()
    order: list[str] = []
    total = 0
    while not problem.is_goal(state):
        chosen = min(problem.candidates(state), key=lambda p: level_key(problem, p))
        state, cost = _attend(problem, state, chosen.patient_id)
        order.append(chosen.patient_id)
        total += cost
    return BaselineResult(order, total + problem.closing_cost(state))


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
