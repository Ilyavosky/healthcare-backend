from datetime import datetime
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.infra.supabase_room_repository import SupabaseRoomRepository
from app.services.room_service import RoomService, SolveOptions
from tests.infra.fake_supabase import FakeSupabase, network_error

SHIFT = datetime.fromisoformat("2026-10-31T08:00:00-06:00")


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def repo(db) -> SupabaseRoomRepository:
    return SupabaseRoomRepository(db)


def test_rooms_round_trip(repo, db):
    room = repo.create_room("Sala", SHIFT, 2)
    assert db.tables["rooms"][0]["shift_started_at"] == "2026-10-31T08:00:00-06:00"
    assert room.shift_started_at == SHIFT
    assert room.status == "open"
    assert repo.get_room(room.id) == room
    assert repo.list_rooms() == [room]
    assert repo.get_room(uuid4()) is None
    updated = repo.update_room(room.id, {"status": "closed", "doctors": 3})
    assert (updated.status, updated.doctors) == ("closed", 3)
    assert repo.update_room(uuid4(), {"status": "open"}) is None


def test_patients_round_trip(repo):
    room = repo.create_room("Sala", SHIFT, 1)
    p = repo.add_patient(room.id, "P1", 2, 20, SHIFT)
    assert (p.label, p.level, p.duration_min, p.attended_at, p.doctor) == (
        "P1",
        2,
        20,
        None,
        None,
    )
    assert repo.get_patient(room.id, p.id) == p
    assert repo.get_patient(uuid4(), p.id) is None
    attended = repo.update_patient(room.id, p.id, {"attended_at": SHIFT, "doctor": 1})
    assert (attended.attended_at, attended.doctor) == (SHIFT, 1)
    assert repo.list_patients(room.id) == [attended]
    assert repo.delete_patient(room.id, p.id) is True
    assert repo.delete_patient(room.id, p.id) is False


def test_duplicate_label_becomes_domain_error(repo):
    room = repo.create_room("Sala", SHIFT, 1)
    repo.add_patient(room.id, "P1", 2, 20, SHIFT)
    with pytest.raises(DomainError) as error:
        repo.add_patient(room.id, "P1", 3, 5, SHIFT)
    assert error.value.code == ErrorCode.DUPLICATE_LABEL
    assert error.value.message == "Ya hay un paciente P1 en esta sala"
    other = repo.add_patient(room.id, "P2", 3, 5, SHIFT)
    with pytest.raises(DomainError):
        repo.update_patient(room.id, other.id, {"label": "P1"})


def test_other_api_errors_and_network(repo, db):
    db.fail_with = APIError({"code": "42501", "message": "permission denied"})
    with pytest.raises(DomainError) as error:
        repo.list_rooms()
    assert error.value.code == ErrorCode.DATABASE_ERROR
    db.fail_with = network_error()
    with pytest.raises(DomainError) as error:
        repo.list_rooms()
    assert error.value.message == "No se pudo conectar con la base de datos"


def test_delete_room_cascades(repo, db):
    room = repo.create_room("Sala", SHIFT, 1)
    repo.add_patient(room.id, "P1", 2, 20, SHIFT)
    assert repo.delete_room(room.id) is True
    assert db.tables["patients"] == []
    assert repo.delete_room(room.id) is False


@pytest.fixture
def solved(repo):
    service = RoomService(repo, lambda: SHIFT)
    room = service.create_room("Sala", SHIFT, 1)
    for label, level, wait, duration in [
        ("P1", 2, 5, 20),
        ("P2", 3, 40, 5),
        ("P3", 1, 0, 30),
    ]:
        service.add_patient(
            room.id,
            label,
            level,
            duration,
            datetime.fromtimestamp(SHIFT.timestamp() - wait * 60, SHIFT.tzinfo),
        )
    result = service.solve_room(
        room.id, Goal(GoalType.SUBSET, frozenset({"P2"})), SolveOptions()
    )
    return service, room, result


def test_save_and_read_solve(repo, solved, db):
    _, room, result = solved
    row = db.tables["solves"][0]
    assert row["computed_at"] == "2026-10-31T08:00:00-06:00"
    assert row["goal_value"] == ["P2"]
    assert row["doctors_free_at"] == [0]
    assert isinstance(row["room_id"], str)
    solve, results = repo.get_solve(room.id, result.solve.id)
    assert solve == result.solve
    assert solve.cost == result.outcome.cost
    assert {r.algorithm for r in results} == {"ucs", "astar"}
    assert all(r.solve_id == solve.id for r in results)
    assert repo.list_solves(room.id) == [solve]
    assert repo.get_solve(uuid4(), solve.id) is None


def test_failed_results_insert_removes_the_solve(repo, db):
    room = repo.create_room("Sala", SHIFT, 1)
    repo.add_patient(room.id, "P1", 2, 20, SHIFT)
    service = RoomService(repo, lambda: SHIFT)
    db.fail_table = "solve_results"
    db.fail_with = network_error()
    with pytest.raises(DomainError):
        service.solve_room(room.id, Goal(GoalType.ALL), SolveOptions())
    assert db.tables["solves"] == []
    assert ("solves", "delete") in db.calls
