from collections.abc import Callable
from enum import Enum
from itertools import accumulate

from app.domain.constants import GOAL_NODE
from app.domain.problem import Problem, State

Heuristic = Callable[[Problem, State | str], int]


class AlgorithmName(str, Enum):
    UCS = "ucs"
    ASTAR_SIMPLE = "astar_simple"
    ASTAR = "astar"


def zero(problem: Problem, state: State | str) -> int:
    return 0


def simple(problem: Problem, state: State | str) -> int:
    if state == GOAL_NODE:
        return 0
    t = problem.time_of(state)
    return sum(p.penalty_at(t) for p in problem.pending(state))


def full(problem: Problem, state: State | str) -> int:
    if state == GOAL_NODE:
        return 0
    pending = problem.pending(state)
    if not pending:
        return 0
    t = problem.time_of(state)
    base = sum(p.penalty_at(t) for p in pending)
    late_weights = sorted((p.weight for p in pending if p.is_late_at(t)), reverse=True)
    if not late_weights:
        return base
    shortest_sums = [0, *accumulate(sorted(p.duration for p in pending))]
    doctors = len(state.free_at)
    extra = 0
    for position, weight in enumerate(late_weights):
        extra += weight * minimum_extra_wait(state, t, position, doctors, shortest_sums)
    return base + extra


def minimum_extra_wait(
    state: State, t: int, position: int, doctors: int, shortest_sums: list[int]
) -> int:
    if position < doctors:
        return min(state.free_at[position] - t, shortest_sums[1])
    return shortest_sums[position // doctors]


HEURISTICS: dict[AlgorithmName, Heuristic] = {
    AlgorithmName.UCS: zero,
    AlgorithmName.ASTAR_SIMPLE: simple,
    AlgorithmName.ASTAR: full,
}
