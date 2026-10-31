from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_clock, get_room_repository
from app.config import Settings
from app.infra.in_memory_room_repository import InMemoryRoomRepository
from app.main import create_app

NOW = datetime.fromisoformat("2026-10-31T08:30:00-06:00")
SHIFT = "2026-10-31T08:00:00-06:00"


@pytest.fixture
def repository() -> InMemoryRoomRepository:
    return InMemoryRoomRepository()


@pytest.fixture
def client(settings: Settings, repository: InMemoryRoomRepository) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_room_repository] = lambda: repository
    app.dependency_overrides[get_clock] = lambda: lambda: NOW
    return TestClient(app)


def new_room(client, doctors: int = 1, name: str = "Sala A") -> dict:
    response = client.post(
        "/api/rooms", json={"name": name, "shiftStartedAt": SHIFT, "doctors": doctors}
    )
    assert response.status_code == 201
    return response.json()


def add(client, room_id: str, **body) -> dict:
    response = client.post(f"/api/rooms/{room_id}/patients", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def guide_room(client) -> dict:
    room = new_room(client)
    add(
        client,
        room["id"],
        label="P1",
        level=2,
        durationMin=20,
        arrivedAt="2026-10-31T07:55:00-06:00",
    )
    add(
        client,
        room["id"],
        label="P2",
        level=3,
        durationMin=5,
        arrivedAt="2026-10-31T07:20:00-06:00",
    )
    add(client, room["id"], label="P3", level=1, durationMin=30, arrivedAt=SHIFT)
    return room


def test_create_and_list_rooms(client):
    first = new_room(client, name="Sala A")
    second = new_room(client, doctors=2, name="Sala B")
    assert first["status"] == "open"
    assert first["doctors"] == 1
    assert datetime.fromisoformat(first["shiftStartedAt"]) == datetime.fromisoformat(
        SHIFT
    )
    listed = client.get("/api/rooms").json()
    assert [r["id"] for r in listed] == [second["id"], first["id"]]


def test_room_defaults_shift_to_now(client):
    room = client.post("/api/rooms", json={"name": "Ahora"}).json()
    assert datetime.fromisoformat(room["shiftStartedAt"]) == NOW


def test_room_detail_has_snapshot(client):
    room = guide_room(client)
    data = client.get(f"/api/rooms/{room['id']}").json()
    assert [p["label"] for p in data["patients"]] == ["P1", "P2", "P3"]
    snapshot = data["snapshot"]
    assert snapshot["t0"] == 30
    assert snapshot["doctorsFreeAt"] == [30]
    assert [
        (p["id"], p["wait"], p["waitingNow"], p["minutesToLimit"])
        for p in snapshot["patients"]
    ] == [
        ("P1", 5, 35, -25),
        ("P2", 40, 70, -10),
        ("P3", 0, 30, -30),
    ]


def test_future_shift_has_no_snapshot(client):
    room = client.post(
        "/api/rooms",
        json={"name": "Mañana", "shiftStartedAt": "2026-11-01T08:00:00-06:00"},
    ).json()
    assert client.get(f"/api/rooms/{room['id']}").json()["snapshot"] is None


def test_solve_room_at_shift_start_matches_guide(client):
    room = guide_room(client)
    response = client.post(f"/api/rooms/{room['id']}/solve", json={"at": SHIFT})
    assert response.status_code == 201
    data = response.json()
    assert data["t0"] == 0
    assert data["cost"] == 280
    assert data["baseline"]["cost"] == 320
    assert data["sameCost"] is True
    assert data["roomId"] == room["id"]
    assert [s["patient"] for s in data["results"]["astar"]["steps"]] == [
        "P3",
        "P2",
        "P1",
    ]


def test_solve_room_now_uses_clock(client):
    room = guide_room(client)
    data = client.post(f"/api/rooms/{room['id']}/solve", json={}).json()
    assert data["t0"] == 30
    assert datetime.fromisoformat(data["computedAt"]) == NOW
    assert data["cost"] == data["results"]["astar"]["cost"]


def test_counter_example_with_two_doctors(client):
    room = new_room(client, doctors=2)
    for label, level, duration, arrived in [
        ("P1", 3, 25, "06:50"),
        ("P2", 1, 5, "08:00"),
        ("P3", 2, 25, "08:00"),
        ("P4", 3, 5, "07:05"),
    ]:
        add(
            client,
            room["id"],
            label=label,
            level=level,
            durationMin=duration,
            arrivedAt=f"2026-10-31T{arrived}:00-06:00",
        )
    data = client.post(f"/api/rooms/{room['id']}/solve", json={"at": SHIFT}).json()
    assert (data["cost"], data["baseline"]["cost"]) == (40, 140)
    assert data["doctorsFreeAt"] == [0, 0]


def test_attended_patients_and_busy_doctors(client):
    room = new_room(client, doctors=2)
    p1 = add(
        client,
        room["id"],
        level=2,
        durationMin=20,
        arrivedAt="2026-10-31T07:55:00-06:00",
    )
    add(
        client,
        room["id"],
        level=3,
        durationMin=5,
        arrivedAt="2026-10-31T07:20:00-06:00",
    )
    add(client, room["id"], level=1, durationMin=30, arrivedAt=SHIFT)
    attended = client.post(
        f"/api/rooms/{room['id']}/patients/{p1['id']}/attend",
        json={"doctor": 2, "at": "2026-10-31T08:20:00-06:00"},
    ).json()
    assert attended["doctor"] == 2
    data = client.post(f"/api/rooms/{room['id']}/solve", json={}).json()
    assert data["t0"] == 30
    assert data["doctorsFreeAt"] == [30, 40]
    assert sorted(s["patient"] for s in data["results"]["astar"]["steps"]) == [
        "P2",
        "P3",
    ]


def test_labels_are_generated(client):
    room = new_room(client)
    labels = [
        add(client, room["id"], level=3, durationMin=10)["label"] for _ in range(3)
    ]
    assert labels == ["P1", "P2", "P3"]


def test_arrival_defaults_to_now(client):
    room = new_room(client)
    patient = add(client, room["id"], level=3, durationMin=10)
    assert datetime.fromisoformat(patient["arrivedAt"]) == NOW


def test_duplicate_label(client):
    room = new_room(client)
    add(client, room["id"], label="P1", level=3, durationMin=10)
    response = client.post(
        f"/api/rooms/{room['id']}/patients",
        json={"label": "P1", "level": 2, "durationMin": 5},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_LABEL"


def test_update_patient_and_unattend(client):
    room = new_room(client)
    p = add(client, room["id"], level=3, durationMin=10, arrivedAt=SHIFT)
    url = f"/api/rooms/{room['id']}/patients/{p['id']}"
    updated = client.patch(
        url, json={"level": 2, "attendedAt": "2026-10-31T08:10:00-06:00"}
    ).json()
    assert (updated["level"], updated["doctor"]) == (2, 1)
    cleared = client.patch(url, json={"attendedAt": None}).json()
    assert (cleared["attendedAt"], cleared["doctor"]) == (None, None)


def test_attention_before_arrival_is_rejected(client):
    room = new_room(client)
    p = add(
        client,
        room["id"],
        level=3,
        durationMin=10,
        arrivedAt="2026-10-31T08:10:00-06:00",
    )
    response = client.post(
        f"/api/rooms/{room['id']}/patients/{p['id']}/attend",
        json={"at": "2026-10-31T08:05:00-06:00"},
    )
    assert response.status_code == 422
    assert response.json()["field"] == "attendedAt"


def test_doctor_out_of_range(client):
    room = new_room(client, doctors=2)
    p = add(client, room["id"], level=3, durationMin=10)
    response = client.post(
        f"/api/rooms/{room['id']}/patients/{p['id']}/attend", json={"doctor": 3}
    )
    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_DOCTORS",
        "message": "La sala tiene 2 médico(s)",
        "field": "doctor",
    }


def test_null_level_is_rejected(client):
    room = new_room(client)
    p = add(client, room["id"], level=3, durationMin=10)
    response = client.patch(
        f"/api/rooms/{room['id']}/patients/{p['id']}", json={"level": None}
    )
    assert response.status_code == 422
    assert response.json()["field"] == "level"


def test_delete_patient_and_room(client):
    room = guide_room(client)
    patients = client.get(f"/api/rooms/{room['id']}").json()["patients"]
    assert (
        client.delete(
            f"/api/rooms/{room['id']}/patients/{patients[0]['id']}"
        ).status_code
        == 204
    )
    assert len(client.get(f"/api/rooms/{room['id']}").json()["patients"]) == 2
    assert client.delete(f"/api/rooms/{room['id']}").status_code == 204
    assert client.get(f"/api/rooms/{room['id']}").status_code == 404


def test_closed_room_rejects_changes(client):
    room = guide_room(client)
    closed = client.patch(f"/api/rooms/{room['id']}", json={"status": "closed"}).json()
    assert closed["status"] == "closed"
    response = client.post(
        f"/api/rooms/{room['id']}/patients", json={"level": 3, "durationMin": 5}
    )
    assert (response.status_code, response.json()["code"]) == (409, "ROOM_CLOSED")
    response = client.post(f"/api/rooms/{room['id']}/solve", json={})
    assert response.status_code == 409
    assert client.get(f"/api/rooms/{room['id']}").status_code == 200
    reopened = client.patch(f"/api/rooms/{room['id']}", json={"status": "open"}).json()
    assert reopened["status"] == "open"


def test_history(client):
    room = guide_room(client)
    first = client.post(f"/api/rooms/{room['id']}/solve", json={"at": SHIFT}).json()
    second = client.post(
        f"/api/rooms/{room['id']}/solve",
        json={
            "goal": {"type": "k", "value": 1},
            "algorithms": ["ucs", "astar_simple", "astar"],
        },
    ).json()
    history = client.get(f"/api/rooms/{room['id']}/solves").json()
    assert [s["id"] for s in history] == [second["solveId"], first["solveId"]]
    assert history[0]["goalType"] == "k"
    assert history[0]["goalValue"] == 1
    detail = client.get(f"/api/rooms/{room['id']}/solves/{first['solveId']}").json()
    assert detail["cost"] == 280
    assert detail["baselineOrder"] == ["P3", "P1", "P2"]
    assert detail["inputSnapshot"]["patients"][1] == {
        "id": "P2",
        "level": 3,
        "wait": 40,
        "duration": 5,
    }
    assert [r["algorithm"] for r in detail["results"]] == ["ucs", "astar"]
    assert [s["patient"] for s in detail["results"][1]["steps"]] == ["P3", "P2", "P1"]
    second_detail = client.get(
        f"/api/rooms/{room['id']}/solves/{second['solveId']}"
    ).json()
    assert [r["algorithm"] for r in second_detail["results"]] == [
        "ucs",
        "astar_simple",
        "astar",
    ]
    assert second_detail["results"][2]["leftOut"]


def test_solve_with_subset_goal_stores_list(client):
    room = guide_room(client)
    data = client.post(
        f"/api/rooms/{room['id']}/solve",
        json={"goal": {"type": "subset", "value": ["P2"]}},
    ).json()
    detail = client.get(f"/api/rooms/{room['id']}/solves/{data['solveId']}").json()
    assert detail["goalValue"] == ["P2"]


def test_empty_room_cannot_be_solved(client):
    room = new_room(client)
    response = client.post(f"/api/rooms/{room['id']}/solve", json={})
    assert (response.status_code, response.json()["code"]) == (
        422,
        "NO_PENDING_PATIENTS",
    )


def test_solve_before_shift(client):
    room = guide_room(client)
    response = client.post(
        f"/api/rooms/{room['id']}/solve", json={"at": "2026-10-31T07:00:00-06:00"}
    )
    assert response.json()["code"] == "SHIFT_NOT_STARTED"


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/rooms/00000000-0000-4000-8000-000000000099"),
        ("get", "/api/rooms/00000000-0000-4000-8000-000000000099/solves"),
        ("post", "/api/rooms/00000000-0000-4000-8000-000000000099/solve"),
        ("delete", "/api/rooms/00000000-0000-4000-8000-000000000099"),
    ],
)
def test_unknown_room(client, method, path):
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 404
    assert response.json()["code"] == "ROOM_NOT_FOUND"


