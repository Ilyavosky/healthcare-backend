from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.infra.in_memory_room_repository import InMemoryRoomRepository
from app.ports.room_repository import PatientRecord, RoomRecord
from app.services.room_service import (
    RoomService,
    SolveOptions,
    minutes_between,
    next_label,
    take_snapshot,
)

SHIFT = datetime.fromisoformat("2026-10-31T08:00:00-06:00")


def at(clock: str) -> datetime:
    return datetime.fromisoformat(f"2026-10-31T{clock}:00-06:00")


def room(doctors: int = 1) -> RoomRecord:
    return RoomRecord(uuid4(), "Sala", SHIFT, doctors, "open", SHIFT)


def patient(
    label, level, duration, arrived, attended=None, doctor=None
) -> PatientRecord:
    return PatientRecord(
        uuid4(), uuid4(), label, level, duration, arrived, attended, doctor, SHIFT
    )


def test_minutes_are_floored():
    assert minutes_between(at("08:30"), SHIFT) == 30
    assert minutes_between(SHIFT + timedelta(seconds=59), SHIFT) == 0
    assert minutes_between(SHIFT, SHIFT + timedelta(seconds=30)) == -1


def test_guide_example_t0_and_waits():
    patients = [
        patient("P1", 2, 20, at("07:55")),
        patient("P2", 3, 5, at("07:20")),
        patient("P3", 1, 30, at("08:00")),
    ]
    snapshot = take_snapshot(room(), patients, at("08:30"))
    assert snapshot.t0 == 30
    assert [(p.patient_id, p.wait) for p in snapshot.patients] == [
        ("P1", 5),
        ("P2", 40),
        ("P3", 0),
    ]
    assert snapshot.attended == frozenset()
    assert snapshot.doctors_free_at == (30,)


def test_wait_plus_t0_is_current_wait_even_when_arriving_late():
    late = patient("P1", 3, 10, at("08:10") + timedelta(seconds=30))
    snapshot = take_snapshot(room(), [late], at("08:10") + timedelta(seconds=45))
    p = snapshot.patients[0]
    assert snapshot.t0 == 10
    assert p.wait == -10
    assert p.wait_at(snapshot.t0) == 0


def test_attended_patient_keeps_doctor_busy():
    patients = [
        patient("P1", 2, 20, at("07:55"), attended=at("08:20"), doctor=2),
        patient("P2", 3, 5, at("07:20"), attended=at("08:00"), doctor=1),
        patient("P3", 1, 30, at("08:00")),
    ]
    snapshot = take_snapshot(room(doctors=3), patients, at("08:30"))
    assert snapshot.attended == frozenset({"P1", "P2"})
    assert snapshot.doctors_free_at == (30, 40, 30)


def test_latest_consultation_of_a_doctor_wins():
    patients = [
        patient("P1", 3, 10, at("08:00"), attended=at("08:00"), doctor=1),
        patient("P2", 3, 25, at("08:00"), attended=at("08:10"), doctor=1),
        patient("P3", 3, 5, at("08:00")),
    ]
    assert take_snapshot(room(), patients, at("08:15")).doctors_free_at == (35,)


def test_snapshot_ignores_the_future():
    patients = [
        patient("P1", 2, 20, at("07:55"), attended=at("09:00"), doctor=1),
        patient("P2", 3, 5, at("08:45")),
    ]
    snapshot = take_snapshot(room(), patients, at("08:30"))
    assert snapshot.attended == frozenset()
    assert [p.patient_id for p in snapshot.patients] == ["P1"]
    assert snapshot.not_arrived == ["P2"]
    assert snapshot.doctors_free_at == (30,)


def test_shift_not_started():
    with pytest.raises(DomainError) as error:
        take_snapshot(room(), [], at("07:59"))
    assert error.value.code == ErrorCode.SHIFT_NOT_STARTED


@pytest.mark.parametrize(
    "labels, expected",
    [([], "P1"), (["P1", "P2"], "P3"), (["P1", "P7", "Juan"], "P8"), (["Ana"], "P1")],
)
def test_next_label(labels, expected):
    assert next_label([patient(label, 3, 5, SHIFT) for label in labels]) == expected


@pytest.fixture
def service() -> RoomService:
    return RoomService(InMemoryRoomRepository(), lambda: at("08:30"))


def test_solve_room_saves_everything(service):
    created = service.create_room("Sala", SHIFT, 1)
    for label, level, wait, duration in [
        ("P1", 2, 5, 20),
        ("P2", 3, 40, 5),
        ("P3", 1, 0, 30),
    ]:
        service.add_patient(
            created.id, label, level, duration, SHIFT - timedelta(minutes=wait)
        )
    result = service.solve_room(
        created.id, Goal(GoalType.ALL), SolveOptions(), at("08:00")
    )
    assert result.outcome.cost == 280
    saved, results = service.get_solve(created.id, result.solve.id)
    assert saved.cost == 280
    assert saved.baseline_cost == 320
    assert saved.reference == "astar"
    assert saved.input_snapshot["t0"] == 0
    assert [r.algorithm for r in results] == ["ucs", "astar"]
    assert [s["patient_id"] for s in results[1].steps] == ["P3", "P2", "P1"]
    assert service.list_solves(created.id) == [saved]


def test_attend_requires_doctor_with_several_doctors(service):
    created = service.create_room("Sala", SHIFT, 2)
    p = service.add_patient(created.id, None, 3, 10, SHIFT)
    with pytest.raises(DomainError) as error:
        service.attend_patient(created.id, p.id, None, at("08:05"))
    assert (error.value.code, error.value.field) == (
        ErrorCode.INVALID_DOCTORS,
        "doctor",
    )
    attended = service.attend_patient(created.id, p.id, 2, at("08:05"))
    assert (attended.doctor, attended.attended_at) == (2, at("08:05"))


def test_unattend_clears_doctor(service):
    created = service.create_room("Sala", SHIFT, 1)
    p = service.add_patient(created.id, None, 3, 10, SHIFT)
    service.attend_patient(created.id, p.id, None, None)
    cleared = service.update_patient(created.id, p.id, {"attended_at": None})
    assert (cleared.attended_at, cleared.doctor) == (None, None)


def test_cannot_reduce_doctors_below_assigned(service):
    created = service.create_room("Sala", SHIFT, 3)
    p = service.add_patient(created.id, None, 3, 10, SHIFT)
    service.attend_patient(created.id, p.id, 3, at("08:10"))
    with pytest.raises(DomainError) as error:
        service.update_room(created.id, {"doctors": 2})
    assert error.value.code == ErrorCode.INVALID_DOCTORS
