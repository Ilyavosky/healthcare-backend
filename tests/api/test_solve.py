import copy

import pytest

from app.search.generator import generate_patients


def post(client, body):
    return client.post("/api/solve", json=body)


def with_changes(body: dict, **changes) -> dict:
    data = copy.deepcopy(body)
    data.update(changes)
    return data


def steps_of(result: dict) -> list[tuple]:
    return [
        (s["patient"], s["doctor"], s["start"], s["end"], s["penalty"])
        for s in result["steps"]
    ]


def test_example_matches_guide(client, example_body):
    response = post(client, example_body)
    assert response.status_code == 200
    data = response.json()
    assert data["results"]["ucs"]["cost"] == 280
    assert data["results"]["astar"]["cost"] == 280
    assert data["results"]["ucs"]["status"] == "optimal"
    assert data["sameCost"] is True
    assert data["baseline"]["cost"] == 320
    assert data["baseline"]["order"] == ["P3", "P1", "P2"]
    assert data["reference"] == "astar"
    assert data["cost"] == 280
    assert data["doctors"] == 1
    assert data["baselineGapPct"] == 14.29
    assert set(data["reductionPct"]) == {"astar"}
    assert steps_of(data["results"]["astar"]) == [
        ("P3", 1, 0, 30, 0),
        ("P2", 1, 30, 35, 40),
        ("P1", 1, 35, 55, 240),
    ]
    assert data["results"]["astar"]["leftOut"] == []
    assert data["results"]["astar"]["closingCost"] == 0
    assert {"patient": "P1", "code": "EXCEEDS_LIMIT", "minutes": 30} in data["alerts"]


def test_response_uses_camel_case(client, example_body):
    result = post(client, example_body).json()["results"]["astar"]
    assert {"maxFrontier", "closingCost", "leftOut", "limitAttempts"} <= set(result)
    assert "afterGoal" in result["steps"][0]


def test_two_doctors(client, four_body):
    data = post(client, with_changes(four_body, doctors=2)).json()
    assert data["cost"] == 80
    assert data["doctors"] == 2
    assert {s["doctor"] for s in data["results"]["astar"]["steps"]} == {1, 2}


def test_doctors_free_at_and_modified_start(client, four_body):
    body = with_changes(
        four_body,
        doctors=2,
        start={"attended": [], "t0": 10, "doctorsFreeAt": [40, 10]},
    )
    data = post(client, body).json()
    first = data["results"]["astar"]["steps"][0]
    assert (first["patient"], first["doctor"], first["start"]) == ("P3", 2, 10)
    assert {"patient": "P3", "code": "ALREADY_LATE", "minutes": 10} in data["alerts"]


def test_start_with_attended(client, example_body):
    body = with_changes(example_body, start={"attended": ["P3"], "t0": 30})
    data = post(client, body).json()
    assert data["cost"] == 280
    assert [s["patient"] for s in data["results"]["astar"]["steps"]] == ["P2", "P1"]


def test_all_algorithms(client, example_body):
    body = with_changes(example_body, algorithms=["ucs", "astar_simple", "astar"])
    data = post(client, body).json()
    assert list(data["results"]) == ["ucs", "astar_simple", "astar"]
    assert {r["cost"] for r in data["results"].values()} == {280}


def test_critical_first_can_be_disabled(client, four_body):
    on = post(client, four_body).json()["cost"]
    off = post(client, with_changes(four_body, criticalFirst=False)).json()["cost"]
    assert (on, off) == (624, 560)


def test_trace(client, example_body):
    body = with_changes(example_body, includeTrace=True, criticalFirst=False)
    trace = post(client, body).json()["results"]["astar"]["trace"]
    assert trace[0] == {
        "attended": [],
        "freeAt": [0],
        "isGoal": False,
        "g": 0,
        "h": 0,
        "f": 0,
    }
    assert [row["f"] for row in trace] == [0, 240, 260, 280, 280, 280]
    assert trace[-1]["isGoal"] is True
    assert trace[-1]["attended"] is None


def test_no_trace_by_default(client, example_body):
    assert post(client, example_body).json()["results"]["astar"]["trace"] == []


def test_k_goal_reports_left_out(client, example_body):
    body = with_changes(example_body, goal={"type": "k", "value": 1})
    data = post(client, body).json()
    astar = data["results"]["astar"]
    assert [s["patient"] for s in astar["steps"]] == ["P3"]
    assert [s["patient"] for s in astar["leftOut"]] == ["P1", "P2"]
    assert all(s["afterGoal"] for s in astar["leftOut"])
    assert astar["closingCost"] == 320
    assert {"patient": "P1", "code": "LEFT_OUT_CRITICAL", "minutes": 25} in data[
        "alerts"
    ]


@pytest.mark.parametrize(
    "goal, expected",
    [
        ({"type": "critical"}, 280),
        ({"type": "horizon", "value": 40}, 280),
        ({"type": "subset", "value": ["P3", "P2"]}, 280),
        ({"type": "all", "value": None}, 280),
    ],
)
def test_goal_types(client, example_body, goal, expected):
    response = post(client, with_changes(example_body, goal=goal))
    assert response.status_code == 200
    assert response.json()["cost"] == expected


def test_large_room_without_limits(client):
    patients = [
        {"id": p.patient_id, "level": p.level, "wait": p.wait, "duration": p.duration}
        for p in generate_patients(60, 5)
    ]
    body = {"patients": patients, "doctors": 60, "algorithms": ["astar"]}
    response = post(client, body)
    assert response.status_code == 200
    data = response.json()
    assert data["results"]["astar"]["status"] == "optimal"
    assert len(data["results"]["astar"]["steps"]) == 60


