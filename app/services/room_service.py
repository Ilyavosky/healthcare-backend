import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal
from app.domain.patient import Patient
from app.domain.problem import Problem
from app.ports.room_repository import (
    NewSolve,
    NewSolveResult,
    PatientRecord,
    RoomRecord,
    RoomRepository,
    SolveRecord,
    SolveResultRecord,
)
from app.search.heuristics import AlgorithmName
from app.search.report import ScheduleStep
from app.services.solve_service import (
    DEFAULT_ALGORITHMS,
    AlgorithmRun,
    SolveOutcome,
    solve,
)

Clock = Callable[[], datetime]
OPEN = "open"
CLOSED = "closed"
LABEL_PATTERN = re.compile(r"^P(\d+)$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def minutes_between(later: datetime, earlier: datetime) -> int:
    return math.floor((later - earlier).total_seconds() / 60)


@dataclass(frozen=True)
class RoomSnapshot:
    now: datetime
    t0: int
    patients: list[Patient]
    attended: frozenset[str]
    doctors_free_at: tuple[int, ...]
    not_arrived: list[str]


@dataclass(frozen=True)
class RoomSolveOutcome:
    solve: SolveRecord
    snapshot: RoomSnapshot
    problem: Problem
    outcome: SolveOutcome


@dataclass(frozen=True)
class SolveOptions:
    algorithms: tuple[AlgorithmName, ...] = DEFAULT_ALGORITHMS
    critical_first: bool = True
    include_trace: bool = False
    trace_limit: int = 500
    time_limit_ms: float | None = None
    fallback_weights: tuple[float, ...] = ()


def take_snapshot(
    room: RoomRecord, patients: list[PatientRecord], now: datetime
) -> RoomSnapshot:
    t0 = minutes_between(now, room.shift_started_at)
    if t0 < 0:
        raise DomainError(
            ErrorCode.SHIFT_NOT_STARTED,
            "El turno de esta sala todavía no empieza en ese momento",
            "at",
        )
    arrived = [p for p in patients if p.arrived_at <= now]
    free_at = [t0] * room.doctors
    attended = set()
    for record in arrived:
        if record.attended_at is None or record.attended_at > now:
            continue
        attended.add(record.label)
        if record.doctor is not None and record.doctor <= room.doctors:
            end = (
                minutes_between(record.attended_at, room.shift_started_at)
                + record.duration_min
            )
            free_at[record.doctor - 1] = max(free_at[record.doctor - 1], end)
    domain_patients = [
        Patient(
            record.label,
            record.level,
            minutes_between(now, record.arrived_at) - t0,
            record.duration_min,
        )
        for record in arrived
    ]
    return RoomSnapshot(
        now=now,
        t0=t0,
        patients=domain_patients,
        attended=frozenset(attended),
        doctors_free_at=tuple(free_at),
        not_arrived=[p.label for p in patients if p.arrived_at > now],
    )


def next_label(patients: list[PatientRecord]) -> str:
    numbers = [int(m.group(1)) for p in patients if (m := LABEL_PATTERN.match(p.label))]
    return f"P{max(numbers, default=0) + 1}"


class RoomService:
    def __init__(self, repository: RoomRepository, clock: Clock = utc_now) -> None:
        self.repository = repository
        self.clock = clock

    def create_room(
        self, name: str, shift_started_at: datetime | None, doctors: int
    ) -> RoomRecord:
        return self.repository.create_room(
            name.strip(), shift_started_at or self.clock(), doctors
        )

    def list_rooms(self) -> list[RoomRecord]:
        return self.repository.list_rooms()

    def get_room(self, room_id: UUID) -> tuple[RoomRecord, list[PatientRecord]]:
        room = self._room(room_id)
        return room, self.repository.list_patients(room_id)

    def update_room(self, room_id: UUID, changes: dict[str, Any]) -> RoomRecord:
        room = self._room(room_id)
        if "name" in changes:
            changes["name"] = changes["name"].strip()
        if "doctors" in changes:
            busy = [
                p.doctor
                for p in self.repository.list_patients(room_id)
                if p.doctor is not None and p.doctor > changes["doctors"]
            ]
            if busy:
                raise DomainError(
                    ErrorCode.INVALID_DOCTORS,
                    f"Hay pacientes asignados al médico {max(busy)}",
                    "doctors",
                )
        if not changes:
            return room
        return self.repository.update_room(room_id, changes) or self._missing_room()

    def delete_room(self, room_id: UUID) -> None:
        if not self.repository.delete_room(room_id):
            self._missing_room()

    def add_patient(
        self,
        room_id: UUID,
        label: str | None,
        level: int,
        duration_min: int,
        arrived_at: datetime | None,
    ) -> PatientRecord:
        room = self._open_room(room_id)
        clean = (
            label.strip()
            if label
            else next_label(self.repository.list_patients(room.id))
        )
        return self.repository.add_patient(
            room.id, clean, level, duration_min, arrived_at or self.clock()
        )

    def update_patient(
        self, room_id: UUID, patient_id: UUID, changes: dict[str, Any]
    ) -> PatientRecord:
        room = self._open_room(room_id)
        patient = self._patient(room_id, patient_id)
        if "label" in changes:
            changes["label"] = changes["label"].strip()
        if changes.get("attended_at", patient.attended_at) is None:
            if changes.get("doctor") is not None:
                raise DomainError(
                    ErrorCode.INVALID_DOCTORS,
                    "Solo se asigna médico a un paciente atendido",
                    "doctor",
                )
            if "attended_at" in changes:
                changes["doctor"] = None
        elif "attended_at" in changes and changes.get("doctor", patient.doctor) is None:
            changes["doctor"] = self._default_doctor(room)
        self._check_attention(room, patient, changes)
        if not changes:
            return patient
        return (
            self.repository.update_patient(room_id, patient_id, changes)
            or self._missing_patient()
        )

    def attend_patient(
        self, room_id: UUID, patient_id: UUID, doctor: int | None, at: datetime | None
    ) -> PatientRecord:
        room = self._open_room(room_id)
        changes = {
            "attended_at": at or self.clock(),
            "doctor": doctor if doctor is not None else self._default_doctor(room),
        }
        return self.update_patient(room_id, patient_id, changes)

    def delete_patient(self, room_id: UUID, patient_id: UUID) -> None:
        self._open_room(room_id)
        if not self.repository.delete_patient(room_id, patient_id):
            self._missing_patient()

    def snapshot(self, room_id: UUID, at: datetime | None = None) -> RoomSnapshot:
        room, patients = self.get_room(room_id)
        return take_snapshot(room, patients, at or self.clock())

    def solve_room(
        self,
        room_id: UUID,
        goal: Goal,
        options: SolveOptions,
        at: datetime | None = None,
    ) -> RoomSolveOutcome:
        room = self._open_room(room_id)
        snapshot = take_snapshot(
            room, self.repository.list_patients(room_id), at or self.clock()
        )
        problem = Problem(
            snapshot.patients,
            goal,
            snapshot.attended,
            snapshot.t0,
            doctors=room.doctors,
            doctors_free_at=snapshot.doctors_free_at,
            critical_first=options.critical_first,
        )
        outcome = solve(
            problem,
            options.algorithms,
            include_trace=options.include_trace,
            trace_limit=options.trace_limit,
            time_limit_ms=options.time_limit_ms,
            fallback_weights=options.fallback_weights,
        )
        record = self.repository.save_solve(
            _new_solve(room, snapshot, goal, options, outcome),
            [_new_result(run) for run in outcome.runs.values()],
        )
        return RoomSolveOutcome(record, snapshot, problem, outcome)

    def list_solves(self, room_id: UUID) -> list[SolveRecord]:
        self._room(room_id)
        return self.repository.list_solves(room_id)

    def get_solve(
        self, room_id: UUID, solve_id: UUID
    ) -> tuple[SolveRecord, list[SolveResultRecord]]:
        self._room(room_id)
        found = self.repository.get_solve(room_id, solve_id)
        if found is None:
            raise DomainError(
                ErrorCode.SOLVE_NOT_FOUND, "No existe esa corrida", "solveId"
            )
        return found

    def _room(self, room_id: UUID) -> RoomRecord:
        return self.repository.get_room(room_id) or self._missing_room()

    def _open_room(self, room_id: UUID) -> RoomRecord:
        room = self._room(room_id)
        if room.status != OPEN:
            raise DomainError(ErrorCode.ROOM_CLOSED, "La sala está cerrada", "status")
        return room

    def _patient(self, room_id: UUID, patient_id: UUID) -> PatientRecord:
        return (
            self.repository.get_patient(room_id, patient_id) or self._missing_patient()
        )

    def _default_doctor(self, room: RoomRecord) -> int:
        if room.doctors == 1:
            return 1
        raise DomainError(
            ErrorCode.INVALID_DOCTORS,
            f"Indica qué médico lo atiende (1 a {room.doctors})",
            "doctor",
        )

    def _check_attention(
        self, room: RoomRecord, patient: PatientRecord, changes: dict[str, Any]
    ) -> None:
        doctor = changes.get("doctor", patient.doctor)
        if doctor is not None and doctor > room.doctors:
            raise DomainError(
                ErrorCode.INVALID_DOCTORS,
                f"La sala tiene {room.doctors} médico(s)",
                "doctor",
            )
        attended_at = changes.get("attended_at", patient.attended_at)
        arrived_at = changes.get("arrived_at", patient.arrived_at)
        if attended_at is not None and attended_at < arrived_at:
            raise DomainError(
                ErrorCode.INVALID_PATIENT,
                "La atención no puede empezar antes de la llegada",
                "attended_at",
            )

    @staticmethod
    def _missing_room() -> RoomRecord:
        raise DomainError(ErrorCode.ROOM_NOT_FOUND, "No existe esa sala", "roomId")

    @staticmethod
    def _missing_patient() -> PatientRecord:
        raise DomainError(
            ErrorCode.PATIENT_NOT_FOUND, "No existe ese paciente", "patientId"
        )


def step_record(step: ScheduleStep) -> dict[str, Any]:
    return {
        "patient_id": step.patient_id,
        "level": step.level,
        "doctor": step.doctor,
        "start": step.start,
        "end": step.end,
        "delay": step.delay,
        "penalty": step.penalty,
        "after_goal": step.after_goal,
    }


def _goal_value(goal: Goal) -> Any:
    if isinstance(goal.value, frozenset):
        return sorted(goal.value)
    return goal.value


def _new_solve(
    room: RoomRecord,
    snapshot: RoomSnapshot,
    goal: Goal,
    options: SolveOptions,
    outcome: SolveOutcome,
) -> NewSolve:
    return NewSolve(
        room_id=room.id,
        computed_at=snapshot.now,
        t0_min=snapshot.t0,
        doctors=room.doctors,
        doctors_free_at=list(snapshot.doctors_free_at),
        critical_first=options.critical_first,
        goal_type=goal.type.value,
        goal_value=_goal_value(goal),
        input_snapshot={
            "patients": [
                {
                    "id": p.patient_id,
                    "level": p.level,
                    "wait": p.wait,
                    "duration": p.duration,
                }
                for p in snapshot.patients
            ],
            "attended": sorted(snapshot.attended),
            "t0": snapshot.t0,
            "doctorsFreeAt": list(snapshot.doctors_free_at),
            "notArrived": snapshot.not_arrived,
        },
        reference=outcome.reference.value
        if outcome.reference is not None
        else "baseline",
        cost=outcome.cost,
        baseline_cost=outcome.baseline.cost,
        baseline_order=outcome.baseline.order,
        same_cost=outcome.same_cost,
        baseline_gap_pct=outcome.baseline_gap_pct,
        alerts=[
            {"patient_id": a.patient_id, "code": a.code.value, "minutes": a.minutes}
            for a in outcome.alerts
        ],
    )


def _new_result(run: AlgorithmRun) -> NewSolveResult:
    attempts = [
        {
            "weight": limit.weight,
            "expanded": limit.expanded,
            "max_frontier": limit.max_frontier,
            "elapsed_ms": round(limit.elapsed_ms, 2),
        }
        for limit in run.limits
    ]
    if not run.finished:
        return NewSolveResult(
            run.name.value,
            "limit_reached",
            run.weight,
            None,
            None,
            None,
            None,
            None,
            [],
            [],
            attempts,
        )
    return NewSolveResult(
        algorithm=run.name.value,
        status="optimal" if run.optimal else "approximate",
        weight=run.weight,
        cost=run.result.cost,
        expanded=run.result.expanded,
        max_frontier=run.result.max_frontier,
        elapsed_ms=round(run.result.elapsed_ms, 2),
        reopened=run.result.reopened,
        steps=[step_record(s) for s in run.schedule.steps],
        left_out=[step_record(s) for s in run.schedule.left_out],
        limit_attempts=attempts,
    )
