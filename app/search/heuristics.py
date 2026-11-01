from collections.abc import Callable
from enum import Enum

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
    t = state.free_at[0]
    attended = state.attended
    total = 0
    for patient_id, weight, slack, _ in problem.rows:
        if patient_id not in attended and slack + t > 0:
            total += weight * (slack + t)
    return total


def full(problem: Problem, state: State | str) -> int:
    if state == GOAL_NODE:
        return 0
    t = state.free_at[0]
    attended = state.attended
    base = 0
    late: list[int] = []
    durations: list[int] = []
    for patient_id, weight, slack, duration in problem.rows:
        if patient_id in attended:
            continue
        durations.append(duration)
        overdue = slack + t
        if overdue >= 0:
            late.append(weight)
            base += weight * overdue
    if not late:
        return base
    late.sort(reverse=True)
    durations.sort()
    free_at = state.free_at
    doctors = len(free_at)
    shortest = durations[0]
    extra = 0
    accumulated = 0
    level = 0
    for position, weight in enumerate(late):
        if position < doctors:
            extra += weight * min(free_at[position] - t, shortest)
            continue
        target = position // doctors
        while level < target:
            accumulated += durations[level]
            level += 1
        extra += weight * accumulated
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
