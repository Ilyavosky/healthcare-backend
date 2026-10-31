from typing import Literal

from pydantic import Field

from app.api.schemas.common import AlertOut, CamelModel, PatientIn, StepOut
from app.domain.goal import GoalType
from app.search.heuristics import AlgorithmName


class StartIn(CamelModel):
    attended: list[str] = Field(default_factory=list)
    t0: int = Field(0, ge=0)
    doctors_free_at: list[int] | None = None


class GoalIn(CamelModel):
    type: GoalType = GoalType.ALL
    value: int | list[str] | None = None


class SolveRequest(CamelModel):
    patients: list[PatientIn] = Field(min_length=1)
    start: StartIn = Field(default_factory=StartIn)
    doctors: int = Field(1, ge=1)
    goal: GoalIn = Field(default_factory=GoalIn)
    algorithms: list[AlgorithmName] = Field(
        [AlgorithmName.UCS, AlgorithmName.ASTAR], min_length=1
    )
    critical_first: bool = True
    include_trace: bool = False
    time_limit_ms: int | None = Field(None, ge=0)
    allow_approximate: bool = True


class TraceRowOut(CamelModel):
    attended: list[str] | None
    free_at: list[int] | None
    is_goal: bool
    g: int
    h: int
    f: float


class AttemptOut(CamelModel):
    weight: float
    expanded: int
    max_frontier: int
    ms: float


class AlgorithmResultOut(CamelModel):
    status: Literal["optimal", "approximate", "limit_reached"]
    weight: float
    cost: int | None
    closing_cost: int | None
    expanded: int | None
    max_frontier: int | None
    ms: float | None
    reopened: int | None
    steps: list[StepOut]
    left_out: list[StepOut]
    trace: list[TraceRowOut]
    limit_attempts: list[AttemptOut]


class BaselineOut(CamelModel):
    cost: int
    order: list[str]
    steps: list[StepOut]
    left_out: list[StepOut]


class SolveResponse(CamelModel):
    reference: str
    cost: int
    doctors: int
    results: dict[str, AlgorithmResultOut]
    baseline: BaselineOut
    same_cost: bool | None
    reduction_pct: dict[str, float]
    baseline_gap_pct: float | None
    alerts: list[AlertOut]
