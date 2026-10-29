from dataclasses import dataclass

from app.domain.constants import LEVEL_LIMITS, LEVEL_WEIGHTS, MAX_LEVEL, MIN_LEVEL
from app.domain.errors import DomainError, ErrorCode


@dataclass(frozen=True)
class Patient:
    patient_id: str
    level: int
    wait: int
    duration: int

    def __post_init__(self) -> None:
        if self.level < MIN_LEVEL or self.level > MAX_LEVEL:
            raise DomainError(
                ErrorCode.INVALID_PATIENT,
                f"El nivel debe estar entre {MIN_LEVEL} y {MAX_LEVEL}",
                "level",
            )
        if self.duration <= 0:
            raise DomainError(
                ErrorCode.INVALID_PATIENT,
                "La duración debe ser mayor que 0",
                "duration",
            )

    @property
    def weight(self) -> int:
        return LEVEL_WEIGHTS[self.level]

    @property
    def limit(self) -> int:
        return LEVEL_LIMITS[self.level]

    def wait_at(self, t: int) -> int:
        return self.wait + t

    def delay_at(self, t: int) -> int:
        return max(0, self.wait_at(t) - self.limit)

    def penalty_at(self, t: int) -> int:
        return self.weight * self.delay_at(t)

    def is_late_at(self, t: int) -> bool:
        return self.wait_at(t) >= self.limit
