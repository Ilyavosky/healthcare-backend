from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.errors import DomainError, ErrorCode
from app.ports.room_repository import (
    NewSolve,
    NewSolveResult,
    PatientRecord,
    RoomRecord,
    SolveRecord,
    SolveResultRecord,
)


class InMemoryRoomRepository:
    def __init__(self) -> None:
        self.rooms: dict[UUID, RoomRecord] = {}
        self.patients: dict[UUID, PatientRecord] = {}
        self.solves: dict[UUID, SolveRecord] = {}
        self.results: dict[UUID, list[SolveResultRecord]] = {}

    def create_room(
        self, name: str, shift_started_at: datetime, doctors: int
    ) -> RoomRecord:
        room = RoomRecord(uuid4(), name, shift_started_at, doctors, "open", _now())
        self.rooms[room.id] = room
        return room

    def list_rooms(self) -> list[RoomRecord]:
        return list(reversed(self.rooms.values()))

    def get_room(self, room_id: UUID) -> RoomRecord | None:
        return self.rooms.get(room_id)

    def update_room(self, room_id: UUID, changes: dict[str, Any]) -> RoomRecord | None:
        room = self.rooms.get(room_id)
        if room is None:
            return None
        self.rooms[room_id] = replace(room, **changes)
        return self.rooms[room_id]

    def delete_room(self, room_id: UUID) -> bool:
        if self.rooms.pop(room_id, None) is None:
            return False
        for patient_id in [
            p.id for p in self.patients.values() if p.room_id == room_id
        ]:
            del self.patients[patient_id]
        for solve_id in [s.id for s in self.solves.values() if s.room_id == room_id]:
            del self.solves[solve_id]
            self.results.pop(solve_id, None)
        return True

    def list_patients(self, room_id: UUID) -> list[PatientRecord]:
        return [p for p in self.patients.values() if p.room_id == room_id]

    def get_patient(self, room_id: UUID, patient_id: UUID) -> PatientRecord | None:
        patient = self.patients.get(patient_id)
        return patient if patient is not None and patient.room_id == room_id else None

    def add_patient(
        self,
        room_id: UUID,
        label: str,
        level: int,
        duration_min: int,
        arrived_at: datetime,
    ) -> PatientRecord:
        self._check_label(room_id, label, None)
        patient = PatientRecord(
            uuid4(), room_id, label, level, duration_min, arrived_at, None, None, _now()
        )
        self.patients[patient.id] = patient
        return patient

    def update_patient(
        self, room_id: UUID, patient_id: UUID, changes: dict[str, Any]
    ) -> PatientRecord | None:
        patient = self.get_patient(room_id, patient_id)
        if patient is None:
            return None
        if "label" in changes:
            self._check_label(room_id, changes["label"], patient_id)
        self.patients[patient_id] = replace(patient, **changes)
        return self.patients[patient_id]

    def delete_patient(self, room_id: UUID, patient_id: UUID) -> bool:
        if self.get_patient(room_id, patient_id) is None:
            return False
        del self.patients[patient_id]
        return True

    def save_solve(self, solve: NewSolve, results: list[NewSolveResult]) -> SolveRecord:
        record = SolveRecord(**asdict(solve), id=uuid4(), created_at=_now())
        self.solves[record.id] = record
        self.results[record.id] = [
            SolveResultRecord(**asdict(result), id=uuid4(), solve_id=record.id)
            for result in results
        ]
        return record

    def list_solves(self, room_id: UUID) -> list[SolveRecord]:
        return [s for s in reversed(self.solves.values()) if s.room_id == room_id]

    def get_solve(
        self, room_id: UUID, solve_id: UUID
    ) -> tuple[SolveRecord, list[SolveResultRecord]] | None:
        solve = self.solves.get(solve_id)
        if solve is None or solve.room_id != room_id:
            return None
        return solve, self.results[solve_id]

    def _check_label(self, room_id: UUID, label: str, patient_id: UUID | None) -> None:
        for p in self.patients.values():
            if p.room_id == room_id and p.label == label and p.id != patient_id:
                raise DomainError(
                    ErrorCode.DUPLICATE_LABEL,
                    f"Ya hay un paciente {label} en esta sala",
                    "label",
                )


def _now() -> datetime:
    return datetime.now(UTC)
