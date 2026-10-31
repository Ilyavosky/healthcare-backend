from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class RoomRecord:
    id: UUID
    name: str
    shift_started_at: datetime
    doctors: int
    status: str
    created_at: datetime


@dataclass(frozen=True)
class PatientRecord:
    id: UUID
    room_id: UUID
    label: str
    level: int
    duration_min: int
    arrived_at: datetime
    attended_at: datetime | None
    doctor: int | None
    created_at: datetime


@dataclass(frozen=True)
class NewSolve:
    room_id: UUID
    computed_at: datetime
    t0_min: int
    doctors: int
    doctors_free_at: list[int]
    critical_first: bool
    goal_type: str
    goal_value: Any
    input_snapshot: dict[str, Any]
    reference: str
    cost: int
    baseline_cost: int
    baseline_order: list[str]
    same_cost: bool | None
    baseline_gap_pct: float | None
    alerts: list[dict[str, Any]]


@dataclass(frozen=True)
class NewSolveResult:
    algorithm: str
    status: str
    weight: float
    cost: int | None
    expanded: int | None
    max_frontier: int | None
    elapsed_ms: float | None
    reopened: int | None
    steps: list[dict[str, Any]]
    left_out: list[dict[str, Any]]
    limit_attempts: list[dict[str, Any]]


@dataclass(frozen=True)
class SolveRecord(NewSolve):
    id: UUID
    created_at: datetime


@dataclass(frozen=True)
class SolveResultRecord(NewSolveResult):
    id: UUID
    solve_id: UUID


class RoomRepository(Protocol):
    def create_room(
        self, name: str, shift_started_at: datetime, doctors: int
    ) -> RoomRecord: ...

    def list_rooms(self) -> list[RoomRecord]: ...

    def get_room(self, room_id: UUID) -> RoomRecord | None: ...

    def update_room(
        self, room_id: UUID, changes: dict[str, Any]
    ) -> RoomRecord | None: ...

    def delete_room(self, room_id: UUID) -> bool: ...

    def list_patients(self, room_id: UUID) -> list[PatientRecord]: ...

    def get_patient(self, room_id: UUID, patient_id: UUID) -> PatientRecord | None: ...

    def add_patient(
        self,
        room_id: UUID,
        label: str,
        level: int,
        duration_min: int,
        arrived_at: datetime,
    ) -> PatientRecord: ...

    def update_patient(
        self, room_id: UUID, patient_id: UUID, changes: dict[str, Any]
    ) -> PatientRecord | None: ...

    def delete_patient(self, room_id: UUID, patient_id: UUID) -> bool: ...

    def save_solve(
        self, solve: NewSolve, results: list[NewSolveResult]
    ) -> SolveRecord: ...

    def list_solves(self, room_id: UUID) -> list[SolveRecord]: ...

    def get_solve(
        self, room_id: UUID, solve_id: UUID
    ) -> tuple[SolveRecord, list[SolveResultRecord]] | None: ...
