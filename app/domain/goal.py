from dataclasses import dataclass
from enum import Enum

from app.domain.errors import DomainError, ErrorCode


class GoalType(str, Enum):
    ALL = "all"
    CRITICAL = "critical"
    K = "k"
    HORIZON = "horizon"
    SUBSET = "subset"


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Goal:
    type: GoalType
    value: int | frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.type in (GoalType.ALL, GoalType.CRITICAL) and self.value is not None:
            self._invalid("Esta meta no lleva valor")
        if self.type == GoalType.K and not (is_int(self.value) and self.value >= 1):
            self._invalid("K debe ser un entero mayor o igual a 1")
        if self.type == GoalType.HORIZON and not (
            is_int(self.value) and self.value > 0
        ):
            self._invalid("El horizonte debe ser un entero mayor que 0")
        if self.type == GoalType.SUBSET and not (
            isinstance(self.value, frozenset) and self.value
        ):
            self._invalid("El subconjunto debe tener al menos un paciente")

    @staticmethod
    def _invalid(message: str) -> None:
        raise DomainError(ErrorCode.INVALID_GOAL_VALUE, message, "goal.value")
