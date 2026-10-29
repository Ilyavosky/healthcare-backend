from dataclasses import dataclass
from enum import Enum

from app.domain.errors import DomainError, ErrorCode


class GoalType(str, Enum):
    ALL = "all"
    CRITICAL = "critical"
    K = "k"
    HORIZON = "horizon"
    SUBSET = "subset"


@dataclass(frozen=True)
class Goal:
    type: GoalType
    value: int | frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.type in (GoalType.ALL, GoalType.CRITICAL) and self.value is not None:
            raise DomainError(
                ErrorCode.INVALID_GOAL_VALUE, "Valor de meta invalido", "goal.value"
            )
        if self.type == GoalType.K:
            if (
                not isinstance(self.value, int)
                or isinstance(self.value, bool)
                or self.value < 1
            ):
                raise DomainError(
                    ErrorCode.INVALID_GOAL_VALUE,
                    "K debe ser un entero mayor o igual a 1",
                    "goal.value",
                )
        if self.type == GoalType.HORIZON:
            if (
                not isinstance(self.value, int)
                or isinstance(self.value, bool)
                or self.value <= 0
            ):
                raise DomainError(
                    ErrorCode.INVALID_GOAL_VALUE,
                    "El horizonte debe ser un entero mayor que 0",
                    "goal.value",
                )
        if self.type == GoalType.SUBSET:
            if not isinstance(self.value, frozenset) or not self.value:
                raise DomainError(
                    ErrorCode.INVALID_GOAL_VALUE,
                    "El subconjunto debe tener al menos un paciente",
                    "goal.value",
                )
