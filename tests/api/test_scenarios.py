from app.search.generator import generate_patients


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config(client):
    data = client.get("/api/config").json()
    assert data["levels"][0] == {
        "level": 1,
        "name": "Crítico",
        "weight": 16,
        "limit": 0,
    }
    assert [level["limit"] for level in data["levels"]] == [0, 10, 60, 120, 240]
    assert data["goalTypes"] == ["all", "critical", "k", "horizon", "subset"]
    assert data["algorithms"] == ["ucs", "astar_simple", "astar"]
    assert "LEFT_OUT_CRITICAL" in data["alertCodes"]
    assert data["csvColumns"] == ["patient_id", "level", "wait", "duration"]
    assert data["defaults"]["timeLimitMs"] == 10000
    assert data["defaults"]["doctors"] == 1


def test_generate_is_reproducible(client):
    data = client.post("/api/scenarios/generate", json={"n": 6, "seed": 3}).json()
    assert data["seed"] == 3
    expected = generate_patients(6, 3)
    assert [p["id"] for p in data["patients"]] == [p.patient_id for p in expected]
    assert [p["wait"] for p in data["patients"]] == [p.wait for p in expected]


def test_generate_without_seed_returns_one(client):
    data = client.post("/api/scenarios/generate", json={"n": 4}).json()
    assert isinstance(data["seed"], int)
    again = client.post("/api/scenarios/generate", json={"n": 4, "seed": data["seed"]})
    assert again.json()["patients"] == data["patients"]


def test_generate_any_size(client):
    data = client.post("/api/scenarios/generate", json={"n": 300, "seed": 1}).json()
    assert len(data["patients"]) == 300


def test_generate_rejects_zero(client):
    response = client.post("/api/scenarios/generate", json={"n": 0})
    assert response.status_code == 422
    assert response.json()["field"] == "n"


def test_generated_scenario_can_be_solved(client):
    scenario = client.post("/api/scenarios/generate", json={"n": 7, "seed": 9}).json()
    response = client.post(
        "/api/solve", json={"patients": scenario["patients"], "doctors": 2}
    )
    assert response.status_code == 200
    assert response.json()["sameCost"] is True


def test_csv_import(client):
    text = "patient_id,level,wait,duration\nP1,2,5,20\nP2,3,40,5\n"
    response = client.post(
        "/api/scenarios/csv", files={"file": ("sala.csv", text.encode(), "text/csv")}
    )
    assert response.status_code == 200
    assert response.json()["patients"] == [
        {"id": "P1", "level": 2, "wait": 5, "duration": 20},
        {"id": "P2", "level": 3, "wait": 40, "duration": 5},
    ]


def test_csv_import_errors(client):
    bad = "patient_id,level,wait,duration\nP1,9,5,20\n"
    response = client.post(
        "/api/scenarios/csv", files={"file": ("a.csv", bad.encode())}
    )
    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_CSV",
        "message": "Fila 2: El nivel debe estar entre 1 y 5",
        "field": "file",
    }


def test_csv_import_rejects_other_encodings(client):
    text = "patient_id,level,wait,duration\nPé,2,5,20\n".encode("latin-1")
    response = client.post("/api/scenarios/csv", files={"file": ("a.csv", text)})
    assert response.json()["message"] == "El archivo debe estar en UTF-8"


def test_csv_import_rejects_huge_files(client):
    text = "patient_id,level,wait,duration\n" + "P1,2,5,20\n" * 1000
    response = client.post(
        "/api/scenarios/csv", files={"file": ("a.csv", text.encode())}
    )
    assert response.json()["message"] == "El archivo es demasiado grande"


def test_csv_import_requires_file(client):
    response = client.post("/api/scenarios/csv")
    assert response.status_code == 422
    assert response.json()["field"] == "file"


def test_csv_export_round_trip(client, example_body):
    response = client.post("/api/scenarios/csv/export", json=example_body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "escenario.csv" in response.headers["content-disposition"]
    assert response.text.splitlines()[0] == "patient_id,level,wait,duration"
    back = client.post(
        "/api/scenarios/csv", files={"file": ("a.csv", response.content)}
    ).json()
    assert back["patients"] == example_body["patients"]


def test_cors_allows_frontend_origin(client):
    response = client.options(
        "/api/solve",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_other_origin(client):
    response = client.options(
        "/api/solve",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers
