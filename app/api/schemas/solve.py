from typing import Any, Literal

from pydantic import Field, StrictBool, StrictInt, field_validator
from pydantic_core import PydanticCustomError

from app.api.schemas.common import AlertOut, CamelModel, PatientIn, StepOut
from app.domain.goal import GoalType
from app.search.heuristics import AlgorithmName


class StartIn(CamelModel):
    attended: list[str] = Field(default_factory=list)
    t0: StrictInt = Field(0, ge=0)
    doctors_free_at: list[StrictInt] | None = None


class GoalIn(CamelModel):
    type: GoalType = GoalType.ALL
    value: Any = None

    @field_validator("value")
    @classmethod
    def check_value(cls, value: Any) -> int | list[str] | None:
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return [item.strip() for item in value]
        raise PydanticCustomError(
            "goal_value", "Debe ser un entero (K u horizonte) o una lista de ids"
        )


class SolveRequest(CamelModel):
    patients: list[PatientIn] = Field(min_length=1)
    start: StartIn = Field(default_factory=StartIn)
    doctors: StrictInt = Field(1, ge=1)
    goal: GoalIn = Field(default_factory=GoalIn)
    algorithms: list[AlgorithmName] = Field(
        [AlgorithmName.UCS, AlgorithmName.ASTAR], min_length=1
    )
    critical_first: StrictBool = True
    include_trace: StrictBool = False
    trace_limit: StrictInt | None = Field(None, ge=1)
    time_limit_ms: StrictInt | None = Field(None, ge=0)
    allow_approximate: StrictBool = True


class TraceChildOut(CamelModel):
    id: int
    patient: str | None
    g: int
    h: int
    f: float
    replaces: int | None = None


class TraceRowOut(CamelModel):
    id: int
    parent: int
    patient: str | None
    is_goal: bool
    g: int
    h: int
    f: float
    children: list[TraceChildOut]


class AttemptOut(CamelModel):
    weight: float
    expanded: int
    max_frontier: int
    ms: float


class AnytimeOut(CamelModel):
    node_id: int
    search_steps: int
    cost: int
    lower_bound: int
    steps: list[StepOut]
    left_out: list[StepOut]


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
    anytime: AnytimeOut | None = None


class BaselineOut(CamelModel):
    cost: int
    order: list[str]
    steps: list[StepOut]
    left_out: list[StepOut]
    alerts: list[AlertOut]


class SolveResponse(CamelModel):
    reference: str
    reference_kind: Literal["optimal", "approximate", "anytime", "baseline"]
    cost: int
    doctors: int
    results: dict[str, AlgorithmResultOut]
    baseline: BaselineOut
    same_cost: bool | None
    reduction_pct: dict[str, float]
    baseline_gap_pct: float | None
    alerts: list[AlertOut]
