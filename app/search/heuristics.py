from collections.abc import Callable
from enum import Enum

from app.domain.problem import Problem, State

Heuristic = Callable[[Problem, State | str], int]


class AlgorithmName(str, Enum):
    UCS = "ucs"


def zero(problem: Problem, state: State | str) -> int:
    return 0


HEURISTICS: dict[AlgorithmName, Heuristic] = {
    AlgorithmName.UCS: zero,
}