def test_unknown_patient_and_solve(client):
    room = new_room(client)
    missing = "00000000-0000-4000-8000-000000000099"
    response = client.patch(
        f"/api/rooms/{room['id']}/patients/{missing}", json={"level": 2}
    )
    assert response.json()["code"] == "PATIENT_NOT_FOUND"
    response = client.get(f"/api/rooms/{room['id']}/solves/{missing}")
    assert (response.status_code, response.json()["code"]) == (404, "SOLVE_NOT_FOUND")


@pytest.mark.parametrize(
    "body, field, message",
    [
        ({"name": ""}, "name", "No puede estar vacío"),
        ({"name": "A", "doctors": 0}, "doctors", "Debe ser mayor o igual que 1"),
        (
            {"name": "A", "shiftStartedAt": "2026-10-31T08:00:00"},
            "shiftStartedAt",
            "La fecha debe incluir zona horaria (por ejemplo -06:00)",
        ),
        (
            {"name": "A", "shiftStartedAt": "ayer"},
            "shiftStartedAt",
            "Debe ser una fecha y hora ISO 8601",
        ),
    ],
)
def test_room_validation(client, body, field, message):
    response = client.post("/api/rooms", json=body)
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["message"]) == (field, message)


def test_invalid_uuid(client):
    response = client.get("/api/rooms/no-es-uuid")
    assert response.status_code == 422
    assert response.json()["field"] == "room_id"


def test_rooms_need_supabase_when_not_overridden(settings):
    client = TestClient(create_app(settings))
    response = client.get("/api/rooms")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_NOT_CONFIGURED"
