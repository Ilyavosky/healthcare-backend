from collections.abc import Callable
from dataclasses import asdict, fields
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from postgrest.exceptions import APIError
from supabase import Client

from app.domain.errors import DomainError, ErrorCode
from app.ports.room_repository import (
    NewSolve,
    NewSolveResult,
    PatientRecord,
    RoomRecord,
    SolveRecord,
    SolveResultRecord,
)

UNIQUE_VIOLATION = "23505"
ROOMS = "rooms"
PATIENTS = "patients"
SOLVES = "solves"
SOLVE_RESULTS = "solve_results"


class SupabaseRoomRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def create_room(
        self, name: str, shift_started_at: datetime, doctors: int
    ) -> RoomRecord:
        row = {
            "name": name,
            "shift_started_at": shift_started_at.isoformat(),
            "doctors": doctors,
        }
        data = self._run(lambda: self.client.table(ROOMS).insert(row).execute())
        return _room(data[0])

    def list_rooms(self) -> list[RoomRecord]:
        data = self._run(
            lambda: (
                self.client.table(ROOMS)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
        )
        return [_room(row) for row in data]

    def get_room(self, room_id: UUID) -> RoomRecord | None:
        data = self._run(
            lambda: (
                self.client.table(ROOMS)
                .select("*")
                .eq("id", str(room_id))
                .limit(1)
                .execute()
            )
        )
        return _room(data[0]) if data else None

    def update_room(self, room_id: UUID, changes: dict[str, Any]) -> RoomRecord | None:
        data = self._run(
            lambda: (
                self.client.table(ROOMS)
                .update(_serialize(changes))
                .eq("id", str(room_id))
                .execute()
            )
        )
        return _room(data[0]) if data else None

    def delete_room(self, room_id: UUID) -> bool:
        data = self._run(
            lambda: self.client.table(ROOMS).delete().eq("id", str(room_id)).execute()
        )
        return bool(data)

    def list_patients(self, room_id: UUID) -> list[PatientRecord]:
        data = self._run(
            lambda: (
                self.client.table(PATIENTS)
                .select("*")
                .eq("room_id", str(room_id))
                .order("created_at")
                .execute()
            )
        )
        return [_patient(row) for row in data]

    def get_patient(self, room_id: UUID, patient_id: UUID) -> PatientRecord | None:
        data = self._run(
            lambda: (
                self.client.table(PATIENTS)
                .select("*")
                .eq("room_id", str(room_id))
                .eq("id", str(patient_id))
                .limit(1)
                .execute()
            )
        )
        return _patient(data[0]) if data else None

    def add_patient(
        self,
        room_id: UUID,
        label: str,
        level: int,
        duration_min: int,
        arrived_at: datetime,
    ) -> PatientRecord:
        row = {
            "room_id": str(room_id),
            "label": label,
            "level": level,
            "duration_min": duration_min,
            "arrived_at": arrived_at.isoformat(),
        }
        data = self._run(
            lambda: self.client.table(PATIENTS).insert(row).execute(), label
        )
        return _patient(data[0])

    def update_patient(
        self, room_id: UUID, patient_id: UUID, changes: dict[str, Any]
    ) -> PatientRecord | None:
        data = self._run(
            lambda: (
                self.client.table(PATIENTS)
                .update(_serialize(changes))
                .eq("room_id", str(room_id))
                .eq("id", str(patient_id))
                .execute()
            ),
            changes.get("label"),
        )
        return _patient(data[0]) if data else None

    def delete_patient(self, room_id: UUID, patient_id: UUID) -> bool:
        data = self._run(
            lambda: (
                self.client.table(PATIENTS)
                .delete()
                .eq("room_id", str(room_id))
                .eq("id", str(patient_id))
                .execute()
            )
        )
        return bool(data)

    def save_solve(self, solve: NewSolve, results: list[NewSolveResult]) -> SolveRecord:
        row = _serialize(asdict(solve))
        data = self._run(lambda: self.client.table(SOLVES).insert(row).execute())
        record = _solve(data[0])
        rows = [
            {**_serialize(asdict(result)), "solve_id": str(record.id)}
            for result in results
        ]
        try:
            if rows:
                self._run(
                    lambda: self.client.table(SOLVE_RESULTS).insert(rows).execute()
                )
        except DomainError:
            self._run(
                lambda: (
                    self.client.table(SOLVES)
                    .delete()
                    .eq("id", str(record.id))
                    .execute()
                )
            )
            raise
        return record

    def list_solves(self, room_id: UUID) -> list[SolveRecord]:
        data = self._run(
            lambda: (
                self.client.table(SOLVES)
                .select("*")
                .eq("room_id", str(room_id))
                .order("created_at", desc=True)
                .execute()
            )
        )
        return [_solve(row) for row in data]

    def get_solve(
        self, room_id: UUID, solve_id: UUID
    ) -> tuple[SolveRecord, list[SolveResultRecord]] | None:
        data = self._run(
            lambda: (
                self.client.table(SOLVES)
                .select("*")
                .eq("room_id", str(room_id))
                .eq("id", str(solve_id))
                .limit(1)
                .execute()
            )
        )
        if not data:
            return None
        results = self._run(
            lambda: (
                self.client.table(SOLVE_RESULTS)
                .select("*")
                .eq("solve_id", str(solve_id))
                .execute()
            )
        )
        return _solve(data[0]), [_result(row) for row in results]

    def _run(
        self, call: Callable[[], Any], label: str | None = None
    ) -> list[dict[str, Any]]:
        try:
            response = call()
        except APIError as error:
            if error.code == UNIQUE_VIOLATION:
                raise DomainError(
                    ErrorCode.DUPLICATE_LABEL,
                    f"Ya hay un paciente {label} en esta sala"
                    if label
                    else "Registro duplicado",
                    "label",
                ) from error
            raise DomainError(
                ErrorCode.DATABASE_ERROR, "La base de datos rechazó la operación"
            ) from error
        except httpx.HTTPError as error:
            raise DomainError(
                ErrorCode.DATABASE_ERROR, "No se pudo conectar con la base de datos"
            ) from error
        return list(response.data or [])


def _serialize(values: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in values.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, UUID):
            out[key] = str(value)
        else:
            out[key] = value
    return out


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _room(row: dict[str, Any]) -> RoomRecord:
    return RoomRecord(
        id=UUID(row["id"]),
        name=row["name"],
        shift_started_at=_datetime(row["shift_started_at"]),
        doctors=int(row["doctors"]),
        status=row["status"],
        created_at=_datetime(row["created_at"]),
    )


def _patient(row: dict[str, Any]) -> PatientRecord:
    return PatientRecord(
        id=UUID(row["id"]),
        room_id=UUID(row["room_id"]),
        label=row["label"],
        level=int(row["level"]),
        duration_min=int(row["duration_min"]),
        arrived_at=_datetime(row["arrived_at"]),
        attended_at=_datetime(row["attended_at"]),
        doctor=row["doctor"],
        created_at=_datetime(row["created_at"]),
    )


def _solve(row: dict[str, Any]) -> SolveRecord:
    values = {f.name: row.get(f.name) for f in fields(SolveRecord)}
    values["id"] = UUID(row["id"])
    values["room_id"] = UUID(row["room_id"])
    values["computed_at"] = _datetime(row["computed_at"])
    values["created_at"] = _datetime(row["created_at"])
    values["baseline_gap_pct"] = _number(row.get("baseline_gap_pct"))
    return SolveRecord(**values)


def _result(row: dict[str, Any]) -> SolveResultRecord:
    values = {f.name: row.get(f.name) for f in fields(SolveResultRecord)}
    values["id"] = UUID(row["id"])
    values["solve_id"] = UUID(row["solve_id"])
    values["weight"] = _number(row.get("weight"))
    values["elapsed_ms"] = _number(row.get("elapsed_ms"))
    return SolveResultRecord(**values)


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None
