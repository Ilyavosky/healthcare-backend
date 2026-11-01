from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt

from app.api.schemas.common import CamelModel, StepOut
from app.api.schemas.solve import AttemptOut, GoalIn, ProblemOut, SolveResponse
from app.search.heuristics import AlgorithmName

RoomStatus = Literal["open", "closed"]


MAX_ROOM_DOCTORS = 32767


class RoomCreate(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    shift_started_at: AwareDatetime | None = None
    doctors: StrictInt = Field(1, ge=1, le=MAX_ROOM_DOCTORS)


class RoomUpdate(CamelModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    shift_started_at: AwareDatetime | None = None
    doctors: StrictInt | None = Field(None, ge=1, le=MAX_ROOM_DOCTORS)
    status: RoomStatus | None = None


class RoomOut(CamelModel):
    id: UUID
    name: str
    shift_started_at: datetime
    doctors: int
    status: RoomStatus
    created_at: datetime


class PatientCreate(CamelModel):
    label: str | None = Field(None, min_length=1, max_length=40)
    level: StrictInt = Field(ge=1, le=5)
    duration_min: StrictInt = Field(gt=0)
    arrived_at: AwareDatetime | None = None


class PatientUpdate(CamelModel):
    label: str | None = Field(None, min_length=1, max_length=40)
    level: StrictInt | None = Field(None, ge=1, le=5)
    duration_min: StrictInt | None = Field(None, gt=0)
    arrived_at: AwareDatetime | None = None
    attended_at: AwareDatetime | None = None
    doctor: StrictInt | None = Field(None, ge=1)


class AttendRequest(CamelModel):
    doctor: StrictInt | None = Field(None, ge=1)
    at: AwareDatetime | None = None


class PatientOut(CamelModel):
    id: UUID
    label: str
    level: int
    duration_min: int
    arrived_at: datetime
    attended_at: datetime | None
    doctor: int | None
    created_at: datetime


class SnapshotPatientOut(CamelModel):
    id: str
    level: int
    wait: int
    duration: int
    attended: bool
    waiting_now: int
    limit: int
    minutes_to_limit: int


class SnapshotOut(CamelModel):
    at: datetime
    t0: int
    doctors_free_at: list[int]
    patients: list[SnapshotPatientOut]
    not_arrived: list[str]


class RoomDetailOut(RoomOut):
    patients: list[PatientOut]
    snapshot: SnapshotOut | None


class RoomSolveRequest(CamelModel):
    goal: GoalIn = Field(default_factory=GoalIn)
    algorithms: list[AlgorithmName] = Field(
        default_factory=lambda: [AlgorithmName.UCS, AlgorithmName.ASTAR], min_length=1
    )
    critical_first: StrictBool = True
    include_trace: StrictBool = False
    time_limit_ms: StrictInt | None = Field(None, ge=0)
    allow_approximate: StrictBool = True
    at: AwareDatetime | None = None


class RoomSolveResponse(SolveResponse):
    solve_id: UUID
    room_id: UUID
    computed_at: datetime
    t0: int
    doctors_free_at: list[int]
    not_arrived: list[str]
    problem: ProblemOut


class SolveSummaryOut(CamelModel):
    id: UUID
    computed_at: datetime
    created_at: datetime
    t0: int
    doctors: int
    critical_first: bool
    goal_type: str
    goal_value: Any
    reference: str
    cost: int
    baseline_cost: int
    same_cost: bool | None
    baseline_gap_pct: float | None


class StoredAlertOut(CamelModel):
    patient: str
    code: str
    minutes: int


class StoredResultOut(CamelModel):
    algorithm: str
    status: str
    weight: float
    cost: int | None
    expanded: int | None
    max_frontier: int | None
    ms: float | None
    reopened: int | None
    steps: list[StepOut]
    left_out: list[StepOut]
    limit_attempts: list[AttemptOut]


class SolveDetailOut(SolveSummaryOut):
    doctors_free_at: list[int]
    input_snapshot: dict[str, Any]
    baseline_order: list[str]
    alerts: list[StoredAlertOut]
    results: list[StoredResultOut]
