import pytest

from app.search.generator import generate_patients

GOOD = {"id": "P1", "level": 2, "wait": 5, "duration": 20}


def solve(client, **body):
    return client.post("/api/solve", json={"patients": [GOOD], **body})


def test_unknown_route_uses_error_format(client):
    response = client.get("/api/no-existe")
    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Ruta no encontrada",
        "field": None,
    }


def test_wrong_method_uses_error_format(client):
    response = client.get("/api/solve")
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_unexpected_error_uses_error_format(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routers import solve as solve_router
    from app.main import create_app

    def boom(*args, **kwargs):
        raise RuntimeError("falla inesperada")

    monkeypatch.setattr(solve_router, "solve", boom)
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    response = client.post("/api/solve", json={"patients": [GOOD]})
    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_ERROR",
        "message": "Error interno del servidor",
        "field": None,
    }


@pytest.mark.parametrize(
    "patient, field",
    [
        ({**GOOD, "level": True}, "patients[0].level"),
        ({**GOOD, "level": "2"}, "patients[0].level"),
        ({**GOOD, "level": 2.0}, "patients[0].level"),
        ({**GOOD, "wait": "5"}, "patients[0].wait"),
        ({**GOOD, "duration": False}, "patients[0].duration"),
        ({**GOOD, "id": "   "}, "patients[0].id"),
        ({**GOOD, "id": 7}, "patients[0].id"),
    ],
)
def test_patients_require_exact_types(client, patient, field):
    response = client.post("/api/solve", json={"patients": [patient]})
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["field"]) == (
        "VALIDATION_ERROR",
        field,
    )


@pytest.mark.parametrize(
    "body, field",
    [
        ({"doctors": "2"}, "doctors"),
        ({"doctors": True}, "doctors"),
        ({"criticalFirst": "yes"}, "criticalFirst"),
        ({"criticalFirst": 1}, "criticalFirst"),
        ({"includeTrace": "true"}, "includeTrace"),
        ({"allowApproximate": 0}, "allowApproximate"),
        ({"timeLimitMs": "100"}, "timeLimitMs"),
        ({"start": {"t0": "0"}}, "start.t0"),
        ({"start": {"doctorsFreeAt": ["0"]}}, "start.doctorsFreeAt[0]"),
        ({"goal": {"type": "k", "value": "1"}}, "goal.value"),
        ({"goal": {"type": "k", "value": True}}, "goal.value"),
        ({"goal": {"type": "k", "value": 1.5}}, "goal.value"),
        ({"goal": {"type": "subset", "value": "P1"}}, "goal.value"),
        ({"goal": {"type": "subset", "value": [1]}}, "goal.value"),
    ],
)
def test_options_require_exact_types(client, body, field):
    response = solve(client, **body)
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["field"]) == (
        "VALIDATION_ERROR",
        field,
    )


def test_goal_value_message(client):
    response = solve(client, goal={"type": "k", "value": "1"})
    assert (
        response.json()["message"]
        == "Debe ser un entero (K u horizonte) o una lista de ids"
    )


def test_ids_are_trimmed_before_checking_duplicates(client):
    response = client.post(
        "/api/solve", json={"patients": [GOOD, {**GOOD, "id": " P1 "}]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "DUPLICATE_PATIENT_ID"


def test_subset_ids_are_trimmed(client):
    response = solve(client, goal={"type": "subset", "value": [" P1 "]})
    assert response.status_code == 200


def test_generate_is_capped(client):
    response = client.post("/api/scenarios/generate", json={"n": 100_001})
    assert response.status_code == 422
    assert response.json()["message"] == "Debe ser menor o igual que 100000"


@pytest.mark.parametrize("doctors", [10**6, 10**9, 10**12])
def test_huge_number_of_doctors(client, doctors):
    patients = [
        {"id": p.patient_id, "level": p.level, "wait": p.wait, "duration": p.duration}
        for p in generate_patients(4, 3)
    ]
    response = client.post(
        "/api/solve",
        json={"patients": patients, "doctors": doctors, "algorithms": ["astar"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"]["astar"]["status"] == "optimal"
    assert {s["doctor"] for s in data["results"]["astar"]["steps"]} == {1, 2, 3, 4}


def test_time_limit_is_total_per_algorithm(client):
    import time

    patients = [
        {"id": p.patient_id, "level": p.level, "wait": p.wait, "duration": p.duration}
        for p in generate_patients(60, 2)
    ]
    started = time.perf_counter()
    response = client.post(
        "/api/solve",
        json={
            "patients": patients,
            "doctors": 3,
            "algorithms": ["astar"],
            "timeLimitMs": 600,
        },
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 3
    attempts = response.json()["results"]["astar"]["limitAttempts"]
    assert sum(a["ms"] for a in attempts) <= 700