def test_time_limit_falls_back_to_approximate(client):
    patients = [
        {"id": p.patient_id, "level": p.level, "wait": p.wait, "duration": p.duration}
        for p in generate_patients(24, 7)
    ]
    body = {
        "patients": patients,
        "doctors": 2,
        "algorithms": ["astar"],
        "timeLimitMs": 300,
    }
    data = post(client, body).json()
    astar = data["results"]["astar"]
    assert astar["status"] == "approximate"
    assert astar["weight"] > 1
    assert astar["limitAttempts"][0]["weight"] == 1
    assert data["sameCost"] is None
    assert data["cost"] <= data["baseline"]["cost"]


def test_without_approximation_returns_baseline(client):
    patients = [
        {"id": p.patient_id, "level": p.level, "wait": p.wait, "duration": p.duration}
        for p in generate_patients(24, 7)
    ]
    body = {
        "patients": patients,
        "doctors": 2,
        "algorithms": ["ucs"],
        "timeLimitMs": 50,
        "allowApproximate": False,
    }
    data = post(client, body).json()
    assert data["results"]["ucs"]["status"] == "limit_reached"
    assert data["results"]["ucs"]["cost"] is None
    assert data["reference"] == "baseline"
    assert data["cost"] == data["baseline"]["cost"]


def test_time_limit_zero_means_no_limit(client, example_body):
    response = post(client, with_changes(example_body, timeLimitMs=0))
    assert response.json()["results"]["astar"]["status"] == "optimal"


def test_duplicate_algorithms_are_merged(client, example_body):
    data = post(
        client, with_changes(example_body, algorithms=["astar", "astar"])
    ).json()
    assert list(data["results"]) == ["astar"]


ERROR_CASES = [
    (
        lambda b: b["patients"].append(
            {"id": "P1", "level": 3, "wait": 0, "duration": 5}
        ),
        "DUPLICATE_PATIENT_ID",
        "patients",
    ),
    (
        lambda b: b.update(start={"attended": ["P9"]}),
        "UNKNOWN_PATIENT",
        "start.attended",
    ),
    (
        lambda b: b.update(goal={"type": "subset", "value": ["P9"]}),
        "UNKNOWN_PATIENT",
        "goal.value",
    ),
    (
        lambda b: b.update(goal={"type": "k", "value": 0}),
        "INVALID_GOAL_VALUE",
        "goal.value",
    ),
    (
        lambda b: b.update(goal={"type": "k", "value": 4}),
        "INVALID_GOAL_VALUE",
        "goal.value",
    ),
    (lambda b: b.update(goal={"type": "k"}), "INVALID_GOAL_VALUE", "goal.value"),
    (
        lambda b: b.update(goal={"type": "all", "value": 3}),
        "INVALID_GOAL_VALUE",
        "goal.value",
    ),
    (
        lambda b: b.update(goal={"type": "horizon", "value": 0}),
        "INVALID_GOAL_VALUE",
        "goal.value",
    ),
    (
        lambda b: b.update(start={"attended": ["P1", "P2", "P3"]}),
        "NO_PENDING_PATIENTS",
        "start.attended",
    ),
    (
        lambda b: b["patients"].append(
            {"id": "P4", "level": 3, "wait": -20, "duration": 5}
        ),
        "PATIENT_NOT_ARRIVED",
        "patients",
    ),
    (
        lambda b: b.update(doctors=2, start={"doctorsFreeAt": [0]}),
        "INVALID_DOCTORS",
        "start.doctorsFreeAt",
    ),
    (
        lambda b: b.update(start={"t0": 10, "doctorsFreeAt": [5]}),
        "INVALID_DOCTORS",
        "start.doctorsFreeAt",
    ),
    (lambda b: b.update(doctors=0), "VALIDATION_ERROR", "doctors"),
    (
        lambda b: b["patients"][0].update(level=7),
        "VALIDATION_ERROR",
        "patients[0].level",
    ),
    (
        lambda b: b["patients"][1].update(duration=0),
        "VALIDATION_ERROR",
        "patients[1].duration",
    ),
    (lambda b: b["patients"][2].pop("id"), "VALIDATION_ERROR", "patients[2].id"),
    (
        lambda b: b["patients"][0].update(wait="mucho"),
        "VALIDATION_ERROR",
        "patients[0].wait",
    ),
    (lambda b: b.update(patients=[]), "VALIDATION_ERROR", "patients"),
    (lambda b: b.update(algorithms=["dfs"]), "VALIDATION_ERROR", "algorithms[0]"),
    (lambda b: b.update(algorithms=[]), "VALIDATION_ERROR", "algorithms"),
    (lambda b: b.update(goal={"type": "nada"}), "VALIDATION_ERROR", "goal.type"),
    (lambda b: b.update(start={"t0": -1}), "VALIDATION_ERROR", "start.t0"),
]


@pytest.mark.parametrize("change, code, field", ERROR_CASES)
def test_errors(client, example_body, change, code, field):
    body = copy.deepcopy(example_body)
    change(body)
    response = post(client, body)
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == code
    assert data["field"] == field
    assert data["message"]


def test_validation_messages_are_in_spanish(client, example_body):
    body = with_changes(example_body, doctors=0)
    assert post(client, body).json()["message"] == "Debe ser mayor o igual que 1"
    body = copy.deepcopy(example_body)
    body["patients"][2].pop("id")
    assert post(client, body).json()["message"] == "Falta este campo"


def test_invalid_json(client):
    response = client.post(
        "/api/solve",
        content="{no es json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
